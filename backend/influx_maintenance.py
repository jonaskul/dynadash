"""Keep the Pulse measurement from growing without bound.

Pulse writes a point every couple of seconds. Nothing in the dashboard charts
raw Pulse data older than seven days, but the points accumulate forever, and a
growing measurement is what makes queries slow again however carefully they are
written.

So: an InfluxDB task rolls raw ``tibber_pulse`` up into ``tibber_pulse_1m`` once
a minute's worth exists, and raw points are pruned once the rollup covers them.
The rollup keeps the information at roughly a thirtieth of the size.

Pruning is a permanent delete, so it is guarded twice over: it only ever touches
the raw measurement, and it never advances past what the rollup has actually
recorded. If the task stops running, pruning stops with it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import influx_store
from config import config

logger = logging.getLogger(__name__)

RAW_MEASUREMENT = "tibber_pulse"
ROLLUP_MEASUREMENT = "tibber_pulse_1m"
TASK_NAME = "dynadash-pulse-rollup"

# Counters must be rolled up with last(); averaging a monotonically increasing
# total would turn it into something that means nothing.
_COUNTER_FIELDS = r"^(accumulated|lastMeter)"

# The rollup must never get closer to the prune boundary than this, so a delete
# can only ever remove points the rollup has already seen.
_PRUNE_SAFETY_MARGIN = timedelta(days=1)


def _rollup_flux(every_minutes: int) -> str:
    bucket = config.influxdb.bucket
    # The lookback is wider than the interval on purpose: overlapping runs
    # rewrite the same windows, and since aggregateWindow aligns to absolute
    # time boundaries those rewrites land on identical timestamps and simply
    # overwrite. That makes the task idempotent and lets it recover from a
    # missed run on its own.
    return f"""option task = {{name: "{TASK_NAME}", every: {every_minutes}m, offset: 30s}}

src = from(bucket: "{bucket}")
    |> range(start: -{every_minutes * 3}m)
    |> filter(fn: (r) => r._measurement == "{RAW_MEASUREMENT}")

counters = src
    |> filter(fn: (r) => r._field =~ /{_COUNTER_FIELDS}/)
    |> aggregateWindow(every: 1m, fn: last, createEmpty: false)

gauges = src
    |> filter(fn: (r) => not (r._field =~ /{_COUNTER_FIELDS}/))
    |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)

union(tables: [counters, gauges])
    |> set(key: "_measurement", value: "{ROLLUP_MEASUREMENT}")
    |> to(bucket: "{bucket}")
"""


# ---------------------------------------------------------------------------
# The rollup task
# ---------------------------------------------------------------------------

def ensure_rollup_task() -> None:
    """Create the downsampling task, or update it if the Flux has changed.

    Blocking — call via ``asyncio.to_thread``.
    """
    client = influx_store.get_client()
    tasks_api = client.tasks_api()
    flux = _rollup_flux(config.retention.rollup_every_minutes)

    existing = None
    for task in tasks_api.find_tasks(name=TASK_NAME) or []:
        if task.name == TASK_NAME:
            existing = task
            break

    if existing is None:
        org = _org_id(client)
        tasks_api.create_task_with_script(name=TASK_NAME, flux=flux, org_id=org)
        logger.info("Created InfluxDB rollup task %r", TASK_NAME)
        return

    if (existing.flux or "").strip() != flux.strip():
        existing.flux = flux
        tasks_api.update_task(existing)
        logger.info("Updated InfluxDB rollup task %r", TASK_NAME)


def _org_id(client) -> str:
    for org in client.organizations_api().find_organizations() or []:
        if org.name == config.influxdb.org:
            return org.id
    raise RuntimeError(f"InfluxDB organization {config.influxdb.org!r} not found")


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

def latest_rollup_time() -> Optional[datetime]:
    """Newest timestamp present in the rollup, or None when it is empty."""
    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -365d)
  |> filter(fn: (r) => r._measurement == "{ROLLUP_MEASUREMENT}")
  |> last()
  |> keep(columns: ["_time"])
"""
    newest: Optional[datetime] = None
    for table in influx_store.query(flux):
        for record in table.records:
            ts = record.get_time()
            if ts is not None and (newest is None or ts > newest):
                newest = ts
    return newest


def prune_cutoff(now: Optional[datetime] = None) -> Optional[datetime]:
    """The timestamp raw Pulse data may safely be deleted before.

    Returns None when nothing should be pruned — either pruning is switched off
    or the rollup has not caught up, in which case the raw points are the only
    copy and must be left alone.
    """
    if not config.retention.prune_raw:
        return None
    if config.retention.raw_pulse_days <= 0:
        return None

    now = now or datetime.now(timezone.utc)
    by_age = now - timedelta(days=config.retention.raw_pulse_days)

    newest_rollup = latest_rollup_time()
    if newest_rollup is None:
        logger.info("Rollup is still empty — not pruning raw Pulse data yet")
        return None

    # Never delete raw data the rollup has not recorded. If the task stalls, the
    # rollup stops advancing and this boundary stops with it.
    by_rollup = newest_rollup - _PRUNE_SAFETY_MARGIN
    cutoff = min(by_age, by_rollup)

    if cutoff <= datetime(1970, 1, 2, tzinfo=timezone.utc):
        return None
    return cutoff


def prune_raw_pulse() -> Optional[datetime]:
    """Delete raw Pulse points older than the safe cutoff.

    Returns the cutoff used, or None when nothing was pruned. Blocking — call
    via ``asyncio.to_thread``.
    """
    cutoff = prune_cutoff()
    if cutoff is None:
        return None

    client = influx_store.get_client()
    client.delete_api().delete(
        start=datetime(1970, 1, 1, tzinfo=timezone.utc),
        stop=cutoff,
        # Scoped to the raw measurement alone: the rollup, prices, consumption,
        # temperatures and channel levels are all untouched.
        predicate=f'_measurement="{RAW_MEASUREMENT}"',
        bucket=config.influxdb.bucket,
        org=config.influxdb.org,
    )
    logger.info(
        "Pruned raw %s points older than %s (kept as %s)",
        RAW_MEASUREMENT,
        cutoff.isoformat(),
        ROLLUP_MEASUREMENT,
    )
    return cutoff


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def backfill_rollup(days: int = 400, chunk_days: int = 1) -> int:
    """Build rollups for Pulse history that predates the task.

    Walks the range a day at a time so a long history cannot be pulled into
    memory all at once. Idempotent: rewriting a window overwrites it. Returns
    the number of chunks processed. Blocking — call via ``asyncio.to_thread``.
    """
    bucket = config.influxdb.bucket
    now = datetime.now(timezone.utc)
    processed = 0

    for offset in range(days, 0, -chunk_days):
        start = now - timedelta(days=offset)
        stop = min(now, start + timedelta(days=chunk_days))
        flux = f"""
src = from(bucket: "{bucket}")
    |> range(start: {start.isoformat()}, stop: {stop.isoformat()})
    |> filter(fn: (r) => r._measurement == "{RAW_MEASUREMENT}")

counters = src
    |> filter(fn: (r) => r._field =~ /{_COUNTER_FIELDS}/)
    |> aggregateWindow(every: 1m, fn: last, createEmpty: false)

gauges = src
    |> filter(fn: (r) => not (r._field =~ /{_COUNTER_FIELDS}/))
    |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)

union(tables: [counters, gauges])
    |> set(key: "_measurement", value: "{ROLLUP_MEASUREMENT}")
    |> to(bucket: "{bucket}")
"""
        try:
            influx_store.query(flux)
            processed += 1
        except Exception as exc:
            logger.warning("Rollup backfill failed for %s: %s", start.date(), exc)

    logger.info("Rollup backfill covered %d day(s)", processed)
    return processed


if __name__ == "__main__":  # pragma: no cover - operator entry point
    # One-off backfill for Pulse history written before the rollup task existed:
    #   backend/.venv/bin/python -m influx_maintenance backfill [days]
    import sys

    logging.basicConfig(level=logging.INFO)
    action = sys.argv[1] if len(sys.argv) > 1 else "backfill"
    if action == "backfill":
        span = int(sys.argv[2]) if len(sys.argv) > 2 else 400
        ensure_rollup_task()
        backfill_rollup(days=span)
    elif action == "prune":
        print(prune_raw_pulse() or "nothing to prune")
    else:
        print(f"usage: python -m influx_maintenance {{backfill [days]|prune}}")
        raise SystemExit(64)
