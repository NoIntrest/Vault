"""
routes/transactions.py — Transaction CRUD and monthly summary.

Routes:  GET    /api/transactions?month=YYYY-MM
         POST   /api/transactions
         DELETE /api/transactions/<id>
         GET    /api/summary?month=YYYY-MM
"""

import logging
from datetime import datetime, date

from flask import Blueprint, jsonify, request, session

from auth import login_required
from database import get_cursor
from routes.settings import get_cached_rates

logger = logging.getLogger(__name__)

transactions_bp = Blueprint("transactions", __name__)


# ── Routes ─────────────────────────────────────────────────────────────────────

@transactions_bp.route("/api/transactions", methods=["GET"])
@login_required
def get_transactions():
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    try:
        with get_cursor(dict_cursor=True) as (_, cur):
            cur.execute(
                "SELECT * FROM transactions WHERE user_id=%s AND date LIKE %s ORDER BY date DESC, id DESC",
                (session["user_id"], f"{month}%")
            )
            rows = cur.fetchall()
        return jsonify([{**dict(r), "amount": float(r["amount"])} for r in rows])
    except Exception as e:
        logger.error("get_transactions error: %s", e)
        return jsonify({"error": "Could not load transactions."}), 500


@transactions_bp.route("/api/transactions", methods=["POST"])
@login_required
def add_transaction():
    data     = request.json or {}
    tx_type  = data.get("type")
    amount   = data.get("amount")
    currency = data.get("currency", "USD")
    category = data.get("category", "Other")
    note     = data.get("note", "")
    tx_date  = data.get("date", str(date.today()))

    if tx_type not in ("income", "expense"):
        return jsonify({"error": "Type must be income or expense"}), 400
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "Amount must be a positive number"}), 400

    try:
        with get_cursor() as (_, cur):
            cur.execute(
                "INSERT INTO transactions (user_id, type, amount, currency, category, note, date) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (session["user_id"], tx_type, amount, currency, category, note, tx_date)
            )
        return jsonify({"success": True})
    except Exception as e:
        logger.error("add_transaction error: %s", e)
        return jsonify({"error": "Could not save transaction."}), 500


@transactions_bp.route("/api/transactions/<int:tx_id>", methods=["DELETE"])
@login_required
def delete_transaction(tx_id):
    try:
        with get_cursor() as (_, cur):
            cur.execute(
                "DELETE FROM transactions WHERE id=%s AND user_id=%s",
                (tx_id, session["user_id"])
            )
        return jsonify({"success": True})
    except Exception as e:
        logger.error("delete_transaction error: %s", e)
        return jsonify({"error": "Could not delete transaction."}), 500


@transactions_bp.route("/api/summary")
@login_required
def summary():
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    try:
        with get_cursor(dict_cursor=True) as (_, cur):
            cur.execute("SELECT currency FROM users WHERE id=%s", (session["user_id"],))
            user = cur.fetchone()
            cur.execute(
                "SELECT type, category, amount, currency FROM transactions "
                "WHERE user_id=%s AND date LIKE %s",
                (session["user_id"], f"{month}%")
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.error("summary error: %s", e)
        return jsonify({"error": "Could not load summary."}), 500

    user_currency = (user["currency"] or "USD") if user else "USD"
    rates = get_cached_rates()

    def to_display(amount, from_cur):
        from_cur = from_cur or "USD"
        if not rates or from_cur == user_currency:
            return float(amount)
        usd = float(amount) / rates.get(from_cur, 1)
        return usd * rates.get(user_currency, 1)

    income   = sum(to_display(r["amount"], r["currency"]) for r in rows if r["type"] == "income")
    expenses = sum(to_display(r["amount"], r["currency"]) for r in rows if r["type"] == "expense")

    cats: dict[str, float] = {}
    for r in rows:
        if r["type"] == "expense":
            cats[r["category"]] = cats.get(r["category"], 0) + to_display(r["amount"], r["currency"])

    return jsonify({
        "income":           income,
        "expenses":         expenses,
        "balance":          income - expenses,
        "categories":       cats,
        "display_currency": user_currency,
    })
