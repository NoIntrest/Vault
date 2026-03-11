"""
config.py — Environment variables and app-wide constants.

All configuration is read from env vars here so no other file
needs to touch os.environ directly.
"""

import os
import logging

logger = logging.getLogger(__name__)

# ── Secret key ─────────────────────────────────────────────────────────────────
# Render sets RENDER automatically.  If we're deployed there and SECRET_KEY is
# missing we refuse to start rather than silently use a guessable dev key.
_SECRET = os.environ.get("SECRET_KEY")
if not _SECRET:
    if os.environ.get("RENDER"):
        raise RuntimeError(
            "SECRET_KEY environment variable must be set in production. "
            "Add it in Render → Environment."
        )
    _SECRET = "vault-local-dev-key-DO-NOT-USE-IN-PROD"
    logger.warning("WARNING: using insecure dev secret key — set SECRET_KEY in production")

SECRET_KEY   = _SECRET
DATABASE_URL = os.environ.get("DATABASE_URL", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
DEBUG        = os.environ.get("DEBUG", "false").lower() == "true"
