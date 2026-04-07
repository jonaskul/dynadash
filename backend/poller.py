from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from config import config
from dynalite import DynaliteClient, DynaliteError
from influx import InfluxWriter

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
GATEWAY_FILE = DATA_DIR / "gateway.json"
AREAS_FILE = DATA_DIR / "areas.json"


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


class Poller:
    """Background asyncio task that polls the Dynalite gateway periodically."""

    def __init__(self) -> None:
        self._state: dict[int, dict[str, Any]] = {}
        self._writer = InfluxWriter()
        self._task: Optional[asyncio.Task[None]] = None
        self._gateway_reachable: bool = False

    def get_state(self) -> dict[int, dict[str, Any]]:
        return dict(self._state)

    def is_gateway_reachable(self) -> bool:
        return self._gateway_reachable

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Poller unexpected error: %s", exc)
            await asyncio.sleep(config.polling_interval_seconds)

    async def _poll_once(self) -> None:
        gateway = _load_gateway()
        if not gateway:
            self._gateway_reachable = False
            return

        client = DynaliteClient(ip=gateway["ip"], scheme=gateway.get("scheme", "http"), verify_ssl=gateway.get("verify_ssl", True))
        areas = _load_areas()

        for area in areas:
            area_id: int = area["id"]
            area_name: str = area["name"]
            area_type: str = area.get("type", "lighting")

            try:
                if area_type == "thermostat":
                    await self._poll_thermostat(client, area_id, area_name)
                else:
                    await self._poll_lighting(client, area_id, area_name, area)
                self._gateway_reachable = True
            except DynaliteError as exc:
                logger.warning("Poll failed for area %d: %s", area_id, exc)
                self._gateway_reachable = False

    async def _poll_lighting(
        self,
        client: DynaliteClient,
        area_id: int,
        area_name: str,
        area_config: dict[str, Any],
    ) -> None:
        preset = await client.get_preset(area_id)
        num_channels: int = area_config.get("channels", 1)

        channels: list[dict[str, Any]] = []
        for ch in range(1, num_channels + 1):
            level = await client.get_channel_level(area_id, ch)
            if level is not None:
                channels.append({"channel": ch, "level": level})
                try:
                    self._writer.write_level(area_id, area_name, ch, level)
                except Exception as exc:
                    logger.debug("InfluxDB write_level failed: %s", exc)

        if preset is not None:
            try:
                self._writer.write_preset(area_id, area_name, preset)
            except Exception as exc:
                logger.debug("InfluxDB write_preset failed: %s", exc)

        self._state[area_id] = {
            "type": "lighting",
            "current_preset": preset,
            "channels": channels,
        }

    async def _poll_thermostat(
        self,
        client: DynaliteClient,
        area_id: int,
        area_name: str,
    ) -> None:
        temperature = await client.get_temperature(area_id)
        setpoint = await client.get_setpoint(area_id)

        if temperature is not None and setpoint is not None:
            try:
                self._writer.write_temperature(area_id, area_name, temperature, setpoint)
            except Exception as exc:
                logger.debug("InfluxDB write_temperature failed: %s", exc)

        self._state[area_id] = {
            "type": "thermostat",
            "current_temp": temperature,
            "setpoint": setpoint,
        }


# Module-level singleton shared across the application.
poller = Poller()
