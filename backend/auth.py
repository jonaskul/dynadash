"""Shared-password authentication for the dashboard.

The API controls lighting and heating and exposes a self-update endpoint that
runs privileged commands, so it must not be reachable by everything on the
network. One household password is the right granularity — there are no
per-user permissions to express — held as an scrypt hash, never in the clear.

Sessions live in the same SQLite file as the rest of the settings so they
survive a restart; an update must not log the whole house out. Only the hash of
each session token is stored, so the table itself grants nobody access.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
import time
from typing import Optional

from tibber_db import DB_PATH, get_setting, set_setting

logger = logging.getLogger(__name__)

COOKIE_NAME = "dynadash_session"
MIN_PASSWORD_LENGTH = 10
SESSION_TTL = 30 * 24 * 3600  # 30 days

_PASSWORD_KEY = "auth_password_hash"

# n=2**14 costs about 100ms on the small boxes this runs on: slow enough to
# make guessing expensive, quick enough for a login. Larger values exceed
# OpenSSL's default 32MB memory cap, so maxmem is always passed explicitly.
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024

# A shared password with unlimited guesses is barely a password, so failures
# are counted per client address and lock that address out for a while.
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300.0
_failures: dict[str, tuple[int, float]] = {}

# Both of these are read on every single API request, and /api/energy/status is
# polled every two seconds. Caching them keeps the guard off the disk entirely
# in the common case; both are invalidated wherever they are written.
_configured: Optional[bool] = None
_valid_tokens: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def init() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )
    purge_expired()
    if not is_configured():
        logger.warning(
            "No dashboard password is set — the API is refusing every request "
            "until one is created in the browser."
        )


def is_configured() -> bool:
    """True once a dashboard password has been set."""
    global _configured
    if _configured is None:
        _configured = bool(get_setting(_PASSWORD_KEY))
    return _configured


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password. Blocking (~100ms) — call via ``asyncio.to_thread``."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
        maxmem=_SCRYPT_MAXMEM,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash. Blocking — use a worker thread.

    The cost parameters come from the stored hash, so hashes written by an
    earlier version keep verifying after the parameters here are raised.
    """
    try:
        scheme, n, r, p, salt_hex, want_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        want = bytes.fromhex(want_hex)
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(want),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError) as exc:
        logger.warning("Stored password hash is unusable: %s", exc)
        return False
    return secrets.compare_digest(digest, want)


def stored_hash() -> Optional[str]:
    return get_setting(_PASSWORD_KEY)


def set_password_hash(hashed: str) -> None:
    global _configured
    set_setting(_PASSWORD_KEY, hashed)
    _configured = True


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session() -> str:
    """Create a session and return its token. The token is never stored."""
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires = now + SESSION_TTL
    th = _token_hash(token)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO sessions(token_hash, created_at, expires_at) VALUES(?,?,?)",
            (th, now, expires),
        )
    _valid_tokens[th] = expires
    return token


def validate_session(token: Optional[str]) -> bool:
    if not token:
        return False
    th = _token_hash(token)
    now = int(time.time())

    cached = _valid_tokens.get(th)
    if cached is not None:
        if cached > now:
            return True
        _valid_tokens.pop(th, None)
        return False

    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT expires_at FROM sessions WHERE token_hash=?", (th,)
            ).fetchone()
    except sqlite3.Error as exc:
        logger.warning("Session lookup failed: %s", exc)
        return False
    if not row or row[0] <= now:
        return False
    _valid_tokens[th] = row[0]
    return True


def delete_session(token: Optional[str]) -> None:
    if not token:
        return
    th = _token_hash(token)
    _valid_tokens.pop(th, None)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (th,))


def delete_all_sessions() -> None:
    """Invalidate every session — used when the password changes."""
    _valid_tokens.clear()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM sessions")


def purge_expired() -> None:
    now = int(time.time())
    for th, expires in list(_valid_tokens.items()):
        if expires <= now:
            del _valid_tokens[th]
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------

def lockout_remaining(client: str) -> float:
    """Seconds this client must wait before trying again; 0 when allowed."""
    entry = _failures.get(client)
    if entry is None:
        return 0.0
    count, last = entry
    if count < MAX_FAILURES:
        return 0.0
    remaining = LOCKOUT_SECONDS - (time.monotonic() - last)
    if remaining <= 0:
        del _failures[client]
        return 0.0
    return remaining


def record_failure(client: str) -> None:
    count, _ = _failures.get(client, (0, 0.0))
    _failures[client] = (count + 1, time.monotonic())


def clear_failures(client: str) -> None:
    _failures.pop(client, None)
