"""Courses routes — list, view, and delete user-created courses."""

from app import app, db, login_required
from flask import render_template, session, redirect, jsonify
from collections import Counter


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


def get_all_tags(course_list):
    """Extract unique tags and their counts from a list of course dicts."""
    all_tags = []
    for c in course_list:
        if c.get("tags"):
            for t in c["tags"].split(","):
                tag = t.strip().lower()
                if tag:
                    all_tags.append(tag)
    counts = Counter(all_tags)
    unique = sorted(counts.keys(), key=lambda t: (-counts[t], t))
    return unique, dict(counts)


@app.route("/courses")
@login_required
def courses():
    """Render course listing page with tag filter."""
    user = db.execute("SELECT name, locked FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    locked = user[0]["locked"] if user else 0

    course_list = db.execute("SELECT * FROM courses ORDER BY id DESC")
    for c in course_list:
        c["is_owner"] = (c["owner_id"] == session["user_id"])

    all_tags, _ = get_all_tags(course_list)
    return render_template("courses.html", username=username, courses=course_list, locked=locked, all_tags=all_tags)


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
