from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class InfluxDBConfig(BaseModel):
    url: str = "http://localhost:8086"
    token: str = ""
    org: str = "home"
    bucket: str = "dynadash"


class AppConfig(BaseModel):
    influxdb: InfluxDBConfig = InfluxDBConfig()
    polling_interval_seconds: int = 10


def load_config() -> AppConfig:
    """Load configuration from config.yaml next to this file."""
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        # Fall back to example file location (one level up)
        config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        return AppConfig()

    with config_path.open() as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    influx_raw = raw.get("influxdb", {})
    return AppConfig(
        influxdb=InfluxDBConfig(**influx_raw),
        polling_interval_seconds=int(raw.get("polling_interval_seconds", 10)),
    )


# Module-level singleton loaded once at import time.
config: AppConfig = load_config()
