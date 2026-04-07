from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/api/config/areas", tags=["config-areas"])

DATA_DIR = Path(__file__).parent.parent / "data"
AREAS_FILE = DATA_DIR / "areas.json"


class AreaConfigIn(BaseModel):
    id: int
    name: str
    type: Literal["lighting", "thermostat"]
    channels: Optional[int] = 1
    presets: dict[str, str] = {}
    temp_min: Optional[float] = 16.0
    temp_max: Optional[float] = 30.0
    order: int = 0

    @field_validator("id")
    @classmethod
    def id_must_be_positive(cls, v: int) -> int:
        if v < 1 or v > 65535:
            raise ValueError("Area ID must be between 1 and 65535")
        return v

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Area name must not be empty")
        return v.strip()


class AreaConfigOut(AreaConfigIn):
    pass


def _load_all() -> list[dict[str, Any]]:
    if not AREAS_FILE.exists():
        return []
    try:
        return json.loads(AREAS_FILE.read_text())
    except Exception:
        return []


def _save_all(areas: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    AREAS_FILE.write_text(json.dumps(areas, indent=2))


@router.get("", response_model=list[AreaConfigOut])
async def list_areas() -> list[AreaConfigOut]:
    areas = _load_all()
    areas.sort(key=lambda a: (a.get("order", 0), a.get("id", 0)))
    return [AreaConfigOut(**a) for a in areas]


@router.post("", response_model=AreaConfigOut, status_code=201)
async def create_area(body: AreaConfigIn) -> AreaConfigOut:
    areas = _load_all()
    if any(a["id"] == body.id for a in areas):
        raise HTTPException(status_code=409, detail=f"Area {body.id} already exists")
    areas.append(body.model_dump())
    _save_all(areas)
    return AreaConfigOut(**body.model_dump())


@router.put("/{area_id}", response_model=AreaConfigOut)
async def update_area(area_id: int, body: AreaConfigIn) -> AreaConfigOut:
    areas = _load_all()
    for i, area in enumerate(areas):
        if area["id"] == area_id:
            areas[i] = body.model_dump()
            _save_all(areas)
            return AreaConfigOut(**body.model_dump())
    raise HTTPException(status_code=404, detail=f"Area {area_id} not found")


@router.delete("/{area_id}", status_code=204)
async def delete_area(area_id: int) -> None:
    areas = _load_all()
    original_length = len(areas)
    areas = [a for a in areas if a["id"] != area_id]
    if len(areas) == original_length:
        raise HTTPException(status_code=404, detail=f"Area {area_id} not found")
    _save_all(areas)
