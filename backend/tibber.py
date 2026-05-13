from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from config import config
from tibber_db import delete_setting, get_setting, set_setting
from tibber_pulse import pulse_manager, rest_poller

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/energy", tags=["energy"])

_GQL_URL = "https://api.tibber.com/v1-beta/gql"
_VALID_RANGES = {"1h", "6h", "24h", "7d"}
_VALID_RESOLUTIONS = {"HOURLY", "DAILY", "MONTHLY"}


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
            headers={"Authorization": f"Bearer {token}"},
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
    from influxdb_client import InfluxDBClient
    with InfluxDBClient(
        url=config.influxdb.url,
        token=config.influxdb.token,
        org=config.influxdb.org,
    ) as client:
        tables = client.query_api().query(flux)
    results = []
    for table in tables:
        for record in table.records:
            results.append({
                "time": record.get_time().isoformat() if record.get_time() else None,
                "value": record.get_value(),
                "field": record.get_field(),
            })
    return results


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
            from influxdb_client import InfluxDBClient
            flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -2h)
  |> filter(fn: (r) => r._measurement == "tibber_price")
  |> filter(fn: (r) => r._field == "total")
  |> last()
"""
            with InfluxDBClient(
                url=config.influxdb.url,
                token=config.influxdb.token,
                org=config.influxdb.org,
            ) as client:
                tables = client.query_api().query(flux)
            for table in tables:
                for record in table.records:
                    current_price = {
                        "total": record.get_value(),
                        "level": record.values.get("level"),
                        "currency": record.values.get("currency"),
                    }
        except Exception:
            pass

    current_power: Optional[float] = None
    if configured:
        try:
            flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "tibber_pulse")
  |> filter(fn: (r) => r._field == "power")
  |> last()
"""
            rows = _influx_query(flux)
            if rows:
                current_power = rows[-1]["value"]
        except Exception:
            pass

    # Consider Pulse "connected" only if we got a measurement in the last 60s
    pulse_live = False
    if pulse_manager.connected and pulse_manager.last_ts:
        try:
            last = datetime.fromisoformat(pulse_manager.last_ts.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - last).total_seconds()
            pulse_live = age < 60
        except Exception:
            pulse_live = pulse_manager.connected

    return {
        "configured": configured,
        "home_id": home_id,
        "pulse_connected": pulse_live,
        "last_pulse_ts": pulse_manager.last_ts,
        "current_price": current_price,
        "current_power": current_power,
    }


@router.get("/prices")
async def get_prices() -> dict[str, Any]:
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


@router.get("/consumption")
async def get_consumption(
    resolution: str = Query("HOURLY"),
    last: int = Query(24),
) -> list[dict[str, Any]]:
    if resolution not in _VALID_RESOLUTIONS:
        raise HTTPException(422, f"Invalid resolution '{resolution}'.")
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


@router.get("/history/power")
async def history_power(
    range: str = Query("24h"),
) -> list[dict[str, Any]]:
    if range not in _VALID_RANGES:
        raise HTTPException(422, f"Invalid range '{range}'. Must be one of: {', '.join(sorted(_VALID_RANGES))}")
    flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -{range})
  |> filter(fn: (r) => r._measurement == "tibber_pulse")
  |> filter(fn: (r) => r._field == "power")
  |> sort(columns: ["_time"])
"""
    try:
        rows = _influx_query(flux)
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
  |> filter(fn: (r) => r._measurement == "tibber_pulse")
  |> filter(fn: (r) => r._field == "accumulatedCost")
  |> sort(columns: ["_time"])
"""
    try:
        rows = _influx_query(flux)
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
  |> filter(fn: (r) => r._measurement == "tibber_pulse")
  |> filter(fn: (r) => {fields_filter})
  |> sort(columns: ["_time"])
"""
    try:
        rows = _influx_query(flux)
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
