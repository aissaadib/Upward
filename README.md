# Upward

A career guidance platform that helps students and young professionals identify the right path, build relevant skills, and make informed decisions about their future — personalized to where they are right now.

---

## Features

- **AI Career Advisor** — generates personalized career paths based on user profile and resume
- **Onboarding Questionnaire** — multi-step form that builds a detailed career profile
- **Course System** — browse, subscribe, and purchase courses with Stripe subscriptions
- **AI Chat Agent** — persistent chat with career context, streaming responses via Groq
- **Teaching Assessment** — AI evaluates resume across 9 dimensions and computes weighted readiness score
- **Course Creation** — users can create and manage their own courses with a WYSIWYG lesson editor
- **Admin Panel** — manage courses, view purchases, and track revenue
- **Profile Management** — update username, upload resume (PDF), change password
- **Email Verification** — 6-digit code sent via Gmail SMTP during registration
- **Authentication** — session-based with Flask-Session, password hashing via Werkzeug
- **Stripe Subscriptions** — monthly recurring payments with webhook lifecycle management
- **PayPal Legacy** — one-time payments (kept for backward compatibility)
- **Security** — CSRF protection, rate limiting, input validation, security headers

---

## Tech Stack

- **Backend:** Python, Flask, Flask-Session
- **Database:** SQLite via CS50 SQL
- **AI:** Groq Cloud (llama-3.1-8b-instant)
- **Payments:** Stripe (subscriptions) + PayPal (legacy)
- **Frontend:** HTML, CSS, JavaScript (no framework)
- **Auth:** Session-based with filesystem storage
- **Email:** Gmail SMTP via smtplib

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/aissaadib/Upward.git
cd Upward
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Copy the `.env` file and fill in your keys:

```env
GROQ_API_KEY=your_groq_api_key
SECRET_KEY=your_random_secret_key
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password

STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

ADMIN_EMAIL=your_admin_email@gmail.com
```

Required keys: `GROQ_API_KEY`, `SECRET_KEY` (app will not start without these).

### 4. Run locally

```bash
python app.py
```

Open `http://localhost:5000` in your browser.

---

## Project Structure

```
Upward/
├── app.py                  # Flask app entry, config, DB init, security infra
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (keys, secrets)
├── upward.db               # SQLite database
├── flask_session/          # Server-side session files
├── uploads/                # Uploaded resume PDFs (temporary)
├── routes/
│   ├── auth.py             # Login, register, verify, logout
│   ├── home.py             # Landing page
│   ├── onboarding.py       # Career profile questionnaire
│   ├── advice.py           # AI career suggestion generation
│   ├── plans.py            # Career plan select, extend, lock, view
│   ├── agent.py            # AI chat agent with streaming
│   ├── courses.py          # Course listing, subscribe, PayPal payments
│   ├── purchases.py        # Stripe checkout, webhooks, access control
│   ├── lessons.py          # Lesson CRUD, file extraction, WYSIWYG editor
│   ├── test.py             # Teaching readiness test, resume rating
│   ├── admin.py            # Admin dashboard, course/purchase management
│   └── profile.py          # Profile update, resume upload, password change
├── services/
│   ├── ai.py               # JSON parsing helpers for AI responses
│   └── profile.py          # Profile summary builder for AI context
├── static/                 # Extracted CSS per template (no framework)
│   ├── admin.css
│   ├── advice.css
│   ├── agent.css
│   ├── courses.css
│   ├── customize_course.css
│   ├── index.css
│   ├── plan_extend.css
│   ├── profile.css
│   ├── test.css
│   └── ... (one .css per template)
└── templates/              # Jinja2 HTML templates
    ├── login.html
    ├── register.html
    ├── verify.html
    ├── onboarding.html
    ├── index.html
    ├── courses.html
    ├── lessons.html
    ├── lesson_display.html
    ├── costumize_lessons.html
    ├── customize_course.html
    ├── profile.html
    ├── admin.html
    ├── admin_courses.html
    ├── admin_purchases.html
    ├── advice.html
    ├── plan.html
    ├── plan_extend.html
    ├── agent.html
    ├── test.html
    ├── payment_success.html
    └── checkout_cancel.html
```

---

## Security

- CSRF protection via signed tokens on all state-changing POST routes
- Rate limiting on login (5/min), registration (3/min), and AI endpoints (5-30/hr per user)
- File upload size limit (10 MB) with cleanup on parse failure
- Session cookies: `HttpOnly`, `SameSite=Lax`
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`
- DEBUG mode disabled in production
- Input length validation on all auth forms
- Generic error messages to prevent user enumeration
- Stripe webhook signature verification
- Parameterized SQL queries via CS50 SQL (no raw query construction)

---

## Deployment

**Start command:**
```
gunicorn app:app
```

Requires `SECRET_KEY` and `GROQ_API_KEY` environment variables to be set on the host.

---

## License

MIT
