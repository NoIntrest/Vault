"""
routes/ai_chat.py — AI budget advisor powered by Groq.

Route:  POST /api/ai-chat
"""

import logging

import requests as req
from flask import Blueprint, jsonify, request, session

from auth import login_required
from config import GROQ_API_KEY, GROQ_MODEL
from database import get_cursor

logger = logging.getLogger(__name__)

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/api/ai-chat", methods=["POST"])
@login_required
def ai_chat():
    data         = request.json or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "No message provided"}), 400
    if not GROQ_API_KEY:
        return jsonify({"error": "no_key"}), 200

    try:
        with get_cursor(dict_cursor=True) as (_, cur):
            cur.execute("SELECT currency FROM users WHERE id=%s", (session["user_id"],))
            user = cur.fetchone()
            cur.execute(
                "SELECT type, amount, currency, category, note, date "
                "FROM transactions WHERE user_id=%s ORDER BY date DESC LIMIT 50",
                (session["user_id"],)
            )
            txs = cur.fetchall()
    except Exception as e:
        logger.error("ai_chat DB error: %s", e)
        return jsonify({"error": "Could not load your data."}), 500

    currency = (user["currency"] or "USD") if user else "USD"
    tx_summary = "\n".join([
        f"- {t['date']} | {t['type'].upper()} | {t['currency'] or currency}{float(t['amount']):.2f} "
        f"| {t['category']} | {t['note'] or ''}"
        for t in txs
    ]) or "No transactions yet."

    income_total  = sum(float(t["amount"]) for t in txs if t["type"] == "income")
    expense_total = sum(float(t["amount"]) for t in txs if t["type"] == "expense")

    system_prompt = (
        f"You are Vault AI, a friendly and insightful personal finance advisor.\n"
        f"The user's preferred currency is {currency}.\n"
        f"Recent transactions (last 50):\n{tx_summary}\n\n"
        f"Summary: income={currency}{income_total:.2f}, "
        f"expenses={currency}{expense_total:.2f}, "
        f"balance={currency}{income_total - expense_total:.2f}\n\n"
        f"Give practical, specific, actionable advice based on THEIR data. "
        f"Be warm but direct. Keep responses concise (3-5 sentences) unless asked for detail. "
        f"Use {currency} for all amounts."
    )

    try:
        response = req.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model":      GROQ_MODEL,
                "max_tokens": 500,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
            },
            timeout=30,
        )
        if response.status_code != 200:
            err = response.json().get("error", {}).get("message", "Groq API error")
            return jsonify({"error": err}), 400
        reply = response.json()["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})
    except Exception as e:
        logger.error("ai_chat groq error: %s", e)
        return jsonify({"error": "AI request failed. Please try again."}), 500
