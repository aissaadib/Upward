"""Teaching-readiness test routes — resume upload, AI rating, and course creation."""

from app import app, db, groq_client, login_required, csrf_required, check_rate_limit
from flask import render_template, request, session, redirect
from services.ai import parse_ai_json
import PyPDF2
import re

@app.route("/test", methods=["GET", "POST"])
@login_required
@csrf_required
def test():
    """Render the resume upload page or process a submitted resume + teaching field."""
    if request.method == "GET":
        return render_template("test.html", username=session.get("username", "User"), loading=False)

    # Handle POST — resume upload
    resume_file = request.files.get("resume")
    major = request.form.get("major", "").strip()

    if not resume_file or not major:
        return render_template("test.html", username=session.get("username", "User"), error="Please upload a resume and specify your teaching field.", loading=False)

    # Extract text from the uploaded file
    try:
        if resume_file.filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(resume_file)
            resume_text = ""
            for page in pdf_reader.pages:
                resume_text += page.extract_text()
        elif resume_file.filename.endswith('.txt'):
            resume_text = resume_file.read().decode('utf-8')
        else:
            return render_template("test.html", username=session.get("username", "User"), error="Only PDF and TXT files are supported.", loading=False)
    except Exception as e:
        print(f"Error reading resume: {e}")
        return render_template("test.html", username=session.get("username", "User"), error="Failed to read resume file.", loading=False)

    if not resume_text or len(resume_text.strip()) < 50:
        return render_template("test.html", username=session.get("username", "User"), error="Resume appears to be empty or too short.", loading=False)

    # Show loading state before AI processes the data
    return render_template("test.html", username=session.get("username", "User"), loading=True, resume_text=resume_text, major=major)


@app.route("/rate_resume", methods=["POST"])
@login_required
@csrf_required
def rate_resume():
    """Call AI to evaluate the resume across 9 teaching-readiness dimensions and compute a weighted rating."""
    resume_text = request.form.get("resume_text", "")
    major = request.form.get("major", "").strip()

    if not resume_text or not major:
        return {"error": "Missing resume or major"}, 400

    user_id = session["user_id"]
    if not check_rate_limit(f"ai:rate:{user_id}", max_attempts=10, window=3600):
        return {"error": "Rate limit exceeded. Try again later."}, 429

    prompt = f"""You are an extremely strict evaluator of teaching readiness.

Your goal is NOT to estimate potential.
Your goal is to evaluate whether the candidate has demonstrated sufficient evidence to teach professionally.

FIELD:
{major}

RESUME:
{resume_text[:3000]}

Rate the candidate on these categories from 1.0 to 5.0.

Scoring scale:
1.0-1.9 = No evidence
2.0-2.9 = Weak or indirect evidence
3.0-3.9 = Solid evidence
4.0-4.4 = Strong documented evidence
4.5-5.0 = Exceptional evidence with measurable impact

IMPORTANT RULES:
- Never assume skills.
- Only score what is explicitly demonstrated.
- Missing information should lower scores.
- Ratings above 4.0 require strong evidence.
- Ratings above 4.5 require exceptional evidence.
- Most candidates should fall between 2.0 and 3.8.

Categories:
1. Subject mastery
2. Ability to explain clearly
3. Communication skills
4. Practical experience
5. Patience & empathy
6. Teaching experience
7. Proof of results
8. Passion/enthusiasm
9. Credibility

For explanation ability:
Require presentations, documentation writing, tutoring, workshops, mentoring, public speaking, etc.

For patience/empathy:
Require mentoring, volunteering, coaching, leadership, customer support or collaborative roles.

For proof of results:
Require testimonials, measurable impact, successful student outcomes, public reviews or portfolio achievements.

Respond ONLY with valid JSON:

{{
  "subject_mastery": 3.5,
  "explanation_ability": 3.0,
  "communication_skills": 3.0,
  "practical_experience": 3.5,
  "patience_empathy": 2.5,
  "teaching_experience": 2.0,
  "proof_of_results": 2.5,
  "passion_enthusiasm": 3.0,
  "credibility": 3.5,
  "reasoning": "Brief explanation",
  "strengths": ["strength 1", "strength 2"],
  "areas_for_improvement": ["improvement 1", "improvement 2"]
}}
"""

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

        # Extract individual dimension scores
        subject = float(rating_data.get("subject_mastery", 2.0))
        explanation = float(rating_data.get("explanation_ability", 2.0))
        communication = float(rating_data.get("communication_skills", 2.0))
        practical = float(rating_data.get("practical_experience", 2.0))
        patience = float(rating_data.get("patience_empathy", 2.0))
        teaching = float(rating_data.get("teaching_experience", 2.0))
        proof = float(rating_data.get("proof_of_results", 2.0))
        passion = float(rating_data.get("passion_enthusiasm", 2.0))
        credibility = float(rating_data.get("credibility", 2.0))

        # Clamp all values between 1.0 and 5.0
        scores = [
            subject, explanation, communication,
            practical, patience, teaching,
            proof, passion, credibility
        ]

        scores = [max(1.0, min(5.0, s)) for s in scores]

        (
            subject,
            explanation,
            communication,
            practical,
            patience,
            teaching,
            proof,
            passion,
            credibility
        ) = scores

        # Compute weighted base score using fixed weights per dimension
        weighted_score = (
            (subject * 0.22) +
            (explanation * 0.18) +
            (communication * 0.10) +
            (practical * 0.18) +
            (patience * 0.05) +
            (teaching * 0.15) +
            (proof * 0.07) +
            (passion * 0.03) +
            (credibility * 0.02)
        )

        # Apply penalties for weak evidence in critical dimensions
        penalty = 0

        if teaching <= 2:
            penalty += 0.4

        if proof <= 2:
            penalty += 0.3

        if practical <= 2:
            penalty += 0.3

        if subject <= 2.5:
            penalty += 0.6

        # Prevent inflated scores when subject mastery doesn't justify it
        if weighted_score > 4 and subject < 4:
            penalty += 0.4

        if weighted_score > 4 and teaching < 3:
            penalty += 0.4

        if weighted_score > 4.5 and proof < 4:
            penalty += 0.5

        # Compute final clamped rating
        rating = max(1.0, min(5.0, weighted_score - penalty))

        rating_data["rating"] = round(rating, 1)

        rating_data["weighted_breakdown"] = {
            "subject_mastery": round(subject * 0.22, 2),
            "explanation_ability": round(explanation * 0.18, 2),
            "communication_skills": round(communication * 0.10, 2),
            "practical_experience": round(practical * 0.18, 2),
            "patience_empathy": round(patience * 0.05, 2),
            "teaching_experience": round(teaching * 0.15, 2),
            "proof_of_results": round(proof * 0.07, 2),
            "passion_enthusiasm": round(passion * 0.03, 2),
            "credibility": round(credibility * 0.02),
            "penalty": round(penalty, 2)
        }

        session["teaching_rating"] = rating_data
        session["teaching_major"] = major

        return redirect("/customize_course")

    except Exception as e:
        print(f"AI rating error: {e}")

        # Fallback: set a default rating so the flow can continue
        session["teaching_rating"] = {"rating": 2.0}
        session["teaching_major"] = major

        return redirect("/customize_course")

@app.route("/customize_course", methods=["GET"])
@login_required
def customize_course():
    """Render the course creator page, passing the teaching rating from session."""
    rating_data = session.get("teaching_rating", {})
    major = session.get("teaching_major", "Unknown")
    
    rating = session.get("teaching_rating", {}).get("rating", 2.5)
    
    return render_template(
        "customize_course.html",
        username=session.get("username", "User"),
        rating=rating,
        major=major,
        rating_data=rating_data
    )


@app.route("/create_course", methods=["POST"])
@login_required
@csrf_required
def create_course():
    """Insert a new course into the database with title, description, price, tags, and AI rating."""
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
    
    course_rating = session.get("teaching_rating", {}).get("rating", 2.5)
    
    db.execute(
        """INSERT INTO courses (owner_id, title, description, tags, price, rating)
           VALUES (?, ?, ?, ?, ?, ?)""",
        owner_id, title, description, tags, price, course_rating
    )

    return redirect("/courses")
