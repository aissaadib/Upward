#imports

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
from pathlib import Path
# Environment Setup
# Loads variables from .env during local development.


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
# Flask Configuration
app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = os.environ.get("SECRET_KEY", "fallback-dev-key-change-this")
Session(app)
# Database & External Services
db = SQL("sqlite:///upward.db")
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SMTP_EMAIL    = os.environ.get("SMTP_EMAIL", "aissa.daoud2010@gmail.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_SERVER   = "smtp.gmail.com"

# Email Verification Utilities
# Handles signup verification emails.
def send_code(to_email, code):
    msg = MIMEText(f"Your Upward verification code is: {code}")
    msg["Subject"] = "Upward - Verification Code"
    msg["From"]    = SMTP_EMAIL
    msg["To"]      = to_email
    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())


def init_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS locked_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            basic_plan TEXT NOT NULL,
            extended_plan TEXT,
            locked_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


init_db()


def get_locked_plan(user_id):
    rows = db.execute("SELECT * FROM locked_plans WHERE user_id = ?", user_id)
    if not rows:
        return None
    row = rows[0]
    return {
        "basic": json.loads(row["basic_plan"]),
        "extended": json.loads(row["extended_plan"]) if row["extended_plan"] else None,
        "locked_at": row["locked_at"],
    }


# AI Helpers
# Utilities for parsing and formatting AI data.

def parse_ai_json(raw):
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


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
        f"Career priority: {answers.get('q6a', 'Not provided')}",
        f"Preferred environment: {answers.get('q6b', 'Not provided')}",
        f"Risk tolerance: {answers.get('q6c', 'Not provided')}",
        f"5-year success vision: {answers.get('q6d', 'Not provided')}",
        f"Learning style: {answers.get('q8a', 'Not provided')}",
        f"Portfolio status: {answers.get('q8b', 'Not provided')}",
        f"Confidence level: {answers.get('q8c', 'Not provided')}",
        f"Country: {answers.get('q11', 'Not provided')}",
    ]
    return "\n".join(lines)


# ─── Routes ──────────────────────────────────────────────────

@app.route("/")
def index():
    if session.get("user_id") is None:
        return redirect("/login")
    user_id = session["user_id"]
    user = db.execute("SELECT name FROM users WHERE id = ?", user_id)
    username = user[0]["name"] if user else "User"
    locked_plan = get_locked_plan(user_id)
    return render_template("index.html", username=username, locked_plan=locked_plan)


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

#verify user
@app.route("/verify", methods=["GET", "POST"])
def verify():
    if "pending_email" not in session:
        return redirect("/register")
    if request.method == "POST":
        entered = request.form.get("code")
        if entered == session.get("verify_code"):
            db.execute("INSERT INTO users (name, email, hash, locked) VALUES (?, ?, ?, ?)",
                       session["pending_username"], session["pending_email"], session["pending_hash"], False)
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

        session["user_answers"] = answers
        session["career_profile"] = build_profile_summary(answers)
        session.modified = True 

        return redirect("/advice")
    return render_template("onboarding.html")


@app.route("/advice")
def advice():
    if session.get("user_id") is None:
        return redirect("/login")
    
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    with open("output.txt", "w") as file:
        pass  
    with open("session.txt", "w") as file:
        pass  
    with open("debug_ai.txt", "w") as file:
        pass  
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

Based on this profile, identify EXACTLY 5 realistic and distinct opportunities, career paths, projects, learning tracks, income opportunities, or exploration routes that this person can pursue.

CORE RULES

Tailor every recommendation to the profile provided.
Do not generate generic advice.
Do not recommend paths that require qualifications, experience, capital, equipment, or connections that the person clearly does not have.
If additional skills are needed, include them as part of the roadmap instead of assuming they already exist.
Be realistic about effort, difficulty, and expected outcomes.
Challenge unrealistic expectations honestly.
Prefer opportunities that can be started immediately.
Every suggestion must be substantially different.
Never repeat the same idea with different wording.
Focus on opportunities with strong long-term value and clear progression.

ROADMAP REQUIREMENTS

The roadmap must be a practical progression plan.

Exactly 4 steps.
Each step must:
start with a strong action verb
have a clear objective
explain what should be achieved
build naturally on the previous step

Bad:
"Learn Python"

Good:
"Complete a beginner Python course and build a small project demonstrating core concepts."

Each roadmap should end with a tangible result such as:

a project
a portfolio piece
applications submitted
a freelance profile
a business validation
a certification
an audience
revenue
a research output

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
    with open("debug_ai.txt", "w", encoding="utf-8") as f:
        f.write(raw)
    try:
        advice_list = parse_ai_json(raw)
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

    session["last_advice"] = advice_list
    for item in advice_list:
        item.setdefault("title", "Untitled Path")
        item.setdefault("category", "Explore")
        item.setdefault("fit", "")
        item.setdefault("outcome", "")
        item.setdefault("roadmap", [])
        item.setdefault("risks", [])
        item.setdefault("links", [])
    if len(advice_list):
        print("need more advice")
    return jsonify({"advice": advice_list})


@app.route("/plan/select", methods=["POST"])
def plan_select():
    if session.get("user_id") is None:
        return jsonify({"error": "Not logged in"}), 401

    suggestion = request.get_json(silent=True) or {}

    if not suggestion.get("title"):
        return jsonify({"error": "Invalid suggestion"}), 400

    session["pending_plan"] = suggestion
    session.pop("pending_extended_plan", None)

    session.modified = True

    user_id = session["user_id"]

    locked = db.execute(
        "SELECT locked FROM users WHERE id = ?",
        user_id
    )

    session["locked"] = locked[0]["locked"] if locked else 0

    return jsonify({"redirect": "/plan/extend"})

@app.route("/plan/extend")
def plan_extend():

    if session.get("user_id") is None:
        return redirect("/login")

    plan = session.get("pending_plan")
    
    if not plan:
        return redirect("/advice")  

    user_id = session["user_id"]

    locked = db.execute(
        "SELECT locked FROM users WHERE id = ?",
        user_id
    )

    locked_value = locked[0]["locked"] if locked else 0

    user = db.execute(
        "SELECT name FROM users WHERE id = ?",
        user_id
    )

    username = user[0]["name"] if user else "User"

    return render_template(
        "plan_extend.html",
        username=username,
        suggestion=plan,
        locked=locked_value
    )


@app.route("/generate_extended_plan", methods=["POST"])
def generate_extended_plan():
    if session.get("user_id") is None:
        return jsonify({"error": "Not logged in"}), 401

    profile = session.get("career_profile", "")
    suggestion = session.get("pending_plan")
    if not profile or not suggestion:
        return jsonify({"error": "Missing profile or selected path."}), 400

    if session.get("pending_extended_plan"):
        return jsonify({"plan": session["pending_extended_plan"]})

    suggestion_text = json.dumps(suggestion, indent=2)
    prompt = f"""You are a practical career strategist. A user chose this path as their main plan.

USER PROFILE:
{profile}

SELECTED PATH (summary):
{suggestion_text}

Create a detailed, actionable success roadmap tailored to this person. Be specific to their country, budget, time, education level, and current skills. No generic fluff.

Respond ONLY with valid JSON (no markdown):
{{
  "title": "same as selected path title",
  "summary": "2-3 sentences on why this path works for them specifically",
  "timeline_months": 6,
  "next_action": "The single most important thing they should do in the next 48 hours",
  "weekly_habits": ["3-4 consistent weekly habits"],
  "success_metrics": ["4-5 measurable checkpoints to know they are on track"],
  "phases": [
    {{
      "month": 1,
      "title": "Phase name",
      "focus": "What this month is about",
      "actions": ["5-7 specific weekly/biweekly actions"],
      "skills": ["skills to build this month"],
      "deliverable": "Concrete thing they should finish by end of month",
      "resources": [{{"label": "Resource name", "url": "https://real-url.com", "why": "Why use this now"}}]
    }}
  ],
  "skills_to_build": [
    {{"skill": "Skill name", "priority": "high/medium/low", "how": "Exact way to learn it given their budget"}}
  ],
  "pitfalls": ["5 common mistakes for someone in their situation on this path"],
  "risks": ["3 honest risks with brief mitigation each"],
  "links": [{{"label": "Resource", "url": "https://...", "when": "When to use it"}}]
}}

Rules:
- phases: exactly 6 months, each month must have actionable steps not vague advice
- Use free or low-cost resources when their budget is limited
- Reference their actual constraints from the profile
- URLs must be real reputable sites"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        return jsonify({"error": f"Could not reach AI: {e}"}), 502

    raw = response.choices[0].message.content.strip()
    try:
        extended = parse_ai_json(raw)
    except:
        extended = {
            "title": suggestion.get("title", "Your plan"),
            "summary": suggestion.get("fit", "A structured path based on your profile."),
            "timeline_months": 6,
            "next_action": suggestion.get("roadmap", ["Start today"])[0] if suggestion.get("roadmap") else "Review your first step.",
            "weekly_habits": ["Block focused learning time", "Track progress weekly"],
            "success_metrics": ["Complete month 1 deliverable", "Build one portfolio piece"],
            "phases": [
                {
                    "month": i + 1,
                    "title": step[:60] if isinstance(step, str) else f"Month {i+1}",
                    "focus": step if isinstance(step, str) else "",
                    "actions": [step] if isinstance(step, str) else [],
                    "skills": [],
                    "deliverable": f"Finish month {i+1} goals",
                    "resources": suggestion.get("links", [])[:1],
                }
                for i, step in enumerate(suggestion.get("roadmap", ["Start", "Learn", "Build", "Apply"])[:6])
            ],
            "skills_to_build": [],
            "pitfalls": suggestion.get("risks", ["Requires consistency"]),
            "risks": suggestion.get("risks", []),
            "links": suggestion.get("links", []),
        }

    session["pending_extended_plan"] = extended
    return jsonify({"plan": extended})


@app.route("/plan/lock", methods=["POST"])
def plan_lock():
    if session.get("user_id") is None:
        return redirect("/login")
    session["locked"] = True
    
    #locked = db.execute("SELECT id FROM locked_plans WHERE user_id = ?", user_id)
    user_id = session["user_id"]
    basic = session.get("pending_plan")
    extended = session.get("pending_extended_plan")
    if not basic or not extended:
        return redirect("/advice")

    existing = db.execute("SELECT id FROM locked_plans WHERE user_id = ?", user_id)
    if existing:
        db.execute(
            "UPDATE locked_plans SET basic_plan = ?, extended_plan = ?, locked_at = datetime('now') WHERE user_id = ?",
            json.dumps(basic), json.dumps(extended), user_id
        )
    else:
        db.execute(
            "INSERT INTO locked_plans (user_id, basic_plan, extended_plan) VALUES (?, ?, ?)",
            user_id, json.dumps(basic), json.dumps(extended)
        )

    session.pop("pending_plan", None)
    session.pop("pending_extended_plan", None)
    db.execute("UPDATE users SET locked = True")
    return redirect("/")


@app.route("/plan")
def plan_view():
    if session.get("user_id") is None:
        return redirect("/login")
    locked = get_locked_plan(session["user_id"])
    if not locked:
        return redirect("/advice")
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    return render_template("plan.html", username=username, plan=locked)


@app.route("/plan/leave", methods=["POST"])
def plan_leave():
    if session.get("user_id") is None:
        return redirect("/login")
    db.execute("DELETE FROM locked_plans WHERE user_id = ?", session["user_id"])
    session.pop("pending_plan", None)
    session.pop("pending_extended_plan", None)
    return redirect("/")


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)