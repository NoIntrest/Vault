"""
auth.py — Password helpers, login_required decorator, and auth Blueprint.

Routes:  POST /api/signup
         POST /api/login
         POST /api/logout
         GET  /api/me
"""

import hashlib
import logging
from functools import wraps

import bcrypt
import psycopg2
from flask import Blueprint, jsonify, request, session

from config import GROQ_API_KEY, GROQ_MODEL
from database import get_cursor
from limiter import limiter

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, hashed: str) -> bool:
    """Supports both bcrypt and legacy SHA-256 hashes."""
    if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
        try:
            return bcrypt.checkpw(pw.encode(), hashed.encode())
        except Exception:
            return False
    return hashlib.sha256(pw.encode()).hexdigest() == hashed


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Routes ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/api/signup", methods=["POST"])
@limiter.limit("10 per minute")
def signup():
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    try:
        with get_cursor(dict_cursor=True) as (conn, cur):
            try:
                cur.execute(
                    "INSERT INTO users (email, password) VALUES (%s, %s)",
                    (email, hash_pw(password))
                )
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                return jsonify({"error": "Email already registered"}), 409
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
        session["user_id"] = user["id"]
        session["email"]   = email
        return jsonify({"success": True, "email": email, "currency": "USD"})
    except Exception as e:
        logger.error("signup error: %s", e)
        return jsonify({"error": "Could not create account. Please try again."}), 500


@auth_bp.route("/api/login", methods=["POST"])
@limiter.limit("15 per minute")
def login():
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    try:
        with get_cursor(dict_cursor=True) as (conn, cur):
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
            if not user or not check_pw(password, user["password"]):
                return jsonify({"error": "Invalid email or password"}), 401
            # Upgrade legacy SHA-256 hash to bcrypt on first login
            if not (user["password"].startswith("$2b$") or user["password"].startswith("$2a$")):
                cur.execute(
                    "UPDATE users SET password=%s WHERE id=%s",
                    (hash_pw(password), user["id"])
                )
        session["user_id"] = user["id"]
        session["email"]   = user["email"]
        return jsonify({"success": True, "email": user["email"], "currency": user["currency"] or "USD"})
    except Exception as e:
        logger.error("login error: %s", e)
        return jsonify({"error": "Login failed. Please try again."}), 500


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@auth_bp.route("/api/me")
def me():
    if "user_id" not in session:
        return jsonify({"logged_in": False})
    try:
        with get_cursor(dict_cursor=True) as (_, cur):
            cur.execute(
                "SELECT email, currency FROM users WHERE id=%s",
                (session["user_id"],)
            )
            user = cur.fetchone()
        return jsonify({
            "logged_in":   True,
            "email":       user["email"],
            "currency":    user["currency"] or "USD",
            "groq_ready":  bool(GROQ_API_KEY),
            "groq_model":  GROQ_MODEL,
        })
    except Exception as e:
        logger.error("me error: %s", e)
        return jsonify({"error": "Could not load user data."}), 500
