from app import app, db, groq_client, login_required
from flask import render_template, redirect, request, session, jsonify
import json
from services.ai import parse_ai_json
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

@app.route("/plan/select", methods=["POST"])
@login_required
def plan_select():
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
@login_required
def plan_extend():
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
@login_required
def generate_extended_plan():
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
        # Validate that we got a dict with required fields
        if not isinstance(extended, dict) or not extended.get("title"):
            raise ValueError("AI did not return a valid plan object")
    except Exception as e:
        print(f"AI JSON parsing failed for extended plan: {e}")
        print(f"Raw response: {raw[:500]}")
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
@login_required
def plan_lock():
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
    db.execute("UPDATE users SET locked = True WHERE id = ?", user_id)
    return redirect("/")


@app.route("/plan")
@login_required
def plan_view():
    locked = get_locked_plan(session["user_id"])
    if not locked:
        return redirect("/advice")
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    suggestion = locked["extended"] or locked["basic"]
    return render_template("plan_extend.html", username=username, suggestion=suggestion, locked=True, plan_data=locked["extended"] or locked["basic"], plan=locked)



@app.route("/plan/leave", methods=["POST"])
@login_required
def plan_leave():
    db.execute("DELETE FROM locked_plans WHERE user_id = ?", session["user_id"])
    session.pop("pending_plan", None)
    session.pop("pending_extended_plan", None)
    return redirect("/")