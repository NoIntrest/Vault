"""
database.py — PostgreSQL connection pool, shared cursor helper, and schema init.

All other modules import `get_cursor` from here; none should open raw
psycopg2 connections themselves.
"""

import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# ── Connection pool ────────────────────────────────────────────────────────────
# Render free PostgreSQL allows ~5 concurrent connections.
# We cap at 3 to leave headroom for migrations / psql sessions.
_pool: ThreadedConnectionPool | None = None


def get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. "
                "Add a PostgreSQL database in Render and link it to this service."
            )
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        _pool = ThreadedConnectionPool(1, 3, dsn=url)
    return _pool


@contextmanager
def get_cursor(dict_cursor: bool = False):
    """
    Context manager that borrows a connection from the pool, yields
    (conn, cursor), commits on success, rolls back on error, and always
    returns the connection to the pool.

    Usage:
        with get_cursor(dict_cursor=True) as (conn, cur):
            cur.execute(...)
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=factory) if factory else conn.cursor()
        try:
            yield conn, cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        pool.putconn(conn)


# ── Database init ──────────────────────────────────────────────────────────────

def init_db():
    """Create / migrate tables. Safe to run on every startup."""
    with get_cursor() as (conn, cur):
        # Users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         SERIAL PRIMARY KEY,
                email      TEXT UNIQUE NOT NULL,
                password   TEXT NOT NULL,
                currency   TEXT DEFAULT 'USD',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration: drop the unused anthropic_key column if present
        cur.execute("""
            ALTER TABLE users DROP COLUMN IF EXISTS anthropic_key
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                type       TEXT NOT NULL,
                amount     NUMERIC(14,2) NOT NULL,
                currency   TEXT DEFAULT 'USD',
                category   TEXT,
                note       TEXT,
                date       TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                month       TEXT NOT NULL,
                category    TEXT NOT NULL,
                goal_amount NUMERIC(14,2) NOT NULL,
                currency    TEXT DEFAULT 'USD',
                UNIQUE (user_id, month, category)
            )
        """)
