"""Dashboard route — renders the user's home page with their locked plan if any."""

from app import app, db, login_required
from flask import render_template, redirect, session
from routes.plans import get_locked_plan

@app.route("/")
@login_required
def index():
    """Render the dashboard with the user's name, locked plan, and available courses."""
    user_id = session["user_id"]
    user = db.execute("SELECT name FROM users WHERE id = ?", user_id)
    username = user[0]["name"] if user else "User"
    locked_plan = get_locked_plan(user_id)
    courses = db.execute("SELECT id, title, description, tags FROM courses ORDER BY id DESC LIMIT 50")
    return render_template("index.html", username=username, locked_plan=locked_plan, courses=courses)
