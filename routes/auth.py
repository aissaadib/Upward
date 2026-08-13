"""Authentication routes: login, register, logout, email verification."""

from app import app, db, SMTP_EMAIL, SMTP_PASSWORD, SMTP_SERVER, login_required, ADMIN_EMAIL, check_rate_limit, csrf_required
from flask import render_template, request, redirect, session
import os
import random
import smtplib
import json
import secrets
import requests
from urllib.parse import urlencode
from email.mime.text import MIMEText
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


def extract_text_from_pdf(file_path):
    """Extract text content from a PDF file using PyPDF2."""
    try:
        import PyPDF2
        text = ""
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return None


def send_code(to_email, code):
    """Send a 6-digit verification code via SMTP to the given email."""
    msg = MIMEText(f"Your Upward verification code is: {code}")
    msg["Subject"] = "Upward - Verification Code"
    msg["From"]    = SMTP_EMAIL
    msg["To"]      = to_email
    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())

@app.route("/login", methods=["GET", "POST"])
@csrf_required
def login():
    """Authenticate user by email/password and set session user_id on success."""
    if request.method == "POST":
        email    = (request.form.get("email") or "").strip()
        password = request.form.get("password")
        if not email or not password:
            return render_template("login.html", error="Fill up all fields")
        if len(email) > 254 or len(password) > 128:
            return render_template("login.html", error="Invalid input")
        ip = request.remote_addr or "unknown"
        if not check_rate_limit(f"login:{ip}", max_attempts=5, window=60):
            return render_template("login.html", error="Too many attempts. Try again later.")
        rows = db.execute("SELECT * FROM users WHERE email = ?", email)
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], password):
            return render_template("login.html", error="Invalid email or password")
        session["user_id"] = rows[0]["id"]
        session["username"] = rows[0]["name"]
        # Auto-grant admin if email matches
        if ADMIN_EMAIL and rows[0]["email"].lower().strip() == ADMIN_EMAIL:
            db.execute("UPDATE users SET admin = 1 WHERE id = ?", rows[0]["id"])
        return redirect("/")
    _google_errors = {
        "google_not_configured": "Google login is not set up yet.",
        "google_denied": "Google sign-in was cancelled.",
        "google_state": "Google sign-in failed. Please try again.",
        "google_token": "Google sign-in failed. Please try again.",
        "google_error": "Google sign-in failed. Please try again later.",
        "google_no_email": "Your Google account has no email address.",
        "google_unverified": "Please verify your Google email address first.",
    }
    gerr = request.args.get("error")
    return render_template("login.html", error=_google_errors.get(gerr) if gerr else None)

@app.route("/register", methods=["GET", "POST"])
@csrf_required
def register():
    """Register a new user: validate inputs, send verification code, redirect to /verify."""
    # Preserve CSRF token across session clear
    csrf_token = session.get("_csrf_token")
    session.clear()
    if csrf_token:
        session["_csrf_token"] = csrf_token
    if request.method == "POST":
        username     = (request.form.get("username") or "").strip()
        email        = (request.form.get("email") or "").strip()
        password     = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not username or not email or not password or not confirmation:
            return render_template("register.html", error="Fill up all fields")
        if len(username) > 100 or len(email) > 254 or len(password) > 128:
            return render_template("register.html", error="Invalid input length")
        if password != confirmation:
            return render_template("register.html", error="Passwords do not match")
        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 characters")
        ip = request.remote_addr or "unknown"
        if not check_rate_limit(f"register:{ip}", max_attempts=3, window=60):
            return render_template("register.html", error="Too many attempts. Try again later.")
        existing_email = db.execute("SELECT 1 FROM users WHERE email = ?", email)
        if existing_email:
            return render_template("register.html", error="Registration failed. Please try again.")
        existing_user = db.execute("SELECT 1 FROM users WHERE name = ?", username)
        if existing_user:
            return render_template("register.html", error="Registration failed. Please try again.")

        # Handle required resume upload
        resume_file = request.files.get("resume")
        if not resume_file or not resume_file.filename:
            return render_template("register.html", error="Resume / CV is required")
        if not resume_file.filename.lower().endswith(".pdf"):
            return render_template("register.html", error="Resume must be a PDF file")
        resume_file.seek(0, os.SEEK_END)
        file_size = resume_file.tell()
        resume_file.seek(0)
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
        if file_size > MAX_FILE_SIZE:
            return render_template("register.html", error="File too large. Maximum size is 10 MB.")

        upload_folder = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        filename = secure_filename(f"pending_{email}_{resume_file.filename}")
        file_path = os.path.join(upload_folder, filename)
        resume_file.save(file_path)
        resume_text = extract_text_from_pdf(file_path)
        if not resume_text:
            os.remove(file_path)
            return render_template("register.html", error="Could not read text from your PDF. Try a different file.")

        code = str(random.randint(100000, 999999))
        session["pending_email"]    = email
        session["pending_username"] = username
        session["pending_hash"]     = generate_password_hash(password)
        session["pending_resume"]   = resume_text
        session["verify_code"]      = code
        try:
            send_code(email, code)
        except Exception as e:
            return render_template("register.html", error=f"Failed to send email: {e}")
        return redirect("/verify")
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    """Clear the session and redirect to login."""
    session.clear()
    return redirect("/login")

@app.route("/login/google")
def login_google():
    """Start Google OAuth 2.0 login."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    if not client_id:
        return redirect("/login?error=google_not_configured")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI") or (
        request.host_url.rstrip("/") + "/login/google/callback"
    )
    state = secrets.token_hex(16)
    session["_oauth_state"] = state
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@app.route("/login/google/callback")
def login_google_callback():
    """Handle the Google OAuth callback: exchange code, upsert user, log in."""
    error = request.args.get("error")
    if error:
        return redirect("/login?error=google_denied")
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state or state != session.get("_oauth_state"):
        return redirect("/login?error=google_state")
    session.pop("_oauth_state", None)

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI") or (
        request.host_url.rstrip("/") + "/login/google/callback"
    )
    try:
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return redirect("/login?error=google_token")

        info_resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        info_resp.raise_for_status()
        info = info_resp.json()
    except Exception as e:
        print(f"Google OAuth error: {e}")
        return redirect("/login?error=google_error")

    email = (info.get("email") or "").strip().lower()
    if not email:
        return redirect("/login?error=google_no_email")
    if info.get("email_verified") is False:
        return redirect("/login?error=google_unverified")
    name = (info.get("name") or info.get("given_name") or email.split("@")[0]).strip()[:100]

    rows = db.execute("SELECT * FROM users WHERE email = ?", email)
    if rows:
        user = rows[0]
    else:
        db.execute("INSERT INTO users (name, email, hash, resume, locked) VALUES (?, ?, ?, ?, ?)",
                   name, email, "__google__", None, 0)
        user = db.execute("SELECT * FROM users WHERE email = ?", email)[0]

    session["user_id"] = user["id"]
    session["username"] = user["name"] or name
    if ADMIN_EMAIL and email == ADMIN_EMAIL:
        db.execute("UPDATE users SET admin = 1 WHERE id = ?", user["id"])
    return redirect("/")

@app.route("/verify", methods=["GET", "POST"])
@csrf_required
def verify():
    """Verify email code, insert user into DB, and log them in."""
    if "pending_email" not in session:
        return redirect("/register")
    if request.method == "POST":
        entered = request.form.get("code")
        if entered == session.get("verify_code"):
            resume_text = session.get("pending_resume")
            db.execute("INSERT INTO users (name, email, hash, resume, locked) VALUES (?, ?, ?, ?, ?)",
                       session["pending_username"], session["pending_email"], session["pending_hash"], resume_text, 0)
            user_id = db.execute("SELECT id FROM users WHERE email = ?",
                                 session["pending_email"])[0]["id"]
            # Clean up pending keys, keep user_id and username
            username = session["pending_username"]
            pending_email = session.get("pending_email", "")
            for k in list(session.keys()):
                if k.startswith("pending_") or k == "verify_code":
                    session.pop(k, None)
            session["user_id"] = user_id
            session["username"] = username
            # Auto-grant admin if email matches
            if ADMIN_EMAIL and pending_email.lower().strip() == ADMIN_EMAIL:
                db.execute("UPDATE users SET admin = 1 WHERE id = ?", user_id)
            return redirect("/")
        else:
            return render_template("verify.html", error="Wrong code, try again")
    return render_template("verify.html")
