from app import app, db, login_required
from flask import render_template, session


@app.route("/courses")
@login_required
def courses():
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"

    course_list = db.execute("SELECT id, title, tags, content, price FROM courses ORDER BY id DESC")

    return render_template("courses.html", username=username, courses=course_list)