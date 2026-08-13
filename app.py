"""Flask application entry point. Sets up config, DB, AI client, and registers all route modules."""

import os
import json
import time
import secrets
import tempfile
from functools import wraps
from collections import defaultdict
from cs50 import SQL
from flask import Flask, session, redirect, jsonify, request
from flask_session import Session
from groq import Groq
import stripe


def load_local_env(path=".env"):
    """Load environment variables from .env file into os.environ (development only)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_local_env()


# ── CSRF Protection ──────────────────────────────────────────────
csrf_exempt_endpoints = set()

def csrf_exempt(f):
    """Decorator to exempt a route from CSRF validation."""
    csrf_exempt_endpoints.add(f.__name__)
    return f

def generate_csrf_token():
    """Generate and store a CSRF token in the session."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

# ── Rate Limiting ────────────────────────────────────────────────
rate_limits = defaultdict(list)

def check_rate_limit(key, max_attempts=5, window=60):
    """Returns True if request is within limit, False if rate-limited."""
    now = time.time()
    key_attempts = rate_limits[key]
    rate_limits[key] = [t for t in key_attempts if now - t < window]
    if len(rate_limits[key]) >= max_attempts:
        return False
    rate_limits[key].append(now)
    return True

def login_required(f):
    """Decorator that redirects unauthenticated users to /login, or returns 401 for JSON requests."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            if request.is_json:
                return jsonify({"error": "Not logged in"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator that requires the user to be an admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        user = db.execute("SELECT admin FROM users WHERE id = ?", session["user_id"])
        if not user or not user[0].get("admin"):
            return redirect("/")
        return f(*args, **kwargs)
    return decorated_function


app = Flask(__name__)
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 24 hours
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    print("[warn] SECRET_KEY not set — using a per-boot random key will reset sessions on restart. "
          "Set SECRET_KEY in the environment (Vercel: Settings -> Environment Variables) for stable sessions.")
    secret_key = secrets.token_hex(32)
app.secret_key = secret_key

# ── Database: SQLite by default (local), PostgreSQL when DATABASE_URL is set (Vercel) ──
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres")


def _ddl(sql):
    """Adapt CREATE TABLE DDL to the active dialect."""
    if IS_POSTGRES:
        return sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return sql


db = SQL(DATABASE_URL if IS_POSTGRES else "sqlite:///upward.db")

# On PostgreSQL, run boot DDL on its own autocommit connection: a failed
# statement rolls back instantly instead of poisoning the pooled session
# (which otherwise breaks the next cs50 "BEGIN" — the classic serverless
# cold-start race where many instances create the same tables at once).
if IS_POSTGRES:
    from sqlalchemy import create_engine, text

    _pg_boot = create_engine(DATABASE_URL, pool_pre_ping=True)

    def _pg_boot_exec(sql):
        try:
            with _pg_boot.connect() as _conn:
                _conn.execution_options(isolation_level="AUTOCOMMIT").execute(text(sql))
        except Exception as e:
            print(f"[ddl] skipped: {e}")


def run_boot_ddl(sql):
    """Execute bootstrap DDL safely on the active dialect."""
    if IS_POSTGRES:
        _pg_boot_exec(_ddl(sql))
    else:
        try:
            db.execute(_ddl(sql))
        except Exception:
            pass


def add_col(table, coldef):
    """Create a column if it is missing (safe on both dialects)."""
    if IS_POSTGRES:
        run_boot_ddl(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {coldef}")
    else:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
        except Exception:
            pass


# Sessions: DB-backed on PostgreSQL (persists on serverless), filesystem locally
if IS_POSTGRES:
    from flask_sqlalchemy import SQLAlchemy

    dbx = SQLAlchemy()
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_TYPE"] = "sqlalchemy"
    app.config["SESSION_SQLALCHEMY"] = dbx
    dbx.init_app(app)
else:
    app.config["SESSION_TYPE"] = "filesystem"
    _session_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_session")
    try:
        os.makedirs(_session_dir, exist_ok=True)
        _probe = os.path.join(_session_dir, ".wprobe")
        with open(_probe, "w") as _fh:
            _fh.write("ok")
        os.remove(_probe)
    except OSError:
        # Read-only filesystems (e.g. serverless) -> use the writable temp dir
        _session_dir = os.path.join(tempfile.gettempdir(), "flask_session")
    app.config["SESSION_FILE_DIR"] = _session_dir

Session(app)

if IS_POSTGRES:
    # Create the sessions table (and any app models on the extension)
    with app.app_context():
        dbx.create_all()

# ── CSRF validation ──────────────────────────────────────────────
def csrf_required(f):
    """Decorator that validates CSRF token on POST/PUT/DELETE requests."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE"):
            token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not token or token != session.get("_csrf_token"):
                if request.is_json:
                    return jsonify({"error": "CSRF validation failed"}), 403
                return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_csrf():
    return {"csrf_token": generate_csrf_token(), "csrf_input": f'<input type="hidden" name="csrf_token" value="{generate_csrf_token()}">'}

# ── Security headers ─────────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.path.startswith("/stripe"):
        pass
    return response

# Ensure required tables exist
run_boot_ddl("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    hash TEXT NOT NULL,
    resume TEXT,
    locked INTEGER DEFAULT 0
)""")

# Add admin column silently (safe for existing DBs)
add_col("users", "admin INTEGER DEFAULT 0")

# Add plan_access column silently (safe for existing DBs)
add_col("users", "plan_access INTEGER DEFAULT 0")

# Add thumbnail and created_at to courses (for existing DBs)
add_col("courses", "thumbnail TEXT DEFAULT ''")
add_col("courses", "created_at TEXT DEFAULT CURRENT_TIMESTAMP")
add_col("courses", "stripe_price_id TEXT DEFAULT ''")

# Create purchases table for Stripe payments
run_boot_ddl("""CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    stripe_session_id TEXT UNIQUE,
    subscription_id TEXT,
    payment_intent TEXT,
    amount INTEGER,
    currency TEXT DEFAULT 'mad',
    status TEXT DEFAULT 'completed',
    current_period_end TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)""")

add_col("purchases", "subscription_id TEXT")
add_col("purchases", "current_period_end TEXT")

# Add bank_account column for creator payouts
add_col("users", "bank_account TEXT DEFAULT ''")

# Create creator_earnings table
run_boot_ddl("""CREATE TABLE IF NOT EXISTS creator_earnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    purchase_id INTEGER,
    amount INTEGER NOT NULL,
    paid INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)""")

# Create locked_plans table if missing
run_boot_ddl("""CREATE TABLE IF NOT EXISTS locked_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    basic_plan TEXT NOT NULL,
    extended_plan TEXT,
    locked_at TEXT DEFAULT CURRENT_TIMESTAMP
)""")

# Stripe configuration
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# Admin email for auto-granting admin on login/register
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").lower().strip()

# PayPal configuration (kept for backward compatibility)
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")
PAYPAL_API_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY") or "missing-groq-key")

SMTP_EMAIL    = os.environ.get("SMTP_EMAIL", "aissa.daoud2010@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_SERVER   = "smtp.gmail.com"

from routes.auth import *
from routes.home import *
from routes.advice import *
from routes.plans import *
from routes.agent import *
from routes.onboarding import *
from routes.courses import *
from routes.test import *
from routes.lessons import *
from routes.purchases import *
from routes.admin import *
from routes.profile import *

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
