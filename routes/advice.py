"""Advice routes — generates AI-powered career suggestions based on user profile."""

from app import app, db, groq_client, login_required, check_rate_limit
from flask import render_template, redirect, session, jsonify
from services.ai import parse_ai_json
import time

@app.route("/advice")
@login_required
def advice():
    """Render the advice page after resetting the user's locked status."""
    user = db.execute("SELECT name, plan_access FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    plan_access = user[0]["plan_access"] if user else 0
    db.execute("UPDATE users SET locked = 0 WHERE id = ?", session["user_id"])
    return render_template("advice.html", username=username, plan_access=plan_access)


@app.route("/generate_advice", methods=["POST"])
@login_required
def generate_advice():
    """Call the AI to generate 7 career suggestions based on the user's stored profile."""
    user_id = session["user_id"]
    if not check_rate_limit(f"ai:{user_id}", max_attempts=10, window=3600):
        return jsonify({"error": "AI rate limit exceeded. Please wait before generating more advice."}), 429

    profile = session.get("career_profile", "")
    if not profile:
        return jsonify({"error": "No profile found. Please complete onboarding first."}), 400

    # ── AI PROMPT ─────────────────────────────────────────
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

CRITICAL: Each suggestion must have UNIQUE and SPECIFIC content. Do not repeat the same title, category, or description across different suggestions.

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

Return ONLY a valid JSON array with exactly 7 objects. Each object must have these keys: "title", "category", "fit", "outcome", "roadmap" (array of 4 strings), "risks" (array of 2-3 strings), "links" (array of objects with "label" and "url"). The "title" and "fit" fields must each be at least 20 characters long. No markdown, no explanation.

REVIEW YOUR OUTPUT BEFORE SUBMITTING:
1. Are all 7 titles unique and descriptive?
2. Does each "fit" field contain specific, distinct information?
3. Are there no repeated phrases or descriptions?
4. Is each suggestion tailored to the specific profile provided?
5. Is every title at least 20 characters long?

"""
    # ─────────────────────────────────────────────────────────

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            timeout=90.0
        )
    except Exception as e:
        print(f"Groq API error (attempt 1): {e}")
        time.sleep(1)
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                timeout=90.0
            )
        except Exception as e2:
            print(f"Groq API error (attempt 2): {e2}")
            return jsonify({"error": "AI service temporarily unavailable. Please try again."}), 502

    raw = response.choices[0].message.content.strip()
    try:
        advice_list = parse_ai_json(raw)
        if not isinstance(advice_list, list) or len(advice_list) == 0:
            raise ValueError("AI did not return a valid list")
        # Validate items have non-blank titles (at least 10 chars)
        valid = []
        for item in advice_list:
            t = item.get("title", "").strip()
            if len(t) >= 10:
                valid.append(item)
        if len(valid) < 4:
            raise ValueError(f"Only {len(valid)} items with valid titles, need at least 4")
        advice_list = valid[:7]
    except Exception as e:
        print(f"AI JSON parsing failed: {e}")
        print(f"Raw response: {raw[:500]}")
        # Retry once with a stricter prompt
        try:
            retry_prompt = prompt + "\n\nCRITICAL: Your previous response was not valid JSON with 7 items. Every title must be at least 20 characters long and descriptive. Return ONLY valid JSON."
            response2 = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": retry_prompt}],
                timeout=90.0
            )
            raw2 = response2.choices[0].message.content.strip()
            advice_list = parse_ai_json(raw2)
            if not isinstance(advice_list, list) or len(advice_list) == 0:
                raise ValueError("Retry also failed")
        except Exception as e2:
            print(f"Retry also failed: {e2}")
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
    # Ensure every suggestion has all expected keys and correct types
    for item in advice_list:
        item.setdefault("title", "Untitled Path")
        item.setdefault("category", "Explore")
        item.setdefault("fit", "")
        item.setdefault("outcome", "")
        item.setdefault("roadmap", [])
        item.setdefault("risks", [])
        item.setdefault("links", [])
        # Normalize risks — AI sometimes returns objects instead of strings
        def _to_str(v):
            if isinstance(v, str): return v
            if isinstance(v, dict):
                return v.get("risk") or v.get("text") or v.get("description") or v.get("name") or str(v)
            return str(v)
        item["risks"] = [_to_str(r) for r in item["risks"]]
        # Normalize roadmap steps to strings
        item["roadmap"] = [_to_str(s) for s in item["roadmap"]]
        # Normalize title, category, fit, outcome to strings
        for k in ("title","category","fit","outcome"):
            if not isinstance(item.get(k), str):
                item[k] = str(item[k]) if item.get(k) else ""
    if len(advice_list):
        print("need more advice")

    return jsonify({"advice": advice_list})
