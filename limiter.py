"""
limiter.py — Shared Flask-Limiter instance.

Defined here so route files can import and apply @limiter.limit()
decorators directly, without creating circular imports.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
