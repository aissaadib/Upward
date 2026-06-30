"""Profile builder — converts raw onboarding form answers into a structured string for AI prompts."""

def build_profile_summary(answers):
    """
    Convert onboarding questionnaire answers into a multi-line summary string
    suitable for injection into the AI prompt.
    """
    skills = answers.get("q2", [])
    if isinstance(skills, list):
        skills = ", ".join(skills) if skills else "None listed"

    lines = [
        f"Main field: {answers.get('field', 'Not provided')}",
        f"Current level: {answers.get('q0', 'Not provided')}",
        f"Education status: {answers.get('q1', 'Not provided')}",
        f"Existing tools and skills: {skills}",
        f"Strongest skill: {answers.get('q3', 'Not provided')}",
        f"Preferred type of work: {answers.get('q4', 'Not provided')}",
        f"Main goal: {answers.get('q5', 'Not provided')}",
        f"Biggest blocker: {answers.get('q6', 'Not provided')}",
        f"Monthly learning budget: {answers.get('q7', 'Not provided')}",
        f"Weekly time available: {answers.get('q8', 'Not provided')}",
        f"Timeline for results: {answers.get('q9', 'Not provided')}",
        f"Preferred work style: {answers.get('q10', 'Not provided')}",
        f"Career priority: {answers.get('q6a', 'Not provided')}",
        f"Preferred environment: {answers.get('q6b', 'Not provided')}",
        f"Risk tolerance: {answers.get('q6c', 'Not provided')}",
        f"5-year success vision: {answers.get('q6d', 'Not provided')}",
        f"Learning style: {answers.get('q8a', 'Not provided')}",
        f"Portfolio status: {answers.get('q8b', 'Not provided')}",
        f"Confidence level: {answers.get('q8c', 'Not provided')}",
        f"Country: {answers.get('q11', 'Not provided')}",
    ]

    # Append resume/portfolio text if the user uploaded one
    if answers.get('resume_text'):
        lines.append(f"\nResume/Portfolio content:\n{answers['resume_text'][:2000]}")

    return "\n".join(lines)
