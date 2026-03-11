"""
routes/settings.py — User preferences, live exchange rates, and health check.

Routes:  POST /api/settings
         GET  /api/rates
         GET  /api/health
"""

import logging
import time

import requests as req
from flask import Blueprint, jsonify, request, session

from auth import login_required
from database import get_cursor

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__)

# ── In-memory rates cache ──────────────────────────────────────────────────────
# Safe because Procfile forces --workers 1 (single process).
_rates_cache: dict = {"ts": 0, "data": {}}


def get_cached_rates() -> dict:
    """Return the most recently fetched rates dict (may be empty on first boot)."""
    return _rates_cache.get("data", {})


# ── Routes ─────────────────────────────────────────────────────────────────────

@settings_bp.route("/api/settings", methods=["POST"])
@login_required
def update_settings():
    data = request.json or {}
    if "currency" not in data:
        return jsonify({"error": "No settings provided"}), 400
    try:
        with get_cursor() as (_, cur):
            cur.execute(
                "UPDATE users SET currency=%s WHERE id=%s",
                (data["currency"], session["user_id"])
            )
        return jsonify({"success": True})
    except Exception as e:
        logger.error("settings error: %s", e)
        return jsonify({"error": "Could not save settings."}), 500


@settings_bp.route("/api/rates")
def get_rates():
    now = time.time()
    if now - _rates_cache["ts"] < 3600 and _rates_cache["data"]:
        return jsonify(_rates_cache["data"])
    try:
        r = req.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        rates = r.json().get("rates", {})
        _rates_cache["ts"]   = now
        _rates_cache["data"] = rates
        return jsonify(rates)
    except Exception as e:
        logger.warning("Exchange rate fetch failed: %s", e)
        fallback = {
            "USD": 1,    "EUR": 0.92, "GBP": 0.79, "INR": 83.1,  "JPY": 149.5,
            "CAD": 1.36, "AUD": 1.53, "CHF": 0.88, "CNY": 7.24,  "SGD": 1.34,
            "AED": 3.67, "MXN": 17.2, "BRL": 4.97, "KRW": 1325,  "THB": 35.1,
        }
        return jsonify(fallback)


@settings_bp.route("/api/health")
def health():
    from config import DATABASE_URL
    if not DATABASE_URL:
        return jsonify({"status": "error", "reason": "DATABASE_URL not set"}), 500
    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT 1")
        return jsonify({"status": "ok", "db": "connected"})
    except Exception as e:
        logger.error("health check failed: %s", e)
        return jsonify({"status": "error", "reason": "DB unreachable"}), 500
