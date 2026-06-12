from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from influx import InfluxImporter, InfluxReader
from routers.config_areas import AreaConfigIn, _load_all, _save_all

router = APIRouter(prefix="/api/backup", tags=["backup"])

VALID_RANGES = {"7d", "30d", "90d", "all"}

_reader = InfluxReader()
_importer = InfluxImporter()


class ImportResult(BaseModel):
    areas_imported: int
    temperature_points: int
    level_points: int


@router.get("/export")
def export_backup(range: str = "7d") -> Response:
    if range not in VALID_RANGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid range '{range}'. Must be one of: {', '.join(sorted(VALID_RANGES))}",
        )
    try:
        areas = _load_all()
        temp = _reader.export_temperature(range)
        levels = _reader.export_channel_level(range)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")

    payload: dict[str, Any] = {
        "dynadash_backup": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "history_range": range,
        "areas": areas,
        "history": {
            "temperature": temp,
            "channel_level": levels,
        },
    }
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"dynadash-backup-{date_str}.json"
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=ImportResult)
def import_backup(body: dict = Body(...)) -> ImportResult:
    if body.get("dynadash_backup") != 1:
        raise HTTPException(
            status_code=422,
            detail="Not a valid DynaDash backup file (missing dynadash_backup version key).",
        )
    try:
        raw_areas: list[dict[str, Any]] = body.get("areas", [])
        validated = [AreaConfigIn(**a).model_dump() for a in raw_areas]
        _save_all(validated)

        history = body.get("history", {})
        t_count = _importer.import_temperature(history.get("temperature", []))
        l_count = _importer.import_channel_level(history.get("channel_level", []))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}")

    return ImportResult(
        areas_imported=len(validated),
        temperature_points=t_count,
        level_points=l_count,
    )
