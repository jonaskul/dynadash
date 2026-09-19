"""The watchdog and the loops it supervises.

Nothing watches the watchdog, so the thing most worth testing is that it cannot
die — an exception escaping it would take the self-healing with it and leave the
failure it exists to catch in place.
"""

from __future__ import annotations

import asyncio

import pytest

import main
from poller import Poller


async def test_watchdog_keeps_going_when_a_check_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "WATCHDOG_INTERVAL", 0.01)
    calls = 0

    def boom() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("check exploded")

    monkeypatch.setattr(main.pulse_manager, "ensure_running", boom)

    task = asyncio.create_task(main._watchdog())
    await asyncio.sleep(0.2)
    still_running = not task.done()
    task.cancel()

    assert still_running, "the watchdog died on a raising check"
    assert calls >= 2, f"the watchdog stopped iterating after {calls} call(s)"


async def test_watchdog_checks_every_supervised_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "WATCHDOG_INTERVAL", 0.01)
    seen: set[str] = set()

    for name, target in [
        ("influx", main.influx_store),
        ("poller", main.poller),
        ("pulse", main.pulse_manager),
        ("rest", main.rest_poller),
    ]:
        monkeypatch.setattr(
            target, "ensure_running", lambda n=name: seen.add(n)
        )
    monkeypatch.setattr(main.auth, "purge_expired", lambda: seen.add("sessions"))

    task = asyncio.create_task(main._watchdog())
    await asyncio.sleep(0.1)
    task.cancel()

    assert seen == {"influx", "poller", "pulse", "rest", "sessions"}


async def test_maintenance_loop_survives_an_unreachable_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "MAINTENANCE_INTERVAL", 0.01)
    attempts = 0

    def boom() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("influxdb is down")

    monkeypatch.setattr(main.influx_maintenance, "ensure_rollup_task", boom)

    task = asyncio.create_task(main._maintenance())
    await asyncio.sleep(0.2)
    still_running = not task.done()
    task.cancel()

    assert still_running, "the maintenance loop died on a failed run"
    assert attempts >= 2


async def test_dead_dynalite_poller_is_restarted() -> None:
    p = Poller()

    async def dies() -> None:
        raise RuntimeError("boom")

    p._loop = dies  # type: ignore[method-assign]
    p._task = asyncio.create_task(p._loop())
    await asyncio.sleep(0.05)
    assert p._task.done()

    p._loop = lambda: asyncio.sleep(3600)  # type: ignore[method-assign]
    p.ensure_running()

    assert not p._task.done()
    p.stop()


async def test_stopping_the_poller_clears_its_handle() -> None:
    """ensure_running has to be able to tell stopped from running."""
    p = Poller()
    p._loop = lambda: asyncio.sleep(3600)  # type: ignore[method-assign]
    p.ensure_running()
    assert p._task is not None

    p.stop()

    assert p._task is None
