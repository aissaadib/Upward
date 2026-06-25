from app import app, db, groq_client, login_required
from flask import render_template, request, session, redirect
from services.ai import parse_ai_json
import PyPDF2
import re

@app.route("/test", methods=["GET", "POST"])
@login_required
def test():
    if request.method == "GET":
        return render_template("test.html", username=session.get("username", "User"), loading=False)

    # Handle POST - resume upload
    resume_file = request.files.get("resume")
    major = request.form.get("major", "").strip()

    if not resume_file or not major:
        return render_template("test.html", username=session.get("username", "User"), error="Please upload a resume and specify your teaching field.", loading=False)

    # Read resume content
    try:
        if resume_file.filename.endswith('.pdf'):
            # Extract text from PDF
            pdf_reader = PyPDF2.PdfReader(resume_file)
            resume_text = ""
            for page in pdf_reader.pages:
                resume_text += page.extract_text()
        elif resume_file.filename.endswith('.txt'):
            # Read text file
            resume_text = resume_file.read().decode('utf-8')
        else:
            return render_template("test.html", username=session.get("username", "User"), error="Only PDF and TXT files are supported.", loading=False)
    except Exception as e:
        print(f"Error reading resume: {e}")
        return render_template("test.html", username=session.get("username", "User"), error="Failed to read resume file.", loading=False)

    if not resume_text or len(resume_text.strip()) < 50:
        return render_template("test.html", username=session.get("username", "User"), error="Resume appears to be empty or too short.", loading=False)

    # Show loading state
    return render_template("test.html", username=session.get("username", "User"), loading=True, resume_text=resume_text, major=major)


@app.route("/rate_resume", methods=["POST"])
@login_required
def rate_resume():
    resume_text = request.form.get("resume_text", "")
    major = request.form.get("major", "").strip()

    if not resume_text or not major:
        return {"error": "Missing resume or major"}, 400

    # AI prompt to rate teaching capability based on 9 categories
    prompt = f"""You are an expert evaluator of teaching capability. Analyze this resume and rate the person's ability to teach or provide instruction in the field of "{major}".

RESUME:
{resume_text[:3000]}

Rate the person on a scale of 1-5 for EACH of these categories:

1. Subject mastery - Do they deeply understand the topic? Can they answer follow-up questions?
2. Ability to explain clearly - Can they simplify complex ideas without confusing people?
3. Communication skills - Speaking, writing, listening, adapting language to the student's level.
4. Practical experience - Have they actually used the skills in real projects/work?
5. Patience & empathy - Do they stay calm when students struggle?
6. Teaching experience - Tutoring, mentoring, workshops, TA roles, etc.
7. Proof of results - Testimonials, student outcomes, portfolio, previous successes.
8. Passion/enthusiasm - Do they genuinely enjoy teaching?
9. Credibility - Degrees, certifications, awards.

Respond ONLY with valid JSON (no markdown):
{{
  "subject_mastery": 4.25,
  "explanation_ability": 4.5,
  "communication_skills": 4.0,
  "practical_experience": 3.75,
  "patience_empathy": 4.25,
  "teaching_experience": 3.0,
  "proof_of_results": 3.5,
  "passion_enthusiasm": 4.0,
  "credibility": 3.75,
  "reasoning": "Brief explanation of the overall assessment",
  "strengths": ["2-3 key strengths for teaching"],
  "areas_for_improvement": ["1-2 areas to improve"]
}}

Rules:
- Each rating must be a number between 1.0 and 5.0
- Be objective and fair based on resume content
- If information is missing, rate conservatively (2.5-3.0)
- Consider both formal education and practical experience
- For teaching experience, look for mentoring, tutoring, leadership roles"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0
        )
        raw = response.choices[0].message.content.strip()
        rating_data = parse_ai_json(raw)

        if not isinstance(rating_data, dict):
            raise ValueError("Invalid rating response")

        # Calculate weighted teaching score
        # Teaching Score = 40% explanation ability + 30% subject mastery + 20% patience/communication + 10% credentials
        explanation = float(rating_data.get("explanation_ability", 2.5))
        subject = float(rating_data.get("subject_mastery", 2.5))
        patience = float(rating_data.get("patience_empathy", 2.5))
        communication = float(rating_data.get("communication_skills", 2.5))
        credibility = float(rating_data.get("credibility", 2.5))

        # Calculate weighted score
        weighted_score = (
            (explanation * 0.40) +
            (subject * 0.30) +
            ((patience + communication) / 2 * 0.20) +
            (credibility * 0.10)
        )

        # Clamp rating between 1 and 5
        rating = max(1.0, min(5.0, weighted_score))

        # Add calculated rating to rating_data
        rating_data["rating"] = round(rating, 1)
        rating_data["weighted_breakdown"] = {
            "explanation_ability": round(explanation * 0.40, 2),
            "subject_mastery": round(subject * 0.30, 2),
            "patience_communication": round(((patience + communication) / 2 * 0.20), 2),
            "credibility": round(credibility * 0.10, 2)
        }

        # Update user rating in database
        user_id = session["user_id"]
        db.execute(
            "UPDATE users SET rating = ? WHERE id = ?",
            rating, user_id
        )

        # Store rating data in session for customization page
        session["teaching_rating"] = rating_data
        session["teaching_major"] = major

        return redirect("/customize_course")

    except Exception as e:
        print(f"AI rating error: {e}")
        # Fallback to default rating
        user_id = session["user_id"]
        db.execute("UPDATE users SET rating = 2.5 WHERE id = ?", user_id)
        session["teaching_major"] = major
        return redirect("/customize_course")


@app.route("/customize_course", methods=["GET"])
@login_required
def customize_course():
    rating_data = session.get("teaching_rating", {})
    major = session.get("teaching_major", "Unknown")
    
    # Get user's current rating from database
    user_id = session["user_id"]
    user = db.execute("SELECT rating FROM users WHERE id = ?", user_id)
    rating = user[0]["rating"] if user else 2.5
    
    return render_template(
        "customize_course.html",
        username=session.get("username", "User"),
        rating=rating,
        major=major,
        rating_data=rating_data
    )


@app.route("/create_course", methods=["POST"])
@login_required
def create_course():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price", "0")
    tags = request.form.get("tags", "").strip()

    if not title or not description:
        return render_template("customize_course.html", 
            username=session.get("username", "User"),
            error="Title and description are required",
            rating=session.get("teaching_rating", {}).get("rating", 2.5),
            major=session.get("teaching_major", "Unknown"),
            rating_data=session.get("teaching_rating", {}))

    try:
        price = float(price)
    except ValueError:
        price = 0.0

    owner_id = session["user_id"]
    
    # Insert course into database
    db.execute(
        """INSERT INTO courses (owner_id, title, description, tags, price)
           VALUES (?, ?, ?, ?, ?)""",
        owner_id, title, description, tags, price
    )

    return redirect("/courses")
