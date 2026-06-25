from app import app, db, login_required
from flask import render_template, session


def init_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            title TEXT,
            description TEXT,
            tags TEXT,
            price INTEGER
        )
    """)
init_db()


@app.route("/courses")
@login_required
def courses():
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"

    course_list = db.execute("SELECT * FROM courses ORDER BY id DESC")

    return render_template("courses.html", username=username, courses=course_list)