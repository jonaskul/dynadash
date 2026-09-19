"""Pulse liveness and reconnect behaviour.

The failure that kept losing the live feed was a task that was alive and going
nowhere: a half-open socket leaves the read loop waiting for a frame that never
comes, and nothing raises. A done() check cannot see that, so these tests cover
silence as well as death.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import influx_store
from tibber_pulse import _BACKOFF_MAX, _BACKOFF_MIN, _STALE_AFTER, TibberPulseManager


def _manager() -> TibberPulseManager:
    mgr = TibberPulseManager()
    mgr._token, mgr._home_id = "token", "home-1"
    return mgr


async def test_stale_but_alive_task_is_reconnected() -> None:
    mgr = _manager()
    stuck = asyncio.Event()

    async def never_returns(*_args: object) -> None:
        await stuck.wait()

    mgr._run = never_returns  # type: ignore[method-assign]
    mgr._task = asyncio.create_task(mgr._run())
    await asyncio.sleep(0)

    mgr._last_activity = time.monotonic() - (_STALE_AFTER + 1)
    original = mgr._task
    mgr.ensure_running()

    assert mgr._task is not original, "a silent task was left running"
    await asyncio.sleep(0.05)
    assert original.cancelled() or original.done()

    mgr.stop()
    stuck.set()


async def test_a_task_that_has_not_connected_yet_is_left_alone() -> None:
    """Before the socket opens there is no silence to measure."""
    mgr = _manager()
    stuck = asyncio.Event()

    async def waits(*_args: object) -> None:
        await stuck.wait()

    mgr._run = waits  # type: ignore[method-assign]
    mgr._task = asyncio.create_task(mgr._run())
    await asyncio.sleep(0)

    assert mgr._last_activity is None
    original = mgr._task
    mgr.ensure_running()

    assert mgr._task is original

    mgr.stop()
    stuck.set()


async def test_recently_active_task_is_left_alone() -> None:
    mgr = _manager()
    stuck = asyncio.Event()

    async def waits(*_args: object) -> None:
        await stuck.wait()

    mgr._run = waits  # type: ignore[method-assign]
    mgr._task = asyncio.create_task(mgr._run())
    await asyncio.sleep(0)

    mgr._last_activity = time.monotonic()
    original = mgr._task
    mgr.ensure_running()

    assert mgr._task is original, "reconnected a perfectly healthy feed"

    mgr.stop()
    stuck.set()


async def test_dead_task_is_restarted() -> None:
    mgr = _manager()

    async def dies(*_args: object) -> None:
        raise RuntimeError("boom")

    mgr._run = dies  # type: ignore[method-assign]
    mgr._task = asyncio.create_task(mgr._run())
    await asyncio.sleep(0.05)
    assert mgr._task.done()

    mgr._run = lambda *a: asyncio.sleep(3600)  # type: ignore[method-assign]
    mgr.ensure_running()

    assert not mgr._task.done()
    mgr.stop()


async def test_nothing_starts_without_credentials() -> None:
    mgr = TibberPulseManager()
    mgr.ensure_running()
    assert mgr._task is None


async def test_stop_clears_liveness_so_a_fresh_task_is_not_judged_stale() -> None:
    mgr = _manager()
    mgr._last_activity = time.monotonic() - 10_000
    mgr._connected = True

    mgr.stop()

    assert mgr._last_activity is None
    assert mgr._connected is False


async def test_data_age_tracks_our_own_clock_not_the_meter() -> None:
    """A meter with a drifting clock must not be able to hide a dead feed."""
    mgr = _manager()
    assert mgr.data_age is None

    mgr._last_ts = "2001-01-01T00:00:00.000+00:00"  # implausible meter timestamp
    assert mgr.data_age is None, "age was taken from the meter's timestamp"

    mgr._last_data = time.monotonic()
    assert mgr.data_age is not None and mgr.data_age < 1


async def test_backoff_floor_prevents_a_reconnect_storm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server that closes the stream instantly must not be hammered."""
    mgr = _manager()
    attempts = 0
    sleeps: list[float] = []

    async def closes_at_once(*_args: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts >= 4:
            raise asyncio.CancelledError

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    mgr._connect = closes_at_once  # type: ignore[method-assign]
    monkeypatch.setattr(asyncio, "sleep", record_sleep)

    with pytest.raises(asyncio.CancelledError):
        await mgr._run("token", "home-1")

    assert sleeps, "reconnected with no delay at all"
    assert min(sleeps) >= _BACKOFF_MIN
    assert max(sleeps) <= _BACKOFF_MAX
    # Repeated instant closes must back off rather than retry at a fixed rate.
    assert sleeps == sorted(sleeps) and sleeps[-1] > sleeps[0]


async def test_measurements_are_queued_not_written_inline(
    write_queue: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read loop must hand the point off without waiting for InfluxDB."""
    mgr = _manager()
    monkeypatch.setattr(influx_store, "write_points", lambda points: None)

    mgr._queue_pulse(
        "home-1",
        {
            "timestamp": "2026-09-19T12:00:00.000+02:00",
            "power": 4305.0,
            "currentL1": 6.1,
        },
    )

    assert influx_store.pending() == 1


async def test_a_malformed_measurement_is_skipped_not_fatal(
    write_queue: None,
) -> None:
    mgr = _manager()

    mgr._queue_pulse("home-1", {})  # no timestamp at all
    mgr._queue_pulse("home-1", {"timestamp": "not-a-timestamp", "power": 1})

    assert influx_store.pending() == 0
