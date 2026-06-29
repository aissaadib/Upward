from app import app, db, login_required, groq_client
from flask import render_template, request, session, redirect, jsonify
import PyPDF2
from services.ai import parse_ai_json

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

    if not title:
        return render_template(
            "costumize_lessons.html",
            username=session.get("username", "User"),
            course=course,
            error="Lesson title is required."
        )

    # Insert lesson into database
    db.execute(
        """INSERT INTO lessons (course_id, title, content)
           VALUES (?, ?, ?)""",
        course_id, title, content_text
    )

    return redirect(f"/lessons/{course_id}")


@app.route("/edit_lesson/<int:lesson_id>")
@login_required
def edit_lesson(lesson_id):
    lesson = db.execute("SELECT * FROM lessons WHERE num = ?", lesson_id)
    if not lesson:
        return redirect("/courses")
    lesson = lesson[0]
    course = db.execute("SELECT * FROM courses WHERE id = ?", lesson["course_id"])
    if not course or course[0]["owner_id"] != session["user_id"]:
        return redirect("/courses")
    course = course[0]
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    return render_template("costumize_lessons.html",
        username=user[0]["name"] if user else "User",
        course=course, lesson=lesson)


@app.route("/update_lesson/<int:lesson_id>", methods=["POST"])
@login_required
def update_lesson(lesson_id):
    lesson = db.execute("SELECT * FROM lessons WHERE num = ?", lesson_id)
    if not lesson:
        return redirect("/courses")
    lesson = lesson[0]
    course = db.execute("SELECT * FROM courses WHERE id = ?", lesson["course_id"])
    if not course or course[0]["owner_id"] != session["user_id"]:
        return redirect("/courses")
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if not title:
        return render_template("costumize_lessons.html",
            username=session.get("username", "User"),
            course=course[0], lesson=lesson, error="Title is required.")
    db.execute("UPDATE lessons SET title = ?, content = ? WHERE num = ?",
        title, content, lesson_id)
    return redirect(f"/lessons/display/{lesson_id}")


@app.route("/delete_lesson/<int:lesson_id>", methods=["POST"])
@login_required
def delete_lesson(lesson_id):
    lesson = db.execute("SELECT * FROM lessons WHERE num = ?", lesson_id)
    if not lesson:
        return "Not found", 404
    course = db.execute("SELECT * FROM courses WHERE id = ?", lesson[0]["course_id"])
    if not course or course[0]["owner_id"] != session["user_id"]:
        return "Unauthorized", 403
    db.execute("DELETE FROM lessons WHERE num = ?", lesson_id)
    return "OK"


@app.route("/api/extract_lesson", methods=["POST"])
@login_required
def extract_lesson():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400

    try:
        if file.filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        elif file.filename.endswith('.txt'):
            text = file.read().decode('utf-8')
        else:
            return jsonify({"error": "Only PDF and TXT files are supported"}), 400

        text = text.strip()
        if not text:
            return jsonify({"error": "Could not extract text from file"}), 400

        prompt = f"""You are an educational content formatter. Format the following lesson text into clean HTML WITHOUT summarizing or rewriting it. Keep the EXACT content but make it readable.

LESSON TEXT:
{text}

Return ONLY clean HTML (no markdown, no JSON). Use these tags:
- <h3> for section headings
- <p> for paragraphs
- <ul><li> for bullet lists
- <ol><li> for numbered lists
- <blockquote> for important notes
- <strong> for key terms
- <br> for line breaks

Preserve all original content exactly. Do NOT change any words."""

        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0
        )
        html = response.choices[0].message.content.strip()
        html = html.replace("```html", "").replace("```", "").strip()
        return jsonify({"html": html})

    except Exception as e:
        print(f"Extract error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/lessons/display/<int:lesson_id>")
@login_required
def lesson_display(lesson_id):
    lesson = db.execute("SELECT * FROM lessons WHERE num = ?", lesson_id)
    if not lesson:
        return redirect("/courses")
    lesson = lesson[0]

    course = db.execute("SELECT * FROM courses WHERE id = ?", lesson["course_id"])
    if not course:
        return redirect("/courses")
    course = course[0]

    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"

    return render_template(
        "lesson_display.html",
        username=username,
        lesson=lesson,
        course=course
    )
