from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import influx_maintenance
import influx_store
from config import config
from tibber_db import delete_setting, get_setting, set_setting
from tibber_pulse import pulse_manager, rest_poller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/energy", tags=["energy"])

_GQL_URL = "https://api.tibber.com/v1-beta/gql"
_USER_AGENT = "DynaDash/1.0"
_VALID_RANGES = {"1h", "6h", "24h", "7d"}
_VALID_RESOLUTIONS = {"HOURLY", "DAILY", "MONTHLY"}

# Pulse writes a measurement every ~2s, so an un-aggregated 7d query returns
# roughly 300k points per field — enough to exhaust memory on the box and hang
# the browser. Every range is downsampled to a few hundred points instead.
_WINDOW = {"1h": "10s", "6h": "1m", "24h": "5m", "7d": "30m"}

# Long ranges read the one-minute rollup rather than the raw measurement. The
# aggregation result is the same at these window sizes, but InfluxDB scans about
# thirty times less to produce it — and raw points are pruned after a few weeks,
# while the rollup is kept.
_ROLLUP_RANGES = frozenset({"24h", "7d"})


def _pulse_measurement(range_: str) -> str:
    return (
        influx_maintenance.ROLLUP_MEASUREMENT
        if range_ in _ROLLUP_RANGES
        else influx_maintenance.RAW_MEASUREMENT
    )


# The dashboard polls /status every two seconds. Serving it straight from
# InfluxDB kept the worker-thread pool busy around the clock, and once that pool
# had nothing free the Pulse read loop stalled with it.
_PRICE_TTL = 60.0
_POWER_TTL = 10.0
# Beyond this, the in-memory measurement is too old to report as live power.
_LIVE_MAX_AGE = 300.0

# Prices and consumption only change once an hour, and the poller stores 720
# hours of consumption, so nothing is gained by reading past that.
_PRICES_TTL = 120.0
_CONSUMPTION_TTL = 120.0
_MAX_STORED_HOURS = 744


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TibberAPIError(Exception):
    pass


async def _gql(token: str, query: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            _GQL_URL,
            json={"query": query},
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": _USER_AGENT,
            },
        )
        r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise TibberAPIError(body["errors"])
    return body["data"]


def _require_token() -> str:
    token = get_setting("tibber_token")
    if not token:
        raise HTTPException(
            status_code=503,
            detail={"error": "no_token", "configured": False},
        )
    return token


def _influx_query(flux: str) -> list[dict[str, Any]]:
    tables = influx_store.query(flux)
    results = []
    for table in tables:
        for record in table.records:
            results.append({
                "time": record.get_time().isoformat() if record.get_time() else None,
                "value": record.get_value(),
                "field": record.get_field(),
            })
    return results


def _last_price() -> Optional[dict[str, Any]]:
    """Most recent stored price. Blocking — call via a worker thread."""
    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -2h)
  |> filter(fn: (r) => r._measurement == "tibber_price")
  |> filter(fn: (r) => r._field == "total")
  |> last()
"""
    rows = [
        {
            "total": record.get_value(),
            "level": record.values.get("level"),
            "currency": record.values.get("currency"),
        }
        for table in influx_store.query(flux)
        for record in table.records
    ]
    return rows[-1] if rows else None


def _last_stored_power() -> Optional[float]:
    """Most recent stored power reading. Blocking — call via a worker thread."""
    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "tibber_pulse")
  |> filter(fn: (r) => r._field == "power")
  |> last()
"""
    rows = _influx_query(flux)
    return rows[-1]["value"] if rows else None


def _local_day_start() -> datetime:
    """Midnight today in the machine's own timezone.

    Prices are bucketed into today and tomorrow the same way Tibber does it, by
    local calendar day rather than by a rolling 24 hours.
    """
    now = datetime.now().astimezone()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _stored_prices() -> dict[str, Any]:
    """Today's and tomorrow's stored prices. Blocking — use a worker thread."""
    day_start = _local_day_start()
    tomorrow = day_start + timedelta(days=1)
    end = day_start + timedelta(days=2)

    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: {day_start.isoformat()}, stop: {end.isoformat()})
  |> filter(fn: (r) => r._measurement == "tibber_price")
  |> filter(fn: (r) => r._field == "total" or r._field == "energy" or r._field == "tax")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
"""
    today: list[dict[str, Any]] = []
    later: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    hour_now = datetime.now().astimezone().replace(
        minute=0, second=0, microsecond=0
    )

    for table in influx_store.query(flux):
        for record in table.records:
            ts = record.get_time()
            if ts is None:
                continue
            values = record.values
            entry = {
                "startsAt": ts.isoformat(),
                "total": values.get("total"),
                "energy": values.get("energy"),
                "tax": values.get("tax"),
                "level": values.get("level"),
                "currency": values.get("currency"),
            }
            local = ts.astimezone()
            (later if local >= tomorrow else today).append(entry)
            if local == hour_now:
                current = entry

    return {"current": current, "today": today, "tomorrow": later}


# Consumption is stored hourly; coarser resolutions are summed from that rather
# than asked of Tibber again.
_RESOLUTION_HOURS = {"HOURLY": 1, "DAILY": 24, "MONTHLY": 24 * 31}


def _stored_consumption(resolution: str, last: int) -> list[dict[str, Any]]:
    """Stored consumption at the requested resolution. Blocking — worker thread."""
    hours = min(_RESOLUTION_HOURS[resolution] * last, _MAX_STORED_HOURS)
    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "tibber_consumption")
  |> filter(fn: (r) => r._field == "consumption" or r._field == "cost" or r._field == "unitPrice")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"])
"""
    rows: list[dict[str, Any]] = []
    for table in influx_store.query(flux):
        for record in table.records:
            ts = record.get_time()
            if ts is None:
                continue
            values = record.values
            rows.append({
                "time": ts.astimezone(),
                "consumption": values.get("consumption"),
                "cost": values.get("cost"),
                "unitPrice": values.get("unitPrice"),
                "currency": values.get("currency"),
            })
    rows.sort(key=lambda r: r["time"])

    if resolution == "HOURLY":
        nodes = [
            {
                "from": r["time"].isoformat(),
                "to": (r["time"] + timedelta(hours=1)).isoformat(),
                "consumption": r["consumption"],
                "cost": r["cost"],
                "unitPrice": r["unitPrice"],
                "currency": r["currency"],
            }
            for r in rows
        ]
        return nodes[-last:]

    return _bucket_consumption(rows, resolution)[-last:]


def _bucket_consumption(
    rows: list[dict[str, Any]], resolution: str
) -> list[dict[str, Any]]:
    """Sum hourly rows into days or months.

    Consumption and cost add up; the unit price is averaged, weighted by the
    consumption it applied to, so an hour with barely any usage cannot pull the
    average around.
    """
    buckets: dict[datetime, dict[str, Any]] = {}
    for r in rows:
        t = r["time"]
        key = (
            t.replace(hour=0, minute=0, second=0, microsecond=0)
            if resolution == "DAILY"
            else t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        )
        bucket = buckets.setdefault(
            key,
            {"consumption": 0.0, "cost": 0.0, "price_sum": 0.0, "currency": None},
        )
        kwh = r["consumption"] or 0.0
        bucket["consumption"] += kwh
        bucket["cost"] += r["cost"] or 0.0
        bucket["price_sum"] += (r["unitPrice"] or 0.0) * kwh
        bucket["currency"] = bucket["currency"] or r["currency"]

    nodes = []
    for key in sorted(buckets):
        b = buckets[key]
        span = timedelta(days=1) if resolution == "DAILY" else timedelta(days=31)
        kwh = b["consumption"]
        nodes.append({
            "from": key.isoformat(),
            "to": (key + span).isoformat(),
            "consumption": kwh,
            "cost": b["cost"],
            "unitPrice": (b["price_sum"] / kwh) if kwh else None,
            "currency": b["currency"],
        })
    return nodes


_cache: dict[str, tuple[float, Any]] = {}


async def _cached(key: str, ttl: float, fn: Callable[..., Any], *args: Any) -> Any:
    """Run *fn* in a worker thread, reusing its result for *ttl* seconds."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[0] < ttl:
        return hit[1]
    value = await asyncio.to_thread(fn, *args)
    _cache[key] = (time.monotonic(), value)
    return value


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class EnergySettings(BaseModel):
    token: str
    home_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_energy_settings() -> dict[str, Any]:
    token = get_setting("tibber_token")
    home_id = get_setting("tibber_home_id")
    configured = bool(token)
    token_hint = f"…{token[-6:]}" if token and len(token) >= 6 else None
    return {
        "configured": configured,
        "token_hint": token_hint,
        "home_id": home_id,
    }


@router.post("/settings")
async def save_energy_settings(body: EnergySettings) -> dict[str, Any]:
    set_setting("tibber_token", body.token)
    set_setting("tibber_home_id", body.home_id)
    await pulse_manager.start(body.token, body.home_id)
    await rest_poller.start(body.token, body.home_id)
    return {"ok": True}


@router.delete("/settings")
async def delete_energy_settings() -> dict[str, Any]:
    delete_setting("tibber_token")
    delete_setting("tibber_home_id")
    pulse_manager.stop()
    rest_poller.stop()
    return {"ok": True}


@router.get("/status")
async def energy_status() -> dict[str, Any]:
    token = get_setting("tibber_token")
    home_id = get_setting("tibber_home_id")
    configured = bool(token)

    current_price: Optional[dict[str, Any]] = None
    if configured and home_id:
        try:
            current_price = await _cached("price", _PRICE_TTL, _last_price)
        except Exception:
            pass

    # The live reading is already in memory from the WebSocket — querying
    # InfluxDB for it on every poll was pure waste.
    current_power: Optional[float] = None
    age = pulse_manager.data_age
    measurement = pulse_manager.last_measurement
    if measurement is not None and age is not None and age < _LIVE_MAX_AGE:
        raw = measurement.get("power")
        if raw is not None:
            try:
                current_power = float(raw)
            except (TypeError, ValueError):
                current_power = None
    elif configured:
        # No live feed right now: fall back to the last stored value, cached so
        # a two-second poll cannot turn into two queries a second.
        try:
            current_power = await _cached("power", _POWER_TTL, _last_stored_power)
        except Exception:
            pass

    # Report Pulse as live only while measurements are actually arriving.
    pulse_live = pulse_manager.connected and age is not None and age < 60

    return {
        "configured": configured,
        "home_id": home_id,
        "pulse_connected": pulse_live,
        "last_pulse_ts": pulse_manager.last_ts,
        "current_price": current_price,
        "current_power": current_power,
    }


async def _live_prices() -> dict[str, Any]:
    """Fetch prices straight from Tibber. Used only when nothing is stored yet."""
    token = _require_token()
    home_id = get_setting("tibber_home_id") or ""
    query = """{{ viewer {{ home(id: "{home_id}") {{
        currentSubscription {{ priceInfo {{
            current {{ total energy tax startsAt level currency }}
            today   {{ total energy tax startsAt level currency }}
            tomorrow {{ total energy tax startsAt level currency }}
        }} }}
    }} }} }}""".format(home_id=home_id)
    try:
        data = await _gql(token, query)
    except TibberAPIError as exc:
        raise HTTPException(502, {"error": "tibber_api_error", "detail": str(exc)})
    info = data["viewer"]["home"]["currentSubscription"]["priceInfo"]
    return {
        "current": info.get("current"),
        "today": info.get("today", []),
        "tomorrow": info.get("tomorrow", []),
    }


@router.get("/prices")
async def get_prices() -> dict[str, Any]:
    """Today's and tomorrow's prices, served from InfluxDB.

    The hourly poller already stores these. Proxying every dashboard load
    straight through to Tibber instead spent the token's rate limit (about 100
    requests per five minutes) on data we had on disk — a couple of open tabs
    was enough to start tripping it.
    """
    try:
        stored = await _cached("prices", _PRICES_TTL, _stored_prices)
    except Exception as exc:
        logger.warning("Stored price lookup failed (%s) — asking Tibber", exc)
        stored = None

    if stored and (stored["today"] or stored["tomorrow"]):
        return stored

    # Nothing stored yet: a fresh install before the first poll, or an InfluxDB
    # that is not answering.
    return await _live_prices()


async def _live_consumption(resolution: str, last: int) -> list[dict[str, Any]]:
    """Fetch consumption from Tibber. Used only when nothing is stored yet."""
    token = _require_token()
    home_id = get_setting("tibber_home_id") or ""
    query = """{{ viewer {{ home(id: "{home_id}") {{
        consumption(resolution: {resolution}, last: {last}) {{
            nodes {{ from to cost unitPrice consumption currency }}
        }}
    }} }} }}""".format(home_id=home_id, resolution=resolution, last=last)
    try:
        data = await _gql(token, query)
    except TibberAPIError as exc:
        raise HTTPException(502, {"error": "tibber_api_error", "detail": str(exc)})
    nodes = data["viewer"]["home"]["consumption"]["nodes"]
    return [n for n in nodes if n]


@router.get("/consumption")
async def get_consumption(
    resolution: str = Query("HOURLY"),
    last: int = Query(24, ge=1, le=_MAX_STORED_HOURS),
) -> list[dict[str, Any]]:
    """Consumption history, served from InfluxDB.

    The hourly poller stores 720 hours of it; daily and monthly figures are
    summed from those rather than asked of Tibber again.
    """
    if resolution not in _VALID_RESOLUTIONS:
        raise HTTPException(422, f"Invalid resolution '{resolution}'.")

    try:
        nodes = await _cached(
            f"consumption:{resolution}:{last}",
            _CONSUMPTION_TTL,
            _stored_consumption,
            resolution,
            last,
        )
    except Exception as exc:
        logger.warning("Stored consumption lookup failed (%s) — asking Tibber", exc)
        nodes = None

    if nodes:
        return nodes

    return await _live_consumption(resolution, last)


@router.get("/history/power")
async def history_power(
    range: str = Query("24h"),
) -> list[dict[str, Any]]:
    if range not in _VALID_RANGES:
        raise HTTPException(422, f"Invalid range '{range}'. Must be one of: {', '.join(sorted(_VALID_RANGES))}")
    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -{range})
  |> filter(fn: (r) => r._measurement == "{_pulse_measurement(range)}")
  |> filter(fn: (r) => r._field == "power")
  |> aggregateWindow(every: {_WINDOW[range]}, fn: mean, createEmpty: false)
  |> sort(columns: ["_time"])
"""
    try:
        rows = await asyncio.to_thread(_influx_query, flux)
    except Exception as exc:
        raise HTTPException(500, f"InfluxDB query failed: {exc}")
    return [{"time": r["time"], "power": r["value"]} for r in rows]


@router.get("/history/cost")
async def history_cost(
    range: str = Query("24h"),
) -> list[dict[str, Any]]:
    if range not in _VALID_RANGES:
        raise HTTPException(422, f"Invalid range '{range}'. Must be one of: {', '.join(sorted(_VALID_RANGES))}")
    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -{range})
  |> filter(fn: (r) => r._measurement == "{_pulse_measurement(range)}")
  |> filter(fn: (r) => r._field == "accumulatedCost")
  |> aggregateWindow(every: {_WINDOW[range]}, fn: max, createEmpty: false)
  |> sort(columns: ["_time"])
"""
    try:
        rows = await asyncio.to_thread(_influx_query, flux)
    except Exception as exc:
        raise HTTPException(500, f"InfluxDB query failed: {exc}")
    return [{"time": r["time"], "accumulatedCost": r["value"]} for r in rows]


_PHASE_FIELDS = [
    "voltagePhase1", "voltagePhase2", "voltagePhase3",
    "currentL1", "currentL2", "currentL3",
]

@router.get("/history/phases")
async def history_phases(
    range: str = Query("1h"),
) -> list[dict[str, Any]]:
    if range not in _VALID_RANGES:
        raise HTTPException(422, f"Invalid range '{range}'. Must be one of: {', '.join(sorted(_VALID_RANGES))}")
    fields_filter = " or ".join(f'r._field == "{f}"' for f in _PHASE_FIELDS)
    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -{range})
  |> filter(fn: (r) => r._measurement == "{_pulse_measurement(range)}")
  |> filter(fn: (r) => {fields_filter})
  |> aggregateWindow(every: {_WINDOW[range]}, fn: mean, createEmpty: false)
  |> sort(columns: ["_time"])
"""
    try:
        rows = await asyncio.to_thread(_influx_query, flux)
    except Exception as exc:
        raise HTTPException(500, f"InfluxDB query failed: {exc}")
    by_time: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = r["time"]
        if t not in by_time:
            by_time[t] = {"time": t}
        if r["field"] and r["value"] is not None:
            by_time[t][r["field"]] = r["value"]
    return sorted(by_time.values(), key=lambda x: x["time"])


@router.get("/homes")
async def get_homes(
    token: Optional[str] = Query(None),
) -> list[dict[str, Any]]:
    if not token:
        token = _require_token()
    query = """{ viewer { homes { id address { address1 city } } } }"""
    try:
        data = await _gql(token, query)
    except TibberAPIError as exc:
        raise HTTPException(502, {"error": "tibber_api_error", "detail": str(exc)})
    return data["viewer"]["homes"]
