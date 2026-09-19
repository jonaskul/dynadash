"""Password handling, sessions and login throttling."""

from __future__ import annotations

import time

import pytest

import auth

pytestmark = pytest.mark.usefixtures("temp_db", "fast_scrypt")


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def test_hash_is_salted_and_verifiable() -> None:
    first = auth.hash_password("correct-horse-battery")
    second = auth.hash_password("correct-horse-battery")

    assert first != second, "hashes are unsalted"
    assert "correct-horse-battery" not in first
    assert auth.verify_password("correct-horse-battery", first)
    assert auth.verify_password("correct-horse-battery", second)


def test_wrong_password_is_rejected() -> None:
    stored = auth.hash_password("correct-horse-battery")
    assert not auth.verify_password("Correct-horse-battery", stored)
    assert not auth.verify_password("", stored)
    assert not auth.verify_password("correct-horse-batter", stored)


@pytest.mark.parametrize(
    "stored",
    ["", "garbage", "scrypt$bad", "bcrypt$1$2$3$aa$bb", "scrypt$x$8$1$aa$bb"],
)
def test_an_unusable_stored_hash_denies_rather_than_crashes(stored: str) -> None:
    assert not auth.verify_password("anything-at-all", stored)


def test_cost_parameters_come_from_the_stored_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raising the cost must not lock anyone out of an older hash."""
    stored = auth.hash_password("correct-horse-battery")
    monkeypatch.setattr(auth, "_SCRYPT_N", 1 << 10)  # as if raised later
    assert auth.verify_password("correct-horse-battery", stored)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def test_session_round_trip() -> None:
    token = auth.create_session()
    assert auth.validate_session(token)


def test_unknown_and_empty_tokens_are_refused() -> None:
    auth.create_session()
    assert not auth.validate_session("forged-token")
    assert not auth.validate_session("")
    assert not auth.validate_session(None)


def test_raw_token_is_never_stored(temp_db) -> None:
    import sqlite3

    token = auth.create_session()
    with sqlite3.connect(temp_db) as conn:
        rows = conn.execute("SELECT token_hash FROM sessions").fetchall()

    assert rows
    assert all(token not in row[0] for row in rows), "session token stored verbatim"


def test_logout_invalidates_only_that_session() -> None:
    keep = auth.create_session()
    drop = auth.create_session()

    auth.delete_session(drop)

    assert not auth.validate_session(drop)
    assert auth.validate_session(keep)


def test_deleting_all_sessions_signs_everyone_out() -> None:
    tokens = [auth.create_session() for _ in range(3)]
    auth.delete_all_sessions()
    assert not any(auth.validate_session(t) for t in tokens)


def test_expired_sessions_are_refused_and_purged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "SESSION_TTL", -1)  # already expired on creation
    token = auth.create_session()

    assert not auth.validate_session(token)

    auth.purge_expired()
    assert not auth.validate_session(token)


def test_a_cached_session_is_not_trusted_past_its_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The in-memory cache must not outlive what it is caching."""
    token = auth.create_session()
    assert auth.validate_session(token)  # populates the cache

    auth._valid_tokens[auth._token_hash(token)] = int(time.time()) - 1

    assert not auth.validate_session(token)


# ---------------------------------------------------------------------------
# Configured state
# ---------------------------------------------------------------------------

def test_is_configured_follows_the_stored_password() -> None:
    assert not auth.is_configured()
    auth.set_password_hash(auth.hash_password("correct-horse-battery"))
    assert auth.is_configured()


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------

def test_lockout_after_repeated_failures() -> None:
    client = "10.0.0.9"
    for _ in range(auth.MAX_FAILURES - 1):
        auth.record_failure(client)
    assert auth.lockout_remaining(client) == 0

    auth.record_failure(client)
    assert auth.lockout_remaining(client) > 0


def test_lockout_is_per_client() -> None:
    for _ in range(auth.MAX_FAILURES):
        auth.record_failure("10.0.0.9")

    assert auth.lockout_remaining("10.0.0.9") > 0
    assert auth.lockout_remaining("10.0.0.10") == 0


def test_a_success_clears_the_count() -> None:
    client = "10.0.0.9"
    for _ in range(auth.MAX_FAILURES - 1):
        auth.record_failure(client)

    auth.clear_failures(client)

    for _ in range(auth.MAX_FAILURES - 1):
        auth.record_failure(client)
    assert auth.lockout_remaining(client) == 0


def test_lockout_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "LOCKOUT_SECONDS", 0.0)
    client = "10.0.0.9"
    for _ in range(auth.MAX_FAILURES):
        auth.record_failure(client)

    assert auth.lockout_remaining(client) == 0
