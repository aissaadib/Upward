"""Courses routes — list, view, and delete user-created courses."""

from app import app, db, login_required
from flask import render_template, session, redirect, jsonify


def init_db():
    """Create the courses table if it does not exist."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            title TEXT,
            description TEXT,
            tags TEXT,
            price INTEGER,
            rating INTEGER
        )
    """)
init_db()


@app.route("/courses")
@login_required
def courses():
    """Render course listing page; mark courses owned by the current user."""
    user = db.execute("SELECT name, locked FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    locked = user[0]["locked"] if user else 0

    course_list = db.execute("SELECT * FROM courses ORDER BY id DESC")
    # Flag each course as owned by the current session user
    for c in course_list:
        c["is_owner"] = (c["owner_id"] == session["user_id"])

    return render_template("courses.html", username=username, courses=course_list, locked=locked)


@app.route("/delete_course/<int:course_id>", methods=["POST"])
@login_required
def delete_course(course_id):
    """Delete a course and its lessons, verifying the current user is the owner."""
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return "Not found", 404
    if course[0]["owner_id"] != session["user_id"]:
        return "Unauthorized", 403
    db.execute("DELETE FROM lessons WHERE course_id = ?", course_id)
    db.execute("DELETE FROM courses WHERE id = ?", course_id)
    return "OK"
