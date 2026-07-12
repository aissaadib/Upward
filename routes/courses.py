"""Courses routes — list, view, subscribe/unsubscribe, delete, and PayPal payments."""

from app import app, db, login_required, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_API_BASE
from flask import render_template, session, redirect, jsonify, request
from collections import Counter
from datetime import datetime, timezone, timedelta
import requests
import base64


def paypal_headers():
    """Return auth headers for PayPal REST API calls."""
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        return None
    token = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def init_db():
    """Create the courses and owners tables if they do not exist."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            title TEXT,
            description TEXT,
            tags TEXT,
            price INTEGER,
            rating REAL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            course_id INTEGER,
            user_id INTEGER,
            booking_date TEXT,
            ending_date TEXT
        )
    """)
    try:
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_owners_unique ON owners (course_id, user_id)")
    except Exception:
        pass
init_db()


def get_all_tags(course_list):
    """Extract unique tags and their counts from a list of course dicts."""
    all_tags = []
    for c in course_list:
        if c.get("tags"):
            for t in c["tags"].split(","):
                tag = t.strip().lower()
                if tag:
                    all_tags.append(tag)
    counts = Counter(all_tags)
    unique = sorted(counts.keys(), key=lambda t: (-counts[t], t))
    return unique, dict(counts)


@app.route("/courses")
@login_required
def courses():
    """Render course listing page with tag filter."""
    user = db.execute("SELECT name, locked, admin FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    locked = user[0]["locked"] if user else 0
    is_admin = bool(user[0].get("admin")) if user else False

    course_list = db.execute("SELECT * FROM courses ORDER BY id DESC")
    for c in course_list:
        c["is_owner"] = (c["owner_id"] == session["user_id"])

    owned = db.execute("SELECT course_id FROM owners WHERE user_id = ?", session["user_id"])
    owned_ids = {r["course_id"] for r in owned}

    purchased = db.execute("SELECT course_id FROM purchases WHERE user_id = ? AND status = 'completed'", session["user_id"])
    purchased_ids = {r["course_id"] for r in purchased}

    all_tags, _ = get_all_tags(course_list)
    return render_template("courses.html", username=username, courses=course_list, locked=locked, all_tags=all_tags, owned_ids=owned_ids, purchased_ids=purchased_ids, is_admin=is_admin)


@app.route("/delete_course/<int:course_id>", methods=["POST"])
@login_required
def delete_course(course_id):
    """Delete a course and its lessons, verifying the current user is the owner."""
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return "Not found", 404
    if course[0]["owner_id"] != session["user_id"]:
        return "Unauthorized", 403
    db.execute("DELETE FROM lessons WHERE course_id = ?", course_id)
    db.execute("DELETE FROM courses WHERE id = ?", course_id)
    return "OK"


@app.route("/toggle_subscription/<int:course_id>", methods=["POST"])
@login_required
def toggle_subscription(course_id):
    """Subscribe or unsubscribe from a course (toggle)."""
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return "Not found", 404
    existing = db.execute("SELECT * FROM owners WHERE course_id = ? AND user_id = ?",
                          course_id, session["user_id"])
    if existing:
        db.execute("DELETE FROM owners WHERE course_id = ? AND user_id = ?",
                   course_id, session["user_id"])
        return jsonify({"subscribed": False})
    else:
        now = datetime.now(timezone.utc)
        ends = now + timedelta(days=30)
        try:
            db.execute("INSERT INTO owners (course_id, user_id, booking_date, ending_date) VALUES (?, ?, ?, ?)",
                       course_id, session["user_id"], now.isoformat(), ends.isoformat())
        except Exception:
            return jsonify({"subscribed": False}), 409
        return jsonify({"subscribed": True})


@app.route("/create-paypal-order", methods=["POST"])
@login_required
def create_paypal_order():
    """Create a PayPal order and return the approval URL."""
    course_id = request.form.get("course_id")
    if not course_id:
        return jsonify({"error": "Missing course_id"}), 400

    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404

    # Already subscribed?
    existing = db.execute("SELECT * FROM owners WHERE course_id = ? AND user_id = ?",
                          course_id, session["user_id"])
    if existing:
        return jsonify({"error": "Already subscribed"}), 400

    price = float(course[0]["price"])

    headers = paypal_headers()
    if not headers:
        return jsonify({"error": "PayPal not configured. Contact admin."}), 500

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {"currency_code": "MAD", "value": f"{price:.2f}"},
            "custom_id": str(course_id),
            "description": course[0]["title"]
        }],
        "application_context": {
            "return_url": request.host_url.rstrip("/") + "/paypal-return",
            "cancel_url": request.host_url.rstrip("/") + "/courses",
            "user_action": "PAY_NOW",
            "brand_name": "Upward"
        }
    }

    resp = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders",
        json=payload,
        headers=headers
    )

    if resp.status_code not in (200, 201):
        return jsonify({"error": "PayPal API error", "details": resp.text}), 500

    order = resp.json()

    approval_url = None
    for link in order.get("links", []):
        if link["rel"] == "approve":
            approval_url = link["href"]
            break

    if not approval_url:
        return jsonify({"error": "No approval URL from PayPal"}), 500

    session["paypal_order_id"] = order["id"]
    session["paypal_course_id"] = int(course_id)

    return jsonify({"approval_url": approval_url})


@app.route("/paypal-return")
@login_required
def paypal_return():
    """PayPal redirects here after the user approves payment."""
    order_id = request.args.get("token")
    course_id = session.pop("paypal_course_id", None)
    session.pop("paypal_order_id", None)

    if not order_id or not course_id:
        return "Payment verification failed — missing order details.", 400

    headers = paypal_headers()
    if not headers:
        return "PayPal not configured", 500

    resp = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture",
        headers=headers
    )

    if resp.status_code not in (200, 201):
        return "Payment capture failed. Please contact support.", 500

    capture_data = resp.json()

    if capture_data.get("status") == "COMPLETED":
        now = datetime.now(timezone.utc)
        db.execute(
            "INSERT INTO owners (course_id, user_id, booking_date, ending_date) VALUES (?, ?, ?, ?)",
            course_id, session["user_id"], now.isoformat(), now.isoformat()
        )
        return render_template("payment_success.html", course_id=course_id)

    return "Payment not completed. Please try again.", 400
