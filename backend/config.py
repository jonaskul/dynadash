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


class RetentionConfig(BaseModel):
    """How long raw Pulse measurements are kept before being rolled up.

    Pulse writes a point every ~2s, which is roughly 43k points a day across 19
    fields — left alone it fills the disk and slows every query. A one-minute
    rollup keeps the information at about a thirtieth of the size, and the raw
    points are pruned once the rollup has them.
    """

    # The dashboard never charts Pulse data older than 7 days, so this is a wide
    # margin over anything that can actually be displayed.
    raw_pulse_days: int = 35
    rollup_every_minutes: int = 5
    # Set false to keep every raw point forever and only build the rollup.
    prune_raw: bool = True


class AppConfig(BaseModel):
    influxdb: InfluxDBConfig = InfluxDBConfig()
    polling_interval_seconds: int = 10
    retention: RetentionConfig = RetentionConfig()


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
        retention=RetentionConfig(**raw.get("retention", {})),
    )


# Module-level singleton loaded once at import time.
config: AppConfig = load_config()
