"""The write queue exists so InfluxDB can never stall the Pulse read loop.

These tests pin that property down: handing off a point must not block, must not
raise, and must survive a database that is not answering.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from influxdb_client import Point

import influx_store


def _point(i: int) -> Point:
    return Point("test").field("i", i)


async def test_enqueue_does_not_block_when_overfilled(write_queue: None) -> None:
    start = time.monotonic()
    for i in range(influx_store._QUEUE_MAX + 250):
        influx_store.enqueue(_point(i))
    elapsed = time.monotonic() - start

    assert elapsed < 2.0, f"enqueue blocked for {elapsed:.2f}s"
    assert influx_store.pending() <= influx_store._QUEUE_MAX


async def test_full_queue_sheds_oldest_points(
    write_queue: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(influx_store, "_dropped", 0)
    for i in range(influx_store._QUEUE_MAX + 10):
        influx_store.enqueue(_point(i))

    # For a live feed the newest reading is the one worth keeping, so overflow
    # must drop from the front rather than refuse the new point.
    assert influx_store._dropped >= 10


async def test_enqueue_before_start_is_survivable() -> None:
    """A point handed over before the queue exists must not raise."""
    assert influx_store._queue is None
    influx_store.enqueue(_point(1))  # must not raise


async def test_drain_survives_unreachable_database(write_queue: None) -> None:
    for i in range(5):
        influx_store.enqueue(_point(i))

    await asyncio.sleep(influx_store._LINGER + 0.5)

    assert influx_store.pending() == 0, "queue was not drained"
    task = influx_store._drain_task
    assert task is not None and not task.done(), "drain task died on write failure"


async def test_drain_batches_rather_than_writing_one_at_a_time(
    write_queue: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    batches: list[int] = []
    monkeypatch.setattr(
        influx_store, "write_points", lambda points: batches.append(len(points))
    )

    for i in range(12):
        influx_store.enqueue(_point(i))
    await asyncio.sleep(influx_store._LINGER + 0.5)

    assert batches, "nothing was written"
    assert sum(batches) == 12
    assert len(batches) == 1, f"expected one coalesced write, got {batches}"


async def test_ensure_running_revives_a_dead_drain_task(write_queue: None) -> None:
    influx_store._drain_task.cancel()
    await asyncio.sleep(0.05)
    assert influx_store._drain_task.done()

    influx_store.ensure_running()

    assert not influx_store._drain_task.done()


async def test_stop_clears_the_queue_so_a_restart_gets_a_fresh_one() -> None:
    """An asyncio.Queue belongs to the loop it was made on.

    Reusing one across runs makes every operation raise, and the drain task
    would then die on each restart.
    """
    await influx_store.start()
    first = influx_store._queue
    await influx_store.stop()
    assert influx_store._queue is None

    await influx_store.start()
    assert influx_store._queue is not first
    await influx_store.stop()


def test_linger_is_short_enough_to_stay_near_real_time() -> None:
    """Batching trades write frequency for lag; the lag has to stay small.

    The dashboard reads live power from memory, so this only delays what lands
    in InfluxDB — but a long linger would show up in the history charts.
    """
    assert 1.0 <= influx_store._LINGER <= 15.0


async def test_get_client_is_reused() -> None:
    """One client, not one per write: the churn was the original problem."""
    try:
        first = influx_store.get_client()
        assert influx_store.get_client() is first
    finally:
        await influx_store.stop()
