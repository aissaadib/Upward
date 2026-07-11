"""Profile routes — update CV, change password, edit username."""

from app import app, db, login_required
from flask import render_template, request, session, redirect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
import PyPDF2


def extract_text_from_pdf(file_path):
    """Extract text content from a PDF file."""
    try:
        text = ""
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return None


@app.route("/profile")
@login_required
def profile():
    """Show the profile page with current user info."""
    user = db.execute("SELECT name, email, resume, locked, admin FROM users WHERE id = ?",
                      session["user_id"])
    if not user:
        return redirect("/login")
    user = user[0]
    return render_template("profile.html",
                           username=user["name"],
                           email=user["email"],
                           has_resume=bool(user.get("resume")),
                           locked=user.get("locked", 0),
                           is_admin=bool(user.get("admin")))


@app.route("/profile/update", methods=["POST"])
@login_required
def profile_update():
    """Update username and/or upload a new resume/CV."""
    new_name = request.form.get("username", "").strip()

    if not new_name:
        return render_template("profile.html",
                               username=session.get("username", "User"),
                               email="",
                               has_resume=False,
                               error="Username cannot be empty.")

    # Check if username is taken by another user
    existing = db.execute("SELECT id FROM users WHERE name = ? AND id != ?",
                          new_name, session["user_id"])
    if existing:
        user = db.execute("SELECT name, email, resume, locked, admin FROM users WHERE id = ?",
                          session["user_id"])
        u = user[0] if user else {}
        return render_template("profile.html",
                               username=session.get("username", "User"),
                               email=u.get("email", ""),
                               has_resume=bool(u.get("resume")),
                               error="Username already taken.")

    db.execute("UPDATE users SET name = ? WHERE id = ?", new_name, session["user_id"])
    session["username"] = new_name

    # Handle resume upload
    resume_file = request.files.get("resume")
    if resume_file and resume_file.filename:
        if not resume_file.filename.lower().endswith(".pdf"):
            user = db.execute("SELECT name, email, resume, locked, admin FROM users WHERE id = ?",
                              session["user_id"])
            u = user[0] if user else {}
            return render_template("profile.html",
                                   username=new_name,
                                   email=u.get("email", ""),
                                   has_resume=bool(u.get("resume")),
                                   error="Resume must be a PDF file.")

        upload_folder = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        filename = secure_filename(f"profile_{session['user_id']}_{resume_file.filename}")
        file_path = os.path.join(upload_folder, filename)
        resume_file.save(file_path)
        resume_text = extract_text_from_pdf(file_path)
        if resume_text:
            db.execute("UPDATE users SET resume = ? WHERE id = ?",
                       resume_text, session["user_id"])

    return redirect("/profile?msg=Profile updated")


@app.route("/profile/change-password", methods=["POST"])
@login_required
def profile_change_password():
    """Change the user's password after verifying current password."""
    current = request.form.get("current_password", "")
    new_pass = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not current or not new_pass or not confirm:
        return redirect("/profile?error=All password fields are required")

    if new_pass != confirm:
        return redirect("/profile?error=New passwords do not match")

    if len(new_pass) < 6:
        return redirect("/profile?error=New password must be at least 6 characters")

    user = db.execute("SELECT hash FROM users WHERE id = ?", session["user_id"])
    if not user or not check_password_hash(user[0]["hash"], current):
        return redirect("/profile?error=Current password is incorrect")

    db.execute("UPDATE users SET hash = ? WHERE id = ?",
               generate_password_hash(new_pass), session["user_id"])

    return redirect("/profile?msg=Password changed successfully")
