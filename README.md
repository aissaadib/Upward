# Upward

A career guidance platform that helps students and young professionals identify the right path, build relevant skills, and make informed decisions about their future — personalized to where they are right now.

---

## Features

- Email-based registration with 6-digit verification code
- Secure password hashing with Werkzeug
- Session-based authentication with Flask-Session
- Animated onboarding landing page with swipeable info cards
- LinkedIn profile linking for personalized guidance
- Mobile-responsive UI across all pages

---

## Tech Stack

- **Backend:** Python, Flask, CS50 SQL
- **Database:** SQLite
- **Frontend:** HTML, CSS, Bootstrap 5
- **Auth:** Flask-Session, Werkzeug
- **Email:** Gmail SMTP via smtplib
- **Deployment:** Railway

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/aissaadib/Upward.git
cd Upward
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Set up the database

Make sure `upward.db` is in the root directory with a `users` table:

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT,
    hash TEXT,
    skill TEXT
);
```

### 4. Configure email

In `app.py`, replace the SMTP credentials with your own:

```python
SMTP_EMAIL = "your_email@gmail.com"
SMTP_PASSWORD = "your_app_password"  # Gmail App Password
```

To get a Gmail App Password: Google Account → Security → 2-Step Verification → App Passwords

### 5. Run locally

```bash
python app.py
```

Then open `http://localhost:5000` in your browser.

---

## Deployment

This project is deployed on [Railway](https://railway.app).

**Build command:**
```
pip install -r requirements.txt
```

**Start command:**
```
gunicorn app:app
```

---

## Project Structure

```
Upward/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── upward.db               # SQLite database
└── templates/
    ├── login.html
    ├── register.html
    ├── verify.html
    ├── onboarding.html
    └── index.html
```

---

## Roadmap

- AI Career Advisor with personalized roadmaps
- Future Risk Score based on automation trends
- Financial Resilience Score
- Skill Tree — visual map of what to learn next
- What-If Simulator for career scenarios
- Weekly Growth Plans
- Country and region salary comparisons
- Google OAuth login
- Portfolio analyzer (resume + GitHub + LinkedIn)

---

## License

MIT
