"""Admin routes — course CRUD and purchase management."""

from app import app, db, login_required, admin_required, STRIPE_PUBLISHABLE_KEY
from flask import render_template, request, session, redirect
from routes.purchases import sync_stripe_price


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    """Admin dashboard with course stats."""
    course_count = db.execute("SELECT COUNT(*) AS c FROM courses")[0]["c"]
    user_count = db.execute("SELECT COUNT(*) AS c FROM users")[0]["c"]
    purchase_count = db.execute("SELECT COUNT(*) AS c FROM purchases")[0]["c"]
    total_revenue = db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM purchases WHERE status = 'completed'")[0]["total"]

    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "Admin"

    return render_template(
        "admin.html",
        username=username,
        course_count=course_count,
        user_count=user_count,
        purchase_count=purchase_count,
        total_revenue=total_revenue,
        stripe_configured=bool(STRIPE_PUBLISHABLE_KEY),
    )


@app.route("/admin/courses")
@login_required
@admin_required
def admin_courses():
    """List all courses for admin management."""
    courses = db.execute("SELECT * FROM courses ORDER BY id DESC")
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "Admin"
    return render_template("admin_courses.html", username=username, courses=courses)


@app.route("/admin/courses/add", methods=["POST"])
@login_required
@admin_required
def admin_add_course():
    """Add a new course (admin only)."""
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price", "0").strip()
    tags = request.form.get("tags", "").strip()
    stripe_price_id = request.form.get("stripe_price_id", "").strip()

    if not title or not description:
        return redirect("/admin/courses?error=Title and description required")

    try:
        price = int(price)
    except ValueError:
        price = 0

    db.execute(
        "INSERT INTO courses (owner_id, title, description, price, tags, rating, stripe_price_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        session["user_id"], title, description, max(price, 0), tags, None, stripe_price_id
    )
    course_id = db.execute("SELECT MAX(id) AS id FROM courses")[0]["id"]
    sync_stripe_price(course_id)
    return redirect("/admin/courses?msg=Course added")


@app.route("/admin/courses/<int:course_id>/edit", methods=["POST"])
@login_required
@admin_required
def admin_edit_course(course_id):
    """Edit an existing course (admin only)."""
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return redirect("/admin/courses?error=Course not found")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price", "0").strip()
    tags = request.form.get("tags", "").strip()
    stripe_price_id = request.form.get("stripe_price_id", "").strip()

    if not title or not description:
        return redirect(f"/admin/courses?error=Title and description required")

    try:
        price = int(price)
    except ValueError:
        price = 0

    # Don't overwrite stripe_price_id if not sent (auto-generated)
    if not stripe_price_id:
        existing = db.execute("SELECT stripe_price_id FROM courses WHERE id = ?", course_id)
        if existing and existing[0].get("stripe_price_id"):
            stripe_price_id = existing[0]["stripe_price_id"]

    db.execute(
        "UPDATE courses SET title = ?, description = ?, price = ?, tags = ?, stripe_price_id = ? WHERE id = ?",
        title, description, max(price, 0), tags, stripe_price_id, course_id
    )
    sync_stripe_price(course_id)
    return redirect("/admin/courses?msg=Course updated")


@app.route("/admin/courses/<int:course_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_course(course_id):
    """Delete a course and its lessons (admin only)."""
    course = db.execute("SELECT * FROM courses WHERE id = ?", course_id)
    if not course:
        return redirect("/admin/courses?error=Course not found")

    db.execute("DELETE FROM lessons WHERE course_id = ?", course_id)
    db.execute("DELETE FROM owners WHERE course_id = ?", course_id)
    db.execute("DELETE FROM purchases WHERE course_id = ?", course_id)
    db.execute("DELETE FROM courses WHERE id = ?", course_id)
    return redirect("/admin/courses?msg=Course deleted")


@app.route("/admin/purchases")
@login_required
@admin_required
def admin_purchases():
    """View all purchases with user and course details."""
    purchases = db.execute("""
        SELECT p.*, u.name AS user_name, u.email, c.title AS course_title
        FROM purchases p
        JOIN users u ON p.user_id = u.id
        JOIN courses c ON p.course_id = c.id
        ORDER BY p.id DESC
    """)
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "Admin"
    return render_template("admin_purchases.html", username=username, purchases=purchases)
