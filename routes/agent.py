"""Agent route — AI career chatbot with persistent chat history."""

from app import app, db, groq_client, login_required, check_rate_limit, _ddl
from flask import render_template, session, jsonify, Response, stream_with_context, request
from routes.plans import get_locked_plan
import json
import time


def init_db():
    """Create the chat_messages table if it does not exist."""
    db.execute(_ddl("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
init_db()


def build_system_prompt():
    """Build a system prompt with user profile and plan data for the career agent."""
    profile = session.get("career_profile", "No profile available.")
    user_id = session["user_id"]

    plan_info = ""
    locked = get_locked_plan(user_id)
    if locked:
        basic = locked.get("basic", {})
        extended = locked.get("extended", {})
        plan_info = f"""
SELECTED PATH: {basic.get("title", "N/A")}
CATEGORY: {basic.get("category", "N/A")}
FIT: {basic.get("fit", "N/A")}
OUTCOME: {basic.get("outcome", "N/A")}
"""

        phases = extended.get("phases", [])
        if phases:
            plan_info += "\nMONTH-BY-MONTH PLAN:\n"
            for ph in phases:
                plan_info += f"  Month {ph.get('month')}: {ph.get('title', '')} - {ph.get('focus', '')}\n"

        skills = extended.get("skills_to_build", [])
        if skills:
            plan_info += "\nSKILLS TO BUILD:\n"
            for s in skills:
                plan_info += f"  - {s.get('skill', '')} ({s.get('priority', '')})\n"

        courses = extended.get("courses", [])
        if courses:
            plan_info += "\nRECOMMENDED COURSES:\n"
            for c in courses:
                plan_info += f"  - {c.get('name', '')} ({c.get('provider', '')})\n"

    return f"""You are Upward, a focused career advisor assistant. You have full access to this user's profile and career plan.

USER PROFILE:
{profile}

USER'S CAREER PLAN:
{plan_info}

RULES:
1. Only answer questions related to the user's career, skills, education, job search, learning path, or the plan above.
2. If the user asks something off-topic (unrelated to their career or the plan), politely apologize and redirect: "I'm here to help with your career journey. Let me know if you have questions about your plan, skills, or next steps."
3. Keep answers concise and practical — under 300 words.
4. Reference their profile and plan when giving advice.
5. Be encouraging but honest. Do not give false hope.
6. Suggest specific actions they can take based on their plan."""


@app.route("/agent")
@login_required
def agent():
    """Render the AI career agent chat page."""
    locked_plan = get_locked_plan(session["user_id"])
    if not locked_plan:
        return render_template("agent.html", username="User", locked=False)
    user = db.execute("SELECT name FROM users WHERE id = ?", session["user_id"])
    username = user[0]["name"] if user else "User"
    return render_template("agent.html", username=username, locked=True)


@app.route("/api/chat_history", methods=["GET"])
@login_required
def get_chat_history():
    """Return the user's chat message history (latest 100)."""
    rows = db.execute(
        "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id ASC LIMIT 100",
        session["user_id"]
    )
    return jsonify({"messages": rows})


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    """Stream an AI chat response, save messages to history."""
    data = request.get_json()
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "No prompt"}), 400

    user_id = session["user_id"]
    if not check_rate_limit(f"ai:chat:{user_id}", max_attempts=30, window=3600):
        return jsonify({"error": "Chat rate limit exceeded. Please wait before sending more messages."}), 429

    # Save user message
    db.execute(
        "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
        user_id, "user", prompt
    )

    # Build conversation history from DB (last 30 messages for context)
    history_rows = db.execute(
        "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 30",
        user_id
    )
    history_rows.reverse()

    messages = [{"role": "system", "content": build_system_prompt()}]
    for row in history_rows:
        messages.append({"role": row["role"], "content": row["content"]})

    def generate():
        full_response = ""
        try:
            stream = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                stream=True,
                timeout=30.0
            )
            for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    full_response += content
                    yield content
        except Exception as e:
            yield f"\n\nSorry, I hit an error: {e}"

        # Save AI response after streaming completes
        if full_response.strip():
            db.execute(
                "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
                user_id, "assistant", full_response.strip()
            )

    return Response(stream_with_context(generate()), mimetype="text/plain")


@app.route("/api/chat/clear", methods=["POST"])
@login_required
def clear_chat():
    """Delete all chat messages for the current user."""
    db.execute("DELETE FROM chat_messages WHERE user_id = ?", session["user_id"])
    return jsonify({"ok": True})
