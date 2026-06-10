import os
import random
import smtplib
import json
from email.mime.text import MIMEText
from cs50 import SQL
from flask import Flask, redirect, render_template, request, session, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
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

app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = os.environ.get("SECRET_KEY", "fallback-dev-key-change-this")
Session(app)

db = SQL("sqlite:///upward.db")
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SMTP_EMAIL    = os.environ.get("SMTP_EMAIL", "aissa.daoud2010@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_SERVER   = "smtp.gmail.com"


def send_code(to_email, code):
    msg = MIMEText(f"Your Upward verification code is: {code}")
    msg["Subject"] = "Upward - Verification Code"
    msg["From"]    = SMTP_EMAIL
    msg["To"]      = to_email
    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())


def build_profile_summary(answers):
    """
    Maps raw onboarding answers into a structured profile string
    that will be injected into the AI prompt.
    """
    skills = answers.get("q2", [])
    if isinstance(skills, list):
        skills = ", ".join(skills) if skills else "None listed"

    lines = [
        f"Main field: {answers.get('field', 'Not provided')}",
        f"Current level: {answers.get('q0', 'Not provided')}",
        f"Education status: {answers.get('q1', 'Not provided')}",
        f"Existing tools and skills: {skills}",
        f"Strongest skill: {answers.get('q3', 'Not provided')}",
        f"Preferred type of work: {answers.get('q4', 'Not provided')}",
        f"Main goal: {answers.get('q5', 'Not provided')}",
        f"Biggest blocker: {answers.get('q6', 'Not provided')}",
        f"Monthly learning budget: {answers.get('q7', 'Not provided')}",
        f"Weekly time available: {answers.get('q8', 'Not provided')}",
        f"Timeline for results: {answers.get('q9', 'Not provided')}",
        f"Preferred work style: {answers.get('q10', 'Not provided')}",
        f"Region: {answers.get('q11', 'Not provided')}",
        f"Country: {answers.get('q12', 'Not provided')}",
        f"City: {answers.get('q13', 'Not provided')}",
    ]
    return "\n".join(lines)


# ─── Routes ──────────────────────────────────────────────────

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


@app.route("/login/google")
def login_google():
    return "Google login coming soon!"


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
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


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if session.get("user_id") is None:
        return redirect("/login")
    if request.method == "POST":
        raw = request.form.get("answers", "{}")
        try:
            answers = json.loads(raw)
        except:
            return render_template("onboarding.html", error=True)

        # Store raw answers for future use
        session["user_answers"] = answers

        # Build the structured profile summary for the AI
        session["career_profile"] = build_profile_summary(answers)

        return redirect("/advice")
    return render_template("onboarding.html")


@app.route("/advice")
def advice():
    if session.get("user_id") is None:
        return redirect("/login")
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    return render_template("advice.html", username=username)


@app.route("/generate_advice", methods=["POST"])
def generate_advice():
    if session.get("user_id") is None:
        return jsonify({"error": "Not logged in"}), 401

    profile = session.get("career_profile", "")
    if not profile:
        return jsonify({"error": "No profile found. Please complete onboarding first."}), 400

    # ── WIP AI PROMPT ─────────────────────────────────────────
    # This prompt will be refined as the product grows.
    # The profile variable contains all user answers structured
    # as key: value lines ready to be injected here.
    prompt = f"""You are a practical career advisor helping a real person plan their next steps.

Here is their profile:
{profile}

Based on this, identify exactly 5 concrete things this person can realistically do with their current competence and situation.

Rules:
- Be specific to their field, level, country, and budget
- Do NOT suggest things that require skills they don't have yet
- Challenge unrealistic expectations honestly
- Each suggestion must be different (don't repeat the same path)
- Roadmap steps must be actionable month-by-month actions

For each suggestion respond with:
- title: a short name for the path or project
- category: one of "Build", "Learn", "Earn", "Apply", "Explore"
- fit: one sentence explaining why this matches their profile specifically
- outcome: what they will have after completing the roadmap
- roadmap: exactly 4 steps, each a concrete monthly action starting with a verb
- risks: 2 honest challenges or things that could go wrong
- links: 3 real URLs from reputable sites (freecodecamp.org, coursera.org, roadmap.sh, developer.mozilla.org, youtube.com, kaggle.com, edx.org, github.com)

Respond ONLY with a valid JSON array. No markdown. No explanation:
[{{"title":"","category":"","fit":"","outcome":"","roadmap":["","","",""],"risks":["",""],"links":[{{"label":"","url":""}}]}}]"""
    # ─────────────────────────────────────────────────────────

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        return jsonify({"error": f"Could not reach AI: {e}"}), 502

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        advice_list = json.loads(raw)
    except:
        parts = [p.strip() for p in raw.split("\n\n") if p.strip()]
        advice_list = [{
            "title": f"Suggestion {idx+1}",
            "category": "Explore",
            "fit": p,
            "outcome": "A clearer next step based on your profile.",
            "roadmap": ["Start with research", "Learn the basics", "Build a small proof", "Share and get feedback"],
            "risks": ["Requires consistency", "Competitive field"],
            "links": []
        } for idx, p in enumerate(parts[:5])]

    return jsonify({"advice": advice_list})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)