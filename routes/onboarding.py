"""Onboarding route — collects career profile answers and builds AI profile."""

from app import app, login_required, db, groq_client
from flask import render_template, session, redirect, jsonify, request
import json
from services.profile import build_profile_summary

@app.route("/api/generate_tools", methods=["POST"])
@login_required
def generate_tools():
    """AI-generate a list of at least 16 popular tools/skills for a given career field."""
    data = request.get_json()
    field = data.get("field", "").strip()
    if not field:
        return jsonify({"error": "No field provided"}), 400

    prompt = f"""List 16 or fewer of the most popular tools, software, technologies, or skills that someone in "{field}" should know.
Return ONLY a valid JSON array of strings, like: ["Tool 1","Tool 2",...]. No markdown, no explanation."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0
        )
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        tools = json.loads(text)
        if not isinstance(tools, list) or len(tools) < 1:
            raise ValueError("Invalid response format")
        return jsonify({"tools": tools})
    except Exception as e:
        print(f"Generate tools error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate_skills", methods=["POST"])
@login_required
def generate_skills():
    """AI-generate a short list (≤5) of core skills for a given career field."""
    data = request.get_json()
    field = data.get("field", "").strip()
    if not field:
        return jsonify({"error": "No field provided"}), 400

    prompt = f"""List 5 or fewer of the most important core skills that someone in "{field}" should master.
Return ONLY a valid JSON array of strings, like: ["Skill 1","Skill 2",...]. No markdown, no explanation."""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0
        )
        text = response.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        skills = json.loads(text)
        if not isinstance(skills, list) or len(skills) < 1:
            raise ValueError("Invalid response format")
        return jsonify({"skills": skills})
    except Exception as e:
        print(f"Generate skills error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    """Handle the onboarding questionnaire: save answers, load stored resume, build AI profile."""
    user_id = session["user_id"]

    if request.method == "POST":
        raw = request.form.get("answers", "{}")
        try:
            answers = json.loads(raw)
        except:
            return render_template("onboarding.html", error=True)

        # Attach stored resume from DB
        user = db.execute("SELECT resume FROM users WHERE id = ?", user_id)
        if user and user[0]["resume"]:
            answers['resume_text'] = user[0]["resume"]

        session["user_answers"] = answers
        session["career_profile"] = build_profile_summary(answers)
        session.modified = True

        db.execute("UPDATE users SET locked = 0 WHERE id = ?", user_id)
        return redirect("/advice")

    return render_template("onboarding.html")
