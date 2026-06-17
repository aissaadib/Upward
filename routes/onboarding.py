from app import app
import json
from services.profile import build_profile_summary
from flask import Flask, redirect, render_template, request, session, jsonify
@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if session.get("user_id") is None:
        return redirect("/login")
    if request.method == "POST":
        raw = request.form.get("answers", "{}")
        try:
            answers = json.loads(raw)
        except:
            return render_template("onboarding.html", error=True)

        session["user_answers"] = answers
        session["career_profile"] = build_profile_summary(answers)
        session.modified = True 

        return redirect("/advice")
    return render_template("onboarding.html")