"""Advice routes — generates AI-powered career suggestions based on user profile."""

from app import app, db, groq_client, login_required
from flask import render_template, redirect, session, jsonify
from services.ai import parse_ai_json

@app.route("/advice")
@login_required
def advice():
    """Render the advice page after resetting the user's locked status."""
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    db.execute("UPDATE users SET locked = 0 WHERE id = ?", session["user_id"])
    return render_template("advice.html", username=username)


@app.route("/generate_advice", methods=["POST"])
@login_required
def generate_advice():
    """Call the AI to generate 7 career suggestions based on the user's stored profile."""

    profile = session.get("career_profile", "")
    if not profile:
        return jsonify({"error": "No profile found. Please complete onboarding first."}), 400

    # ── WIP AI PROMPT ─────────────────────────────────────────
    # The profile variable contains all user answers structured as key: value lines.
    prompt = f"""You are a practical career advisor helping a real person plan their next steps.

Here is their profile:
{profile}

Based on this profile, identify EXACTLY 7 realistic and distinct opportunities, career paths, projects, learning tracks, income opportunities, or exploration routes that this person can pursue.

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

CRITICAL: Each suggestion must have UNIQUE and SPECIFIC content. Do not repeat the same title, category, or description across different suggestions. Each "fit" field must contain distinct, actionable information specific to that particular opportunity.

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
[{{"title":"","category":"","fit":"","outcome":"","roadmap":["","","",""],"risks":["",""],"links":[{{"label":"","url":""}}]}}]

REVIEW YOUR OUTPUT BEFORE SUBMITTING:
1. Are all 7 titles unique?
2. Does each "fit" field contain specific, distinct information?
3. Are there no repeated phrases or descriptions?
4. Is each suggestion tailored to the specific profile provided?

"""
    # ─────────────────────────────────────────────────────────

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0
        )
    except Exception as e:
        print(f"Groq API error: {e}")
        return jsonify({"error": "AI service temporarily unavailable. Please try again."}), 502

    raw = response.choices[0].message.content.strip()
    try:
        advice_list = parse_ai_json(raw)
        # Validate that we got a list with at least one item
        if not isinstance(advice_list, list) or len(advice_list) == 0:
            raise ValueError("AI did not return a valid list")
    except Exception as e:
        print(f"AI JSON parsing failed: {e}")
        print(f"Raw response: {raw[:500]}")
        parts = [p.strip() for p in raw.split("\n\n") if p.strip()]
        if not parts:
            # Generic fallback when AI output is completely unparseable
            advice_list = [{
                "title": "Explore your field",
                "category": "Research",
                "fit": "Start by researching different roles and opportunities in your chosen field to understand what interests you most.",
                "outcome": "A clearer understanding of available paths and requirements.",
                "roadmap": ["Research job descriptions", "Identify required skills", "Talk to people in the field", "Create a learning plan"],
                "risks": ["Information overload", "Changing interests"],
                "links": []
            }]
        else:
            # Fallback: wrap each paragraph into a suggestion object
            advice_list = [{
                "title": f"Suggestion {idx+1}",
                "category": "Explore",
                "fit": p,
                "outcome": "A clearer next step based on your profile.",
                "roadmap": ["Start with research", "Learn the basics", "Build a small proof", "Share and get feedback"],
                "risks": ["Requires consistency", "Competitive field"],
                "links": []
            } for idx, p in enumerate(parts[:5])]

    # Validate for repetitive content — regenerate if >30% titles are duplicates
    titles = [item.get("title", "").lower().strip() for item in advice_list]
    unique_titles = set(titles)
    if len(unique_titles) < len(titles) * 0.7:
        print("Detected repetitive titles, regenerating with fallback")
        advice_list = [{
            "title": f"Path {i+1}: {['Freelance', 'Full-time job', 'Internship', 'Contract work', 'Remote work', 'Part-time', 'Volunteer'][i%7]}",
            "category": ["Technology", "Business", "Creative", "Healthcare", "Education", "Finance", "Marketing"][i%7],
            "fit": f"A structured approach to building skills and experience in this area, tailored to your background and goals.",
            "outcome": "Clear progression toward your career objectives with measurable milestones.",
            "roadmap": ["Research requirements", "Learn essential skills", "Build portfolio", "Apply for opportunities"],
            "risks": ["Competition", "Skill gaps", "Time commitment"],
            "links": []
        } for i in range(7)]

    session["last_advice"] = advice_list
    # Ensure every suggestion has all expected keys
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
