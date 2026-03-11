"""
app.py — Flask application factory and entry point.

Wires together all blueprints and serves the single-page frontend.

Run locally:
    python app.py

On Render (via Procfile):
    gunicorn app:app --workers 1 --bind 0.0.0.0:$PORT
"""

import logging

from flask import Flask, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import SECRET_KEY, DEBUG
from database import init_db

# ── Blueprints ─────────────────────────────────────────────────────────────────
from auth import auth_bp
from routes.settings import settings_bp
from routes.transactions import transactions_bp
from routes.budget import budget_bp
from routes.ai_chat import ai_bp

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)

# ── App factory ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = SECRET_KEY

# ── Rate limiter ───────────────────────────────────────────────────────────────
# In-memory storage is safe because Procfile sets --workers 1.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# Apply per-route rate limits to auth endpoints
limiter.limit("10 per minute")(auth_bp.view_functions["signup"])
limiter.limit("15 per minute")(auth_bp.view_functions["login"])
limiter.limit("30 per minute")(ai_bp.view_functions["ai_chat"])

# ── Register blueprints ────────────────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(transactions_bp)
app.register_blueprint(budget_bp)
app.register_blueprint(ai_bp)


# ── Frontend ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    print("\n💰 Vault — Money Manager v5")
    print("═" * 44)
    print("  Open:  http://localhost:5000")
    print("  Stop:  Ctrl+C")
    print("  DB:    PostgreSQL (persistent)")
    print("═" * 44 + "\n")
    app.run(debug=DEBUG, port=5000)
