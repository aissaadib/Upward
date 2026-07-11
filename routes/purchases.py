"""Purchases routes — Stripe subscriptions, webhook handler, and access helpers."""

from app import app, db, login_required, STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET
from flask import render_template, request, session, redirect, jsonify
import stripe
from datetime import datetime, timezone, timedelta


def has_course_access(user_id, course_id):
    """Return True if the user has active access to the given course.

    Checks: course ownership (lifetime), owners table (free subscriptions with expiry),
            purchases table (Stripe subscriptions with expiry).
    """
    course = db.execute("SELECT owner_id, price FROM courses WHERE id = ?", course_id)
    if not course:
        return False
    course = course[0]
    # Owner always has access
    if course["owner_id"] == user_id:
        return True
    now_iso = datetime.now(timezone.utc).isoformat()
    # Check owners table (free subscriptions — 1 month expiry)
    sub = db.execute(
        "SELECT ending_date FROM owners WHERE course_id = ? AND user_id = ?",
        course_id, user_id
    )
    if sub:
        end = sub[0].get("ending_date")
        if end and end > now_iso:
            return True
        # Expired — clean up silently
        if end and end <= now_iso:
            db.execute("DELETE FROM owners WHERE course_id = ? AND user_id = ?",
                       course_id, user_id)
    # Check purchases table (Stripe subscriptions — monthly expiry)
    purchase = db.execute(
        "SELECT current_period_end FROM purchases WHERE course_id = ? AND user_id = ? AND status = 'completed'",
        course_id, user_id
    )
    if purchase:
        end = purchase[0].get("current_period_end")
        if end is None:
            return True  # Legacy one-time purchase (never expires)
        if end and end > now_iso:
            return True
    return False


def get_period_end(subscription):
    """Extract current_period_end from a Stripe subscription object as ISO string."""
    period = subscription.get("current_period_end")
    if period:
        return datetime.fromtimestamp(period, tz=timezone.utc).isoformat()
    return (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()


@app.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    """Create a Stripe Checkout Session for monthly subscription to a course."""
    if not STRIPE_SECRET_KEY:
        return jsonify({"error": "Stripe is not configured. Contact admin."}), 500

    course_id = request.form.get("course_id")
    if not course_id:
        return jsonify({"error": "Missing course_id"}), 400

    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404
    course = course[0]

    # Already has active access?
    if has_course_access(session["user_id"], int(course_id)):
        return jsonify({"error": "You already have access to this course"}), 400

    if course["price"] == 0:
        return jsonify({"error": "Free courses cannot be purchased through checkout"}), 400

    stripe_price_id = course.get("stripe_price_id", "").strip()
    if not stripe_price_id:
        return jsonify({
            "error": "This course is not yet configured for monthly billing. Contact admin."
        }), 500

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{"price": stripe_price_id, "quantity": 1}],
            mode="subscription",
            success_url=request.host_url.rstrip("/") + "/checkout/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url.rstrip("/") + "/checkout/cancel",
            metadata={
                "course_id": str(course_id),
                "user_id": str(session["user_id"]),
            },
        )
        return jsonify({"url": checkout_session.url})
    except stripe.error.StripeError as e:
        return jsonify({"error": f"Stripe error: {e.user_message or str(e)}"}), 500


@app.route("/checkout/success")
@login_required
def checkout_success():
    """Show payment success page and verify the subscription session."""
    session_id = request.args.get("session_id")
    verified = False

    if session_id and STRIPE_SECRET_KEY:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            metadata = checkout_session.metadata or {}
            course_id = metadata.get("course_id")
            user_id = metadata.get("user_id")

            if (checkout_session.payment_status == "paid"
                    and user_id and str(session["user_id"]) == user_id
                    and course_id):

                existing = db.execute(
                    "SELECT 1 FROM purchases WHERE stripe_session_id = ?", session_id
                )
                if not existing:
                    sub_id = checkout_session.get("subscription")
                    period_end = None
                    if sub_id:
                        try:
                            sub = stripe.Subscription.retrieve(sub_id)
                            period_end = get_period_end(sub)
                        except stripe.error.StripeError:
                            period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

                    db.execute(
                        """INSERT INTO purchases
                           (user_id, course_id, stripe_session_id, subscription_id,
                            payment_intent, amount, currency, status, current_period_end)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?)""",
                        session["user_id"],
                        course_id,
                        session_id,
                        sub_id,
                        checkout_session.payment_intent,
                        checkout_session.amount_total,
                        checkout_session.currency or "mad",
                        period_end,
                    )
                verified = True
        except stripe.error.StripeError:
            pass

    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"

    return render_template(
        "payment_success.html",
        username=username,
        verified=verified
    )


@app.route("/checkout/cancel")
@login_required
def checkout_cancel():
    """Show payment cancellation page."""
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    return render_template("checkout_cancel.html", username=username)


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events for subscription lifecycle."""
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    if not STRIPE_WEBHOOK_SECRET or not sig_header:
        return jsonify({"error": "Webhook secret not configured"}), 400

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        return jsonify({"error": str(e)}), 400

    event_type = event.get("type")

    # Initial subscription creation
    if event_type == "checkout.session.completed":
        checkout_session = event["data"]["object"]
        metadata = checkout_session.get("metadata", {})
        course_id = metadata.get("course_id")
        user_id = metadata.get("user_id")

        if not course_id or not user_id:
            return jsonify({"error": "Missing metadata"}), 400

        existing = db.execute(
            "SELECT 1 FROM purchases WHERE stripe_session_id = ?",
            checkout_session.get("id")
        )
        if existing:
            return jsonify({"status": "already recorded"}), 200

        if checkout_session.get("payment_status") == "paid":
            sub_id = checkout_session.get("subscription")
            period_end = None
            if sub_id:
                try:
                    sub = stripe.Subscription.retrieve(sub_id)
                    period_end = get_period_end(sub)
                except stripe.error.StripeError:
                    period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

            db.execute(
                """INSERT INTO purchases
                   (user_id, course_id, stripe_session_id, subscription_id,
                    payment_intent, amount, currency, status, current_period_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', ?)""",
                int(user_id),
                int(course_id),
                checkout_session.get("id"),
                sub_id,
                checkout_session.get("payment_intent"),
                checkout_session.get("amount_total"),
                checkout_session.get("currency") or "mad",
                period_end,
            )

    # Monthly renewal — extend access by another month
    elif event_type == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        sub_id = invoice.get("subscription")
        if sub_id:
            try:
                sub = stripe.Subscription.retrieve(sub_id)
                period_end = get_period_end(sub)
            except stripe.error.StripeError:
                period_end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

            db.execute(
                "UPDATE purchases SET current_period_end = ?, status = 'completed' WHERE subscription_id = ?",
                period_end, sub_id
            )

    # Subscription cancelled/expired — revoke access
    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        sub = event["data"]["object"]
        sub_id = sub.get("id")
        status = sub.get("status")

        if sub_id and status == "incomplete_expired":
            db.execute(
                "UPDATE purchases SET status = 'expired' WHERE subscription_id = ?",
                sub_id
            )
        elif sub_id and status == "canceled":
            db.execute(
                "UPDATE purchases SET status = 'expired' WHERE subscription_id = ?",
                sub_id
            )
        elif sub_id and status == "past_due":
            period_end = get_period_end(sub)
            db.execute(
                "UPDATE purchases SET current_period_end = ?, status = 'past_due' WHERE subscription_id = ?",
                period_end, sub_id
            )

    return jsonify({"status": "ok"}), 200
