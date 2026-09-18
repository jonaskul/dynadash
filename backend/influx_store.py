"""Shared InfluxDB access for the whole backend.

Two things here exist to keep the Tibber Pulse WebSocket alive:

* **One client, reused.** Building an ``InfluxDBClient`` per call opens a fresh
  TCP connection every time. At Pulse rates (a measurement every ~2s) plus a
  dashboard polling ``/api/energy/status``, that was well over a connection per
  second of pure churn.
* **Writes never block the caller.** Points are appended to a bounded queue and
  flushed by one background task. Nothing on the event loop waits for InfluxDB,
  so a slow or unreachable database can no longer stall the Pulse read loop —
  which is what silently killed the live feed: a blocked reader stops draining
  the socket, the pong frames behind it are never processed, and the connection
  dies on a keepalive timeout.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import Any, Optional

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from config import config

logger = logging.getLogger(__name__)

# Bound the queue so an InfluxDB outage costs memory we have, not all of it.
# At one Pulse point every two seconds this holds a bit under three hours.
_QUEUE_MAX = 5_000
_BATCH_MAX = 500
# How long the drain task lingers collecting more points before writing. The UI
# reads live power straight from memory, so this lag is invisible there.
_LINGER = 5.0

_client: Optional[InfluxDBClient] = None
_client_lock = threading.Lock()

_queue: Optional[asyncio.Queue[Point]] = None
_drain_task: Optional[asyncio.Task[None]] = None
_dropped = 0


# ---------------------------------------------------------------------------
# Shared client
# ---------------------------------------------------------------------------

def get_client() -> InfluxDBClient:
    """Return the process-wide client, creating it on first use.

    The client is thread-safe, so query and write calls dispatched to worker
    threads can all share this one instance.
    """
    global _client
    with _client_lock:
        if _client is None:
            _client = InfluxDBClient(
                url=config.influxdb.url,
                token=config.influxdb.token,
                org=config.influxdb.org,
                # Without a bound, a hung InfluxDB holds a worker thread
                # forever and the pool eventually has nothing left to give.
                timeout=10_000,
            )
        return _client


def query(flux: str) -> Any:
    """Run a Flux query. Blocking — call via ``asyncio.to_thread``."""
    return get_client().query_api().query(flux)


def write_points(points: list[Point]) -> None:
    """Write a batch synchronously. Blocking — call via ``asyncio.to_thread``."""
    if not points:
        return
    get_client().write_api(write_options=SYNCHRONOUS).write(
        bucket=config.influxdb.bucket, record=points
    )


# ---------------------------------------------------------------------------
# Background write queue
# ---------------------------------------------------------------------------

def enqueue(point: Point) -> None:
    """Queue a point for background writing.

    Never blocks and never raises: callers on the event loop must be able to
    hand off a measurement without caring whether InfluxDB is healthy. When the
    queue is full the oldest point is dropped, because for a live feed the
    newest reading is the one worth keeping.
    """
    global _dropped
    q = _queue
    if q is None:
        logger.warning("InfluxDB queue not started — dropping point")
        return
    try:
        q.put_nowait(point)
    except asyncio.QueueFull:
        with contextlib.suppress(asyncio.QueueEmpty, asyncio.QueueFull):
            q.get_nowait()
            q.put_nowait(point)
        _dropped += 1
        if _dropped % 100 == 1:
            logger.warning(
                "InfluxDB queue full — %d point(s) dropped so far", _dropped
            )


def pending() -> int:
    """Number of points waiting to be written."""
    return _queue.qsize() if _queue is not None else 0


async def _drain() -> None:
    q = _queue
    assert q is not None
    loop = asyncio.get_running_loop()
    while True:
        batch = [await q.get()]
        deadline = loop.time() + _LINGER
        while len(batch) < _BATCH_MAX:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(q.get(), timeout=remaining))
            except asyncio.TimeoutError:
                break
        try:
            await asyncio.to_thread(write_points, batch)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            # Dropping the batch is the right call: retrying a backlog against a
            # struggling database only makes the backlog worse.
            logger.warning(
                "InfluxDB write failed, discarding %d point(s): %s", len(batch), exc
            )


async def start() -> None:
    """Create the queue and start the drain task."""
    global _queue, _drain_task
    if _drain_task is not None and not _drain_task.done():
        return
    # Always a fresh queue: an asyncio.Queue is bound to the loop it was made
    # on, so one carried over from a previous run would reject every operation.
    _queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _drain_task = asyncio.create_task(_drain(), name="influx-drain")
    logger.info("InfluxDB write queue started")


def ensure_running() -> None:
    """Restart the drain task if it ever died. Called by the watchdog."""
    global _drain_task
    if _queue is None:
        return
    if _drain_task is None or _drain_task.done():
        logger.warning("InfluxDB drain task was dead — restarting")
        _drain_task = asyncio.create_task(_drain(), name="influx-drain")


async def stop() -> None:
    """Stop the drain task and flush whatever is still queued."""
    global _drain_task
    task, _drain_task = _drain_task, None
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    global _queue
    q, _queue = _queue, None
    if q is not None:
        leftover: list[Point] = []
        while True:
            try:
                leftover.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break
        if leftover:
            try:
                await asyncio.to_thread(write_points, leftover)
                logger.info("Flushed %d queued point(s) on shutdown", len(leftover))
            except Exception as exc:
                logger.warning("Final InfluxDB flush failed: %s", exc)

    global _client
    with _client_lock:
        if _client is not None:
            with contextlib.suppress(Exception):
                _client.close()
            _client = None
