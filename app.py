import os
import json
from functools import wraps
from cs50 import SQL
from flask import Flask, session, redirect, jsonify, request
from flask_session import Session
from groq import Groq


def load_local_env(path=".env"):
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


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            if request.is_json:
                return jsonify({"error": "Not logged in"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


app = Flask(__name__)
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_PERMANENT_LIFETIME"] = 86400  # 24 hours
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "flask_session"
app.secret_key = os.environ.get("SECRET_KEY", "fallback-dev-key-change-this")
Session(app)

db = SQL("sqlite:///upward.db")
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SMTP_EMAIL    = os.environ.get("SMTP_EMAIL", "aissa.daoud2010@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_SERVER   = "smtp.gmail.com"

from routes.auth import *
from routes.home import *
from routes.advice import *
from routes.plans import *
from routes.onboarding import *
from routes.courses import *
from routes.test import *

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)