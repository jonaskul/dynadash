from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config import config as app_config

router = APIRouter(prefix="/api/settings", tags=["settings"])

DATA_DIR = Path(__file__).parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"


class AppSettings(BaseModel):
    polling_interval_seconds: int = Field(default=60, ge=60, le=3600)


def load_settings() -> AppSettings:
    if SETTINGS_FILE.exists():
        try:
            return AppSettings(**json.loads(SETTINGS_FILE.read_text()))
        except Exception:
            pass
    return AppSettings(polling_interval_seconds=app_config.polling_interval_seconds)


def save_settings(s: AppSettings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s.model_dump(), indent=2))


@router.get("", response_model=AppSettings)
async def get_settings() -> AppSettings:
    return load_settings()


@router.post("", response_model=AppSettings)
async def update_settings(body: AppSettings) -> AppSettings:
    save_settings(body)
    return body
