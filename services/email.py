"""Email service — sends verification codes via SMTP (Gmail)."""

import os
import smtplib
from email.mime.text import MIMEText


SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"

def send_code(to_email, code):
    """Send a 6-digit verification code email via Gmail SMTP."""
    msg = MIMEText(
        f"Your Upward verification code is: {code}"
    )

    msg["Subject"] = "Upward - Verification Code"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email

    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(
            SMTP_EMAIL,
            to_email,
            msg.as_string()
        )
