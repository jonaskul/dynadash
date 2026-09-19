"""Shared fixtures.

Every test here is hermetic: no InfluxDB, no Tibber, no network. Where a test
needs the database to be unreachable, that is the point being tested — the
backend has to keep the Pulse feed alive through it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator, Iterator

import pytest

import auth
import influx_store
import tibber_db


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the settings/session database at a throwaway file.

    Both modules bind DB_PATH at import time, so both have to be redirected,
    and the caches that would otherwise carry state between tests are reset.
    """
    db = tmp_path / "test.db"
    monkeypatch.setattr(tibber_db, "DB_PATH", db)
    monkeypatch.setattr(auth, "DB_PATH", db)
    monkeypatch.setattr(auth, "_configured", None)
    monkeypatch.setattr(auth, "_valid_tokens", {})
    monkeypatch.setattr(auth, "_failures", {})
    tibber_db.init_db()
    auth.init()
    yield db


@pytest.fixture
def fast_scrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the KDF cost so password tests are not dominated by hashing.

    The cost parameters are stored in each hash, so lowering them here still
    exercises the real code path end to end.
    """
    monkeypatch.setattr(auth, "_SCRYPT_N", 1 << 8)


@pytest.fixture
async def write_queue(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Run the InfluxDB write queue for the duration of a test.

    There is no InfluxDB behind it, so the drain task's writes fail — which is
    exactly the condition most of these tests are about.

    The linger is shortened so tests do not spend seconds waiting for a batch to
    be flushed; `test_linger_is_short_enough_to_stay_near_real_time` covers the
    real value.
    """
    monkeypatch.setattr(influx_store, "_LINGER", 0.05)
    await influx_store.start()
    try:
        yield
    finally:
        # Let any in-flight write finish first. Cancelling a task that is inside
        # asyncio.to_thread leaves the executor future dangling, and the test
        # event loop then never finishes closing.
        await asyncio.sleep(0.3)
        await influx_store.stop()
