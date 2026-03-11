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

from config import SECRET_KEY, DEBUG
from database import init_db
from limiter import limiter

# ── Blueprints ─────────────────────────────────────────────────────────────────
from auth import auth_bp
from routes.settings import settings_bp
from routes.transactions import transactions_bp
from routes.budget import budget_bp
from routes.ai_chat import ai_bp
from routes.csv_io import csv_bp

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = SECRET_KEY

# Bind the shared limiter instance to this app
limiter.init_app(app)

# ── Register blueprints ────────────────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(transactions_bp)
app.register_blueprint(budget_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(csv_bp)


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
