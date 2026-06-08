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
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
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

SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "aissa.daoud2010@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_SERVER = "smtp.gmail.com"

def send_code(to_email, code):
    msg = MIMEText(f"Your Upward verification code is: {code}")
    msg["Subject"] = "Upward - Verification Code"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
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

        if db.execute("SELECT * FROM users WHERE name = ?", username):
            return render_template("register.html", error="Username already taken")

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

        labels = {
            "field": "Main field",
            "q0": "Education level",
            "q1": "Experience level",
            "q2": "Strongest skills",
            "q3": "Tools already used",
            "q4": "Favorite kind of work",
            "q5": "Current goal",
            "q6": "Preferred work style",
            "q7": "Weekly learning time",
            "q8": "Biggest challenge",
            "q9": "Budget for learning",
            "q10": "Preferred timeline",
            "q11": "Region",
            "q12": "Country",
            "q13": "City",
        }
        lines = []
        for key, label in labels.items():
            value = answers.get(key, "Not provided")
            if isinstance(value, list):
                value = ", ".join(value)
            lines.append(f"{label}: {value or 'Not provided'}")

        summary = "\n".join(lines)

        session["career_advice"] = summary
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

    career_text = session.get("career_advice", "")
    if not career_text:
        return jsonify({"error": "No profile data found. Please complete onboarding first."}), 400

    count = 5

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{
                "role": "user",
                "content": f"""You are a practical career advisor. Based on this profile, choose exactly {count} concrete things this user can do with their current competence.

Profile:
{career_text}

Each suggestion must be specific, realistic for the user's level and location, and different from the others.

For each suggestion include:
- title: short role, project, or path name
- category: one of "Build", "Learn", "Earn", "Apply", "Explore"
- fit: one short sentence explaining why it fits the user's competence
- outcome: what they could have after following the roadmap
- roadmap: exactly 4 short steps, each starting with a strong action verb
- links: exactly 3 useful links from reputable sites such as freecodecamp.org, coursera.org, edx.org, roadmap.sh, developer.mozilla.org, youtube.com, kaggle.com, github.com, linkedin.com/learning

Respond ONLY with a valid JSON array, no markdown, no extra text:
[{{"title": "suggestion title", "category": "Build", "fit": "why this fits", "outcome": "expected outcome", "roadmap": ["step 1", "step 2", "step 3", "step 4"], "links": [{{"label": "link label", "url": "https://..."}}]}}]"""
            }]
        )
    except Exception as e:
        return jsonify({"error": f"Could not generate advice from Groq: {e}"}), 502

    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        advice_list = json.loads(raw)
    except:
        parts = [p.strip() for p in raw.split("\n\n") if p.strip()]
        advice_list = [{
            "title": f"Suggestion {i+1}",
            "category": "Explore",
            "fit": p,
            "outcome": "A clearer next step based on your profile.",
            "roadmap": ["Choose one direction", "Learn the basics", "Build a small proof", "Share it and ask for feedback"],
            "links": []
        } for i, p in enumerate(parts[:count])]

    return jsonify({"advice": advice_list})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
