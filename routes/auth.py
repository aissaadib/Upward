"""Authentication routes: login, register, logout, email verification."""

from app import app, db, SMTP_EMAIL, SMTP_PASSWORD, SMTP_SERVER, login_required
from flask import render_template, request, redirect, session
import os
import random
import smtplib
import json
from email.mime.text import MIMEText
from werkzeug.security import check_password_hash, generate_password_hash


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
def login():
    """Authenticate user by email/password and set session user_id on success."""
    session.clear()
    if request.method == "POST":
        email    = request.form.get("email")
        password = request.form.get("password")
        if not email or not password:
            return render_template("login.html", error="Fill up all fields")
        rows = db.execute("SELECT * FROM users WHERE email = ?", email)
        if len(rows) != 1:
            return render_template("login.html", error="No account with that email")
        if not check_password_hash(rows[0]["hash"], password):
            return render_template("login.html", error="Invalid password")
        session["user_id"] = rows[0]["id"]
        return redirect("/")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register a new user: validate inputs, send verification code, redirect to /verify."""
    session.clear()
    if request.method == "POST":
        username     = request.form.get("username")
        email        = request.form.get("email")
        password     = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not username or not email or not password or not confirmation:
            return render_template("register.html", error="Fill up all fields")
        if password != confirmation:
            return render_template("register.html", error="Passwords do not match")
        if db.execute("SELECT * FROM users WHERE email = ?", email):
            return render_template("register.html", error="Email already registered")
        if db.execute("SELECT * FROM users WHERE name = ?", username):
            return render_template("register.html", error="Username already taken")
        code = str(random.randint(100000, 999999))
        session["pending_email"]    = email
        session["pending_username"] = username
        session["pending_hash"]     = generate_password_hash(password)
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
    """Placeholder for Google OAuth login — redirects to home."""
    return redirect("/")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    """Verify email code, insert user into DB, and log them in."""
    if "pending_email" not in session:
        return redirect("/register")
    if request.method == "POST":
        entered = request.form.get("code")
        if entered == session.get("verify_code"):
            db.execute("INSERT INTO users (name, email, hash, locked) VALUES (?, ?, ?, ?)",
                       session["pending_username"], session["pending_email"], session["pending_hash"], 0)
            user_id = db.execute("SELECT id FROM users WHERE email = ?",
                                 session["pending_email"])[0]["id"]
            session.clear()
            session["user_id"] = user_id
            return redirect("/")
        else:
            return render_template("verify.html", error="Wrong code, try again")
    return render_template("verify.html")
