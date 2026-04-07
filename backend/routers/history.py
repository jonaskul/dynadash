from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from influx import InfluxReader

router = APIRouter(prefix="/api/history", tags=["history"])

_reader = InfluxReader()

VALID_RANGES = {"1h", "6h", "24h", "7d"}


def _validate_range(range_str: str) -> None:
    if range_str not in VALID_RANGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid range '{range_str}'. Must be one of: {', '.join(sorted(VALID_RANGES))}",
        )


@router.get("/temperature")
async def temperature_history(
    area_id: int = Query(..., description="Area ID"),
    range: str = Query("24h", description="Time range: 1h, 6h, 24h, 7d"),
) -> list[dict[str, Any]]:
    """Return temperature and setpoint history for a thermostat area."""
    _validate_range(range)
    try:
        return _reader.query_temperature_history(area_id, range)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"InfluxDB query failed: {exc}")


@router.get("/level")
async def level_history(
    area_id: int = Query(..., description="Area ID"),
    channel: int = Query(1, description="Channel number"),
    range: str = Query("24h", description="Time range: 1h, 6h, 24h, 7d"),
) -> list[dict[str, Any]]:
    """Return channel level history for a lighting area."""
    _validate_range(range)
    try:
        return _reader.query_level_history(area_id, channel, range)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"InfluxDB query failed: {exc}")
