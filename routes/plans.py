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


def call_ai_for_section(prompt, section_name, fallback_data):
    """Helper function to call AI for a specific section with fallback"""
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0
        )
        raw = response.choices[0].message.content.strip()
        result = parse_ai_json(raw)
        if isinstance(result, dict):
            return result
        return fallback_data
    except Exception as e:
        print(f"AI error for {section_name}: {e}")
        return fallback_data

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
    path_title = suggestion.get("title", "Career Path")

    # Generate each section with separate AI calls to avoid repetition

    # 1. Basic plan info
    basic_prompt = f"""You are a practical career strategist. A user chose this path: "{path_title}"

USER PROFILE:
{profile}

SELECTED PATH SUMMARY:
{suggestion_text}

Generate ONLY the basic plan information. Be specific to their situation.

Respond ONLY with valid JSON (no markdown):
{{
  "title": "{path_title}",
  "summary": "2-3 sentences on why this path works for them specifically",
  "timeline_months": 6,
  "next_action": "The single most important thing they should do in the next 48 hours"
}}

Rules:
- Be specific to their country, budget, time, education level, and current skills
- No generic fluff"""

    basic_data = call_ai_for_section(basic_prompt, "basic info", {
        "title": path_title,
        "summary": suggestion.get("fit", "A structured path based on your profile."),
        "timeline_months": 6,
        "next_action": suggestion.get("roadmap", ["Start today"])[0] if suggestion.get("roadmap") else "Review your first step."
    })

    # 2. Weekly habits and success metrics
    habits_prompt = f"""You are a practical career strategist. User is pursuing: "{path_title}"

USER PROFILE:
{profile}

Generate ONLY weekly habits and success metrics. Do NOT repeat the path title or summary.

Respond ONLY with valid JSON (no markdown):
{{
  "weekly_habits": ["3-4 consistent weekly habits specific to their situation"],
  "success_metrics": ["4-5 measurable checkpoints to know they are on track"]
}}

Rules:
- Habits must be actionable and realistic given their time constraints
- Metrics must be measurable and specific
- Reference their actual constraints from the profile"""

    habits_data = call_ai_for_section(habits_prompt, "habits and metrics", {
        "weekly_habits": ["Block focused learning time", "Track progress weekly"],
        "success_metrics": ["Complete month 1 deliverable", "Build one portfolio piece"]
    })

    # 3. Skills to build
    skills_prompt = f"""You are a practical career strategist. User is pursuing: "{path_title}"

USER PROFILE:
{profile}

Generate ONLY the skills they need to build. Do NOT repeat any previous content.

Respond ONLY with valid JSON (no markdown):
{{
  "skills_to_build": [
    {{"skill": "Skill name", "priority": "high/medium/low", "how": "Exact way to learn it given their budget"}}
  ]
}}

Rules:
- Focus on skills most critical for this specific path
- Consider their budget (use free resources if budget is limited)
- Be specific about HOW to learn each skill"""

    skills_data = call_ai_for_section(skills_prompt, "skills", {
        "skills_to_build": []
    })

    # 4. Phases (6 months)
    phases_prompt = f"""You are a practical career strategist. User is pursuing: "{path_title}"

USER PROFILE:
{profile}

Generate ONLY the 6-month phase breakdown. Do NOT repeat any previous content.

Respond ONLY with valid JSON (no markdown):
{{
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
  ]
}}

Rules:
- Exactly 6 phases (months 1-6)
- Each month must have actionable steps, not vague advice
- Use free or low-cost resources when budget is limited
- Each phase should build on the previous one
- URLs must be real reputable sites"""

    phases_data = call_ai_for_section(phases_prompt, "phases", {
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
        ]
    })

    # 5. Pitfalls and risks
    risks_prompt = f"""You are a practical career strategist. User is pursuing: "{path_title}"

USER PROFILE:
{profile}

Generate ONLY pitfalls and risks. Do NOT repeat any previous content.

Respond ONLY with valid JSON (no markdown):
{{
  "pitfalls": ["5 common mistakes for someone in their situation on this path"],
  "risks": ["3 honest risks with brief mitigation each"]
}}

Rules:
- Pitfalls should be specific to their situation (education level, budget, location)
- Risks should be realistic and include mitigation strategies
- Do not repeat content from phases or skills"""

    risks_data = call_ai_for_section(risks_prompt, "risks", {
        "pitfalls": suggestion.get("risks", ["Requires consistency"]),
        "risks": suggestion.get("risks", [])
    })

    # 6. Links and resources
    links_prompt = f"""You are a practical career strategist. User is pursuing: "{path_title}"

USER PROFILE:
{profile}

Generate ONLY additional resources and links. Do NOT repeat any previous content.

Respond ONLY with valid JSON (no markdown):
{{
  "links": [{{"label": "Resource", "url": "https://...", "when": "When to use it"}}]
}}

Rules:
- Provide 3-5 high-quality, reputable resources
- Include when in their journey they should use each resource
- Consider their budget (prioritize free resources)
- URLs must be real and working"""

    links_data = call_ai_for_section(links_prompt, "links", {
        "links": suggestion.get("links", [])
    })

    # Combine all sections
    extended = {
        **basic_data,
        **habits_data,
        **skills_data,
        **phases_data,
        **risks_data,
        **links_data
    }

    session["pending_extended_plan"] = extended
    return jsonify({"plan": extended})

@app.route("/plan/lock", methods=["POST"])
@login_required
def plan_lock():
    session["locked"] = 1
    
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
    db.execute("UPDATE users SET locked = 1 WHERE id = ?", user_id)
    return redirect("/")


@app.route("/plan")
@login_required
def plan_view():
    locked_plan = get_locked_plan(session["user_id"])
    if not locked_plan:
        return redirect("/advice")
    user = db.execute("SELECT name, locked FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    locked_value = user[0]["locked"] if user else 0
    suggestion = locked_plan["extended"] or locked_plan["basic"]
    return render_template("plan_extend.html", username=username, suggestion=suggestion, locked=locked_value, plan_data=locked_plan["extended"] or locked_plan["basic"], plan=locked_plan)



@app.route("/plan/leave", methods=["POST"])
@login_required
def plan_leave():
    db.execute("DELETE FROM locked_plans WHERE user_id = ?", session["user_id"])
    db.execute("UPDATE users SET locked = 0 WHERE id = ?", session["user_id"])
    session.pop("pending_plan", None)
    session.pop("pending_extended_plan", None)
    return redirect("/")