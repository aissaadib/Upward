from app import app, login_required, db
from flask import render_template, session,redirect, jsonify, request
import json
import os
from werkzeug.utils import secure_filename
from services.profile import build_profile_summary

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(file_path):
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

@app.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    if request.method == "POST":
        raw = request.form.get("answers", "{}")
        try:
            answers = json.loads(raw)
        except:
            return render_template("onboarding.html", error=True)

        # Handle file upload
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