from __future__ import annotations

import logging
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
    # Restart background services with new credentials
    await pulse_manager.start(body.token, body.home_id)
    await rest_poller.start(body.token, body.home_id)
    return {"configured": True, "home_id": body.home_id}


@router.delete("/settings")
async def delete_energy_settings() -> dict[str, Any]:
    pulse_manager.stop()
    rest_poller.stop()
    delete_setting("tibber_token")
    delete_setting("tibber_home_id")
    return {"configured": False}


@router.get("/homes")
async def list_homes() -> Any:
    token = _require_token()
    query = "{ viewer { homes { id address { address1 city } } } }"
    try:
        data = await _gql(token, query)
    except TibberAPIError as exc:
        raise HTTPException(502, {"error": "tibber_api_error", "detail": str(exc)})
    return data["viewer"]["homes"]


@router.get("/status")
async def energy_status() -> dict[str, Any]:
    token = get_setting("tibber_token")
    home_id = get_setting("tibber_home_id")
    configured = bool(token)

    current_price: Optional[dict[str, Any]] = None
    if configured and home_id:
        try:
            flux = f"""
from(bucket: "{config.influxdb.bucket}")
  |> range(start: -2h)
  |> filter(fn: (r) => r._measurement == "tibber_price")
  |> filter(fn: (r) => r._field == "total" or r._field == "level")
  |> last()
  |> pivot(rowKey: ["_time", "level", "currency"], columnKey: ["_field"], valueColumn: "_value")
"""
            rows = _influx_query(flux)
            if rows:
                row = rows[-1]
                current_price = {
                    "total": row.get("value"),
                    "level": row.get("level"),
                    "currency": row.get("currency"),
                }
        except Exception:
            pass

    return {
        "configured": configured,
        "home_id": home_id,
        "pulse_connected": pulse_manager.connected,
        "last_pulse_ts": pulse_manager.last_ts,
        "current_price": current_price,
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
    last: int = Query(30, ge=1, le=744),
) -> list[dict[str, Any]]:
    token = _require_token()
    home_id = get_setting("tibber_home_id") or ""
    if resolution not in _VALID_RESOLUTIONS:
        raise HTTPException(
            422,
            f"Invalid resolution '{resolution}'. Must be one of: {', '.join(_VALID_RESOLUTIONS)}",
        )
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
