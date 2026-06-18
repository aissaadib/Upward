from app import app, login_required, db
from flask import render_template, session,redirect, jsonify, request
import json
from services.profile import build_profile_summary

@app.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    if request.method == "POST":
        raw = request.form.get("answers", "{}")
        try:
            answers = json.loads(raw)
        except:
            return render_template("onboarding.html", error=True)

        session["user_answers"] = answers
        session["career_profile"] = build_profile_summary(answers)
        session.modified = True

        user_id = session["user_id"]
        db.execute("UPDATE users SET locked = False WHERE id = ?", user_id)

        return redirect("/advice")
    return render_template("onboarding.html")