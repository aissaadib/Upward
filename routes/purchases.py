"""Purchases routes — Stripe subscriptions, webhook handler, and access helpers."""

from app import app, db, login_required, csrf_required, STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET
from flask import render_template, request, session, redirect, jsonify
import stripe
from datetime import datetime, timezone, timedelta


def sync_stripe_price(course_id):
    """Create or update a Stripe product + monthly recurring price for a course.

    Called automatically when a course is saved with price > 0.
    Sets courses.stripe_price_id so the checkout flow can use it.
    """
    if not STRIPE_SECRET_KEY:
        return
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course or course[0]["price"] <= 0:
        return
    course = course[0]
    existing_id = (course.get("stripe_price_id") or "").strip()

    try:
        # If a price ID exists, try to update the product name
        if existing_id:
            try:
                price = stripe.Price.retrieve(existing_id)
                stripe.Product.modify(price.product, name=course["title"])
            except stripe.error.StripeError:
                existing_id = ""  # stale ID — create fresh
        # No valid price ID — create product + monthly price
        if not existing_id:
            product = stripe.Product.create(name=course["title"])
            price = stripe.Price.create(
                product=product.id,
                unit_amount=int(course["price"] * 100),
                currency="mad",
                recurring={"interval": "month"},
            )
            db.execute("UPDATE courses SET stripe_price_id = ? WHERE id = ?",
                       price.id, course_id)
    except stripe.error.StripeError:
        pass  # silently fail — admin can retry


PLAN_PRICE_ID = None

def get_plan_price_id():
    """Get or create the Stripe price ID for the 130 MAD Extended Plan one-time purchase."""
    global PLAN_PRICE_ID
    if not STRIPE_SECRET_KEY:
        return None
    if PLAN_PRICE_ID:
        return PLAN_PRICE_ID
    try:
        name = "Extended Career Plan"
        products = stripe.Product.search(query=f"name:'{name}' AND active:'true'", limit=1)
        if products.data:
            product = products.data[0]
        else:
            product = stripe.Product.create(name=name)
        prices = stripe.Price.list(product=product.id, active=True, limit=1, type="one_time")
        if prices.data:
            PLAN_PRICE_ID = prices.data[0].id
        else:
            price = stripe.Price.create(
                product=product.id,
                unit_amount=13000,
                currency="mad",
            )
            PLAN_PRICE_ID = price.id
    except stripe.error.StripeError:
        return None
    return PLAN_PRICE_ID


@app.route("/create-plan-checkout", methods=["POST"])
@login_required
@csrf_required
def create_plan_checkout():
    """Create a Stripe Checkout Session for the 130 MAD Extended Plan."""
    if not STRIPE_SECRET_KEY:
        return jsonify({"error": "Stripe is not configured. Contact admin."}), 500

    price_id = get_plan_price_id()
    if not price_id:
        return jsonify({"error": "Could not set up plan pricing. Try again later."}), 500

    user_id = session["user_id"]
    existing = db.execute("SELECT plan_access FROM users WHERE id = ?", user_id)
    if existing and existing[0].get("plan_access"):
        return jsonify({"error": "You already have access to the Extended Plan."}), 400

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{"price": price_id, "quantity": 1}],
            mode="payment",
            success_url=request.host_url.rstrip("/") + "/checkout/plan-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=request.host_url.rstrip("/") + "/advice",
            metadata={
                "plan_purchase": "true",
                "user_id": str(user_id),
            },
        )
        return jsonify({"url": checkout_session.url})
    except stripe.error.StripeError as e:
        return jsonify({"error": f"Stripe error: {e.user_message or str(e)}"}), 500


@app.route("/checkout/plan-success")
@login_required
def checkout_plan_success():
    """Show plan payment success page."""
    session_id = request.args.get("session_id")
    granted = False

    if session_id and STRIPE_SECRET_KEY:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            metadata = checkout_session.metadata or {}
            user_id = metadata.get("user_id")

            if (checkout_session.payment_status == "paid"
                    and user_id and str(session["user_id"]) == user_id
                    and metadata.get("plan_purchase") == "true"):

                existing = db.execute(
                    "SELECT 1 FROM purchases WHERE stripe_session_id = ?", session_id
                )
                if not existing:
                    db.execute(
                        """INSERT INTO purchases
                           (user_id, course_id, stripe_session_id, payment_intent, amount, currency, status)
                           VALUES (?, ?, ?, ?, ?, ?, 'completed')""",
                        session["user_id"], -1, session_id,
                        checkout_session.payment_intent,
                        checkout_session.amount_total,
                        checkout_session.currency or "mad",
                    )
                db.execute("UPDATE users SET plan_access = 1 WHERE id = ?", session["user_id"])
                granted = True
        except stripe.error.StripeError:
            pass

    return render_template("payment_success.html",
                           username=session.get("username", "User"),
                           verified=granted,
                           is_plan=True)


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
        "SELECT booking_date, ending_date FROM owners WHERE course_id = ? AND user_id = ?",
        course_id, user_id
    )
    if sub:
        end = sub[0].get("ending_date")
        start = sub[0].get("booking_date")
        if end and end > now_iso:
            return True
        # Legacy record (ending_date == booking_date) — lifetime access
        if end and start and end[:19] == start[:19]:
            return True
        # Truly expired — clean up
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
        sync_stripe_price(int(course_id))
        course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
        if course:
            stripe_price_id = (course[0].get("stripe_price_id") or "").strip()
    if not stripe_price_id:
        return jsonify({
            "error": "Could not create Stripe price. Try editing the course in Admin first."
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
        plan_purchase = metadata.get("plan_purchase")

        if not user_id:
            return jsonify({"error": "Missing metadata"}), 400

        existing = db.execute(
            "SELECT 1 FROM purchases WHERE stripe_session_id = ?",
            checkout_session.get("id")
        )
        if existing:
            return jsonify({"status": "already recorded"}), 200

        if checkout_session.get("payment_status") == "paid":
            if plan_purchase == "true":
                db.execute(
                    "UPDATE users SET plan_access = 1 WHERE id = ?",
                    int(user_id)
                )
                db.execute(
                    """INSERT INTO purchases
                       (user_id, course_id, stripe_session_id, payment_intent, amount, currency, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'completed')""",
                    int(user_id), -1, checkout_session.get("id"),
                    checkout_session.get("payment_intent"),
                    checkout_session.get("amount_total"),
                    checkout_session.get("currency") or "mad",
                )
            elif course_id:
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
