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
    # Sort: most frequent first, then alphabetically
    unique = sorted(counts.keys(), key=lambda t: (-counts[t], t))
    return unique, dict(counts)


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

    all_tags, tag_counts = get_all_tags(course_list)
    return render_template("courses.html", username=username, courses=course_list, locked=locked, all_tags=all_tags, tag_counts=tag_counts)


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


SEED_COURSES = [
    {"title":"Python Crash Course","description":"Learn Python from scratch with hands-on projects and exercises.","tags":"python, beginner, programming","price":0,"rating":4.5},
    {"title":"React & Next.js Masterclass","description":"Build modern web apps with React, Next.js, and TypeScript.","tags":"javascript, react, frontend, web","price":49,"rating":4.8},
    {"title":"Data Science Fundamentals","description":"Pandas, NumPy, matplotlib and real-world data analysis.","tags":"python, data-science, machine-learning","price":39,"rating":4.3},
    {"title":"UI/UX Design Principles","description":"Master Figma, user research, and interaction design.","tags":"design, ui-ux, figma","price":29,"rating":4.6},
    {"title":"Flutter Mobile Apps","description":"Cross-platform mobile development with Flutter and Dart.","tags":"mobile, flutter, dart","price":59,"rating":4.2},
    {"title":"Go Backend Development","description":"Build scalable APIs and microservices with Go.","tags":"backend, go, api, programming","price":44,"rating":4.4},
    {"title":"Docker & Kubernetes","description":"Containerize and orchestrate your applications.","tags":"devops, docker, kubernetes","price":54,"rating":4.7},
    {"title":"PostgreSQL Deep Dive","description":"SQL, indexing, query optimization, and database design.","tags":"database, sql, postgresql","price":34,"rating":4.1},
    {"title":"Cybersecurity Essentials","description":"Ethical hacking, network security, and penetration testing.","tags":"security, ethical-hacking, cybersecurity","price":69,"rating":4.9},
    {"title":"Game Dev with Unity","description":"Create 2D and 3D games using Unity and C#.","tags":"game-dev, unity, csharp","price":49,"rating":4.0},
    {"title":"Machine Learning A-Z","description":"Supervised and unsupervised learning with scikit-learn.","tags":"python, machine-learning, data-science","price":79,"rating":4.5},
    {"title":"Responsive Web Design","description":"HTML, CSS, Flexbox, Grid, and mobile-first design.","tags":"frontend, web, css, beginner","price":19,"rating":4.3},
]


@app.route("/seed_courses")
@login_required
def seed_courses():
    """Insert sample courses with varied hashtags for testing the tag filter."""
    existing = db.execute("SELECT COUNT(*) AS cnt FROM courses")
    if existing and existing[0]["cnt"] > 3:
        # Already seeded — just redirect
        return redirect("/courses")

    uid = session["user_id"]
    for c in SEED_COURSES:
        db.execute(
            "INSERT INTO courses (owner_id, title, description, tags, price, rating) VALUES (?, ?, ?, ?, ?, ?)",
            uid, c["title"], c["description"], c["tags"], c["price"], c["rating"]
        )
    return redirect("/courses")
