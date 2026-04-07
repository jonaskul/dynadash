from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dynalite import DynaliteClient, DynaliteError
from poller import poller

router = APIRouter(prefix="/api/areas", tags=["areas"])

DATA_DIR = Path(__file__).parent.parent / "data"
GATEWAY_FILE = DATA_DIR / "gateway.json"
AREAS_FILE = DATA_DIR / "areas.json"


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class PresetRequest(BaseModel):
    preset: int
    fade_ms: int = 1000


class LevelRequest(BaseModel):
    channel: int
    level: float
    fade_ms: int = 500


class SetpointRequest(BaseModel):
    setpoint: float


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _load_gateway() -> Optional[dict[str, str]]:
    if not GATEWAY_FILE.exists():
        return None
    try:
        return json.loads(GATEWAY_FILE.read_text())
    except Exception:
        return None


def _load_areas() -> list[dict[str, Any]]:
    if not AREAS_FILE.exists():
        return []
    try:
        return json.loads(AREAS_FILE.read_text())
    except Exception:
        return []


def _get_client() -> DynaliteClient:
    gw = _load_gateway()
    if not gw:
        raise HTTPException(status_code=503, detail="Gateway not configured")
    return DynaliteClient(ip=gw["ip"])


def _require_area(area_id: int, areas: list[dict[str, Any]]) -> dict[str, Any]:
    for a in areas:
        if a["id"] == area_id:
            return a
    raise HTTPException(status_code=404, detail=f"Area {area_id} not found")


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("")
async def get_areas() -> list[dict[str, Any]]:
    """Return all areas with their current live state merged from the poller."""
    areas = _load_areas()
    areas.sort(key=lambda a: (a.get("order", 0), a.get("id", 0)))
    state = poller.get_state()
    gateway_reachable = poller.is_gateway_reachable()

    result: list[dict[str, Any]] = []
    for area in areas:
        area_id: int = area["id"]
        live = state.get(area_id, {})

        merged: dict[str, Any] = {
            "id": area_id,
            "name": area["name"],
            "type": area["type"],
            "presets": area.get("presets", {}),
            "gateway_reachable": gateway_reachable,
        }

        if area["type"] == "thermostat":
            merged["current_temp"] = live.get("current_temp")
            merged["setpoint"] = live.get("setpoint")
            merged["temp_min"] = area.get("temp_min", 16.0)
            merged["temp_max"] = area.get("temp_max", 30.0)
        else:
            merged["current_preset"] = live.get("current_preset")
            merged["channels"] = live.get("channels", [])
            merged["num_channels"] = area.get("channels", 1)

        result.append(merged)

    return result


@router.post("/{area_id}/preset")
async def set_preset(area_id: int, body: PresetRequest) -> dict[str, str]:
    areas = _load_areas()
    _require_area(area_id, areas)
    client = _get_client()
    try:
        await client.set_preset(area_id, body.preset, body.fade_ms)
    except DynaliteError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"status": "ok"}


@router.post("/{area_id}/level")
async def set_level(area_id: int, body: LevelRequest) -> dict[str, str]:
    areas = _load_areas()
    _require_area(area_id, areas)
    client = _get_client()
    try:
        await client.set_level(area_id, body.channel, body.level, body.fade_ms)
    except DynaliteError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"status": "ok"}


@router.post("/{area_id}/setpoint")
async def set_setpoint(area_id: int, body: SetpointRequest) -> dict[str, str]:
    areas = _load_areas()
    area = _require_area(area_id, areas)
    temp_min: float = area.get("temp_min", 16.0)
    temp_max: float = area.get("temp_max", 30.0)
    if not (temp_min <= body.setpoint <= temp_max):
        raise HTTPException(
            status_code=422,
            detail=f"Setpoint must be between {temp_min} and {temp_max}",
        )
    client = _get_client()
    try:
        await client.set_setpoint(area_id, body.setpoint)
    except DynaliteError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"status": "ok"}
