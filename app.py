import os
import random
import smtplib
from email.mime.text import MIMEText
from cs50 import SQL
from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from urllib.parse import urlparse
import ollama 
client = ollama.Client()
model = "gemma3"
app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = os.urandom(24)
Session(app)

db = SQL("sqlite:///upward.db")

SMTP_EMAIL = "aissa.daoud2010@gmail.com"
SMTP_PASSWORD = "rxpgfvfyxczunktx"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def send_code(to_email, code):
    msg = MIMEText(f"Your Upward verification code is: {code}")
    msg["Subject"] = "Upward – Verification Code"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())


@app.route("/")
def index():
    if session.get("user_id") is None:
        return redirect("/login")
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    return render_template("index.html", username=username)


@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()
    if request.method == "POST":
        email = request.form.get("email")
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


@app.route("/login/google")
def login_google():
    return "Google login coming soon!"


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if session.get("user_id") is None:
        return redirect("/login")
    if request.method == "POST":
        profile = request.form.get("profile")
        target_domain = "linkedin.com"
        parsed_url = urlparse(profile)  
        netloc = parsed_url.netloc.lower()
        if netloc == target_domain or netloc.endswith('.' + target_domain):
            print("the right domain name")
            return render_template("index.html")
        print("wrong domain")

        return render_template("onboarding.html",error = True)
    return render_template("onboarding.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    session.clear()
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username or not email or not password or not confirmation:
            return render_template("register.html", error="Fill up all fields")

        if password != confirmation:
            return render_template("register.html", error="Passwords do not match")

        if db.execute("SELECT * FROM users WHERE email = ?", email):
            return render_template("register.html", error="Email already registered")

        code = str(random.randint(100000, 999999))
        session["pending_email"] = email
        session["pending_username"] = username
        session["pending_hash"] = generate_password_hash(password)
        session["verify_code"] = code

        try:
            send_code(email, code)
        except Exception as e:
            return render_template("register.html", error=f"Failed to send email: {e}")

        return redirect("/verify")
    return render_template("register.html")


@app.route("/verify", methods=["GET", "POST"])
def verify():
    if "pending_email" not in session:
        return redirect("/register")

    if request.method == "POST":
        entered = request.form.get("code")
        if entered == session.get("verify_code"):
            db.execute("INSERT INTO users (name, email, hash) VALUES (?, ?, ?)",
                       session["pending_username"], session["pending_email"], session["pending_hash"])
            user_id = db.execute("SELECT id FROM users WHERE email = ?",
                                 session["pending_email"])[0]["id"]
            session.clear()
            session["user_id"] = user_id
            return redirect("/")
        else:
            return render_template("verify.html", error="Wrong code, try again")

    return render_template("verify.html")


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)