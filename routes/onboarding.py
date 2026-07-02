"""Onboarding route — collects career profile answers and optional resume upload."""

from app import app, login_required, db, groq_client
from flask import render_template, session, redirect, jsonify, request
import json
import os
from werkzeug.utils import secure_filename
from services.profile import build_profile_summary

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension (.pdf)."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
    """Extract text content from a PDF file using PyPDF2."""
    try:
        import PyPDF2
        text = ""
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return None

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
    """Handle the onboarding questionnaire: save answers and optional resume to session, then redirect to /advice."""
    if request.method == "POST":
        raw = request.form.get("answers", "{}")
        try:
            answers = json.loads(raw)
        except:
            return render_template("onboarding.html", error=True)

        # Handle optional resume PDF upload — extract text and attach to answers
        resume_file = request.files.get('resume_file')
        resume_text = None
        if resume_file and resume_file.filename and allowed_file(resume_file.filename):
            filename = secure_filename(resume_file.filename)
            upload_folder = os.path.join(os.getcwd(), 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, f"{session['user_id']}_{filename}")
            resume_file.save(file_path)
            resume_text = extract_text_from_pdf(file_path)
            if resume_text:
                answers['resume_text'] = resume_text

        session["user_answers"] = answers
        session["career_profile"] = build_profile_summary(answers)
        session.modified = True

        user_id = session["user_id"]
        db.execute("UPDATE users SET locked = 0 WHERE id = ?", user_id)

        return redirect("/advice")
    return render_template("onboarding.html")
