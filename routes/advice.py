from app import app, db, groq_client, login_required
from flask import render_template, redirect, session, jsonify
from services.ai import parse_ai_json

@app.route("/advice")
@login_required
def advice():
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    return render_template("advice.html", username=username)


@app.route("/generate_advice", methods=["POST"])
@login_required
def generate_advice():

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

