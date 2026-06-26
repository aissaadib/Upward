from app import app, db, login_required
from flask import render_template, request, session, redirect
import PyPDF2

# Ensure lessons table exists with all columns
def init_lessons_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            num INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            title TEXT,
            content TEXT
        )
    """)
    # Try to add title column if it doesn't exist (older schema)
    try:
        db.execute("ALTER TABLE lessons ADD COLUMN title TEXT")
    except Exception:
        pass

init_lessons_db()


@app.route("/lessons/<int:course_id>")
@login_required
def lessons(course_id):
    # Get course details
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return redirect("/courses")
    course = course[0]

    # Get all lessons for this course
    lesson_list = db.execute(
        "SELECT * FROM lessons WHERE course_id = ? ORDER BY num ASC",
        course_id
    )

    # Check if current user is the owner
    is_owner = course["owner_id"] == session["user_id"]

    # Get username
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"

    return render_template(
        "lessons.html",
        username=username,
        course=course,
        lessons=lesson_list,
        is_owner=is_owner
    )


@app.route("/customize_lesson/<int:course_id>")
@login_required
def customize_lesson(course_id):
    # Verify course exists and user is owner
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return redirect("/courses")
    course = course[0]

    if course["owner_id"] != session["user_id"]:
        return redirect(f"/lessons/{course_id}")

    # Get username
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"

    return render_template(
        "costumize_lessons.html",
        username=username,
        course=course
    )


@app.route("/create_lesson/<int:course_id>", methods=["POST"])
@login_required
def create_lesson(course_id):
    # Verify course exists and user is owner
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return redirect("/courses")
    course = course[0]

    if course["owner_id"] != session["user_id"]:
        return redirect(f"/lessons/{course_id}")

    title = request.form.get("title", "").strip()
    content_text = request.form.get("content", "").strip()
    lesson_file = request.files.get("lesson_pdf")

    if not title:
        return render_template(
            "costumize_lessons.html",
            username=session.get("username", "User"),
            course=course,
            error="Lesson title is required."
        )

    # If PDF uploaded, extract text and use it as content
    if lesson_file and lesson_file.filename:
        try:
            if lesson_file.filename.endswith('.pdf'):
                pdf_reader = PyPDF2.PdfReader(lesson_file)
                extracted_text = ""
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        extracted_text += page_text + "\n"
                content = extracted_text.strip() if extracted_text else content_text
            elif lesson_file.filename.endswith('.txt'):
                content = lesson_file.read().decode('utf-8').strip()
            else:
                content = content_text
        except Exception as e:
            print(f"Error reading lesson file: {e}")
            content = content_text
    else:
        content = content_text

    # Insert lesson into database
    db.execute(
        """INSERT INTO lessons (course_id, title, content)
           VALUES (?, ?, ?)""",
        course_id, title, content
    )

    return redirect(f"/lessons/{course_id}")
