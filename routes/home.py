"""Dashboard route — renders the landing page with user's locked plan if logged in."""

from app import app, db
from flask import render_template, session
from routes.plans import get_locked_plan

@app.route("/")
def index():
    """Render the landing page. Shows locked plan if user is logged in."""
    username = None
    locked_plan = None
    if "user_id" in session:
        user_id = session["user_id"]
        user = db.execute("SELECT name FROM users WHERE id = ?", user_id)
        username = user[0]["name"] if user else "User"
        locked_plan = get_locked_plan(user_id)
    return render_template("index.html", username=username, locked_plan=locked_plan)
