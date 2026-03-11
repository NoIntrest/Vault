"""
routes/budget.py — Monthly budget goals and spending progress.

Routes:  GET  /api/budget?month=YYYY-MM        → fetch saved goals
         POST /api/budget                       → save / replace goals
         GET  /api/budget/progress?month=       → goals joined with actual spending
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from auth import login_required
from database import get_cursor

logger = logging.getLogger(__name__)

budget_bp = Blueprint("budget", __name__)


# ── Routes ─────────────────────────────────────────────────────────────────────

@budget_bp.route("/api/budget", methods=["GET"])
@login_required
def get_budget():
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    try:
        with get_cursor(dict_cursor=True) as (_, cur):
            cur.execute(
                "SELECT category, goal_amount, currency FROM budgets "
                "WHERE user_id=%s AND month=%s",
                (session["user_id"], month)
            )
            rows = cur.fetchall()
        return jsonify([{**dict(r), "goal_amount": float(r["goal_amount"])} for r in rows])
    except Exception as e:
        logger.error("get_budget error: %s", e)
        return jsonify({"error": "Could not load budget goals."}), 500


@budget_bp.route("/api/budget", methods=["POST"])
@login_required
def save_budget():
    data     = request.json or {}
    month    = data.get("month", datetime.now().strftime("%Y-%m"))
    goals    = data.get("goals", [])   # [{category, goal_amount, currency}]
    currency = data.get("currency", "USD")

    if not isinstance(goals, list):
        return jsonify({"error": "goals must be a list"}), 400

    try:
        with get_cursor() as (_, cur):
            # Delete then re-insert — clean replace for the whole month
            cur.execute(
                "DELETE FROM budgets WHERE user_id=%s AND month=%s",
                (session["user_id"], month)
            )
            for g in goals:
                cat    = g.get("category", "").strip()
                amount = g.get("goal_amount", 0)
                try:
                    amount = float(amount)
                except (TypeError, ValueError):
                    amount = 0
                if cat and amount > 0:
                    cur.execute(
                        "INSERT INTO budgets (user_id, month, category, goal_amount, currency) "
                        "VALUES (%s,%s,%s,%s,%s)",
                        (session["user_id"], month, cat, amount, currency)
                    )
        return jsonify({"success": True})
    except Exception as e:
        logger.error("save_budget error: %s", e)
        return jsonify({"error": "Could not save budget goals."}), 500


@budget_bp.route("/api/budget/progress")
@login_required
def get_budget_progress():
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    try:
        with get_cursor(dict_cursor=True) as (_, cur):
            cur.execute("SELECT currency FROM users WHERE id=%s", (session["user_id"],))
            user = cur.fetchone()

            cur.execute(
                "SELECT category, goal_amount FROM budgets "
                "WHERE user_id=%s AND month=%s",
                (session["user_id"], month)
            )
            goals = {r["category"]: float(r["goal_amount"]) for r in cur.fetchall()}

            # Actual spending per category
            cur.execute(
                "SELECT category, SUM(amount) AS total FROM transactions "
                "WHERE user_id=%s AND type='expense' AND date LIKE %s "
                "GROUP BY category",
                (session["user_id"], f"{month}%")
            )
            spent = {r["category"]: float(r["total"]) for r in cur.fetchall()}

            # Income and total expenses (for savings goal)
            cur.execute(
                "SELECT type, SUM(amount) AS total FROM transactions "
                "WHERE user_id=%s AND date LIKE %s GROUP BY type",
                (session["user_id"], f"{month}%")
            )
            totals = {r["type"]: float(r["total"]) for r in cur.fetchall()}

    except Exception as e:
        logger.error("get_budget_progress error: %s", e)
        return jsonify({"error": "Could not load progress."}), 500

    income   = totals.get("income", 0)
    expenses = totals.get("expense", 0)

    rows = []
    for cat, goal in goals.items():
        # Savings is a special computed category: income − expenses
        actual = (income - expenses) if cat == "Savings" else spent.get(cat, 0)
        rows.append({"category": cat, "goal": goal, "actual": round(actual, 2)})

    return jsonify({
        "progress":         rows,
        "display_currency": (user["currency"] or "USD") if user else "USD",
    })
