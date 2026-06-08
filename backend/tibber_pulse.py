from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

import websockets
from influxdb_client import Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from config import config

logger = logging.getLogger(__name__)

_PULSE_FIELDS = [
    "power", "lastMeterConsumption", "accumulatedConsumption",
    "accumulatedCost", "accumulatedReward", "minPower", "averagePower",
    "maxPower", "powerProduction", "minPowerProduction", "maxPowerProduction",
    "lastMeterProduction", "powerFactor", "voltagePhase1", "voltagePhase2",
    "voltagePhase3", "currentL1", "currentL2", "currentL3",
]

_LIVE_MEASUREMENT_QUERY = """subscription($homeId: ID!) {
    liveMeasurement(homeId: $homeId) {
        timestamp power lastMeterConsumption accumulatedConsumption
        accumulatedCost accumulatedReward currency minPower averagePower
        maxPower powerProduction minPowerProduction maxPowerProduction
        lastMeterProduction powerFactor voltagePhase1 voltagePhase2
        voltagePhase3 currentL1 currentL2 currentL3
    }
}"""

_PRICE_QUERY = """{{ viewer {{ home(id: "{home_id}") {{
    currentSubscription {{ priceInfo {{
        current {{ total energy tax startsAt level currency }}
        today   {{ total energy tax startsAt level currency }}
        tomorrow {{ total energy tax startsAt level currency }}
    }} }}
}} }} }}"""

_CONSUMPTION_QUERY = """{{ viewer {{ home(id: "{home_id}") {{
    consumption(resolution: HOURLY, last: 720) {{
        nodes {{ from to cost unitPrice consumption currency }}
    }}
}} }} }}"""


def _influx_client():
    from influxdb_client import InfluxDBClient
    return InfluxDBClient(
        url=config.influxdb.url,
        token=config.influxdb.token,
        org=config.influxdb.org,
    )


# ---------------------------------------------------------------------------
# WebSocket Pulse manager
# ---------------------------------------------------------------------------

class TibberPulseManager:
    """Manages the Tibber Pulse WebSocket subscription with auto-reconnect."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task[None]] = None
        self._connected: bool = False
        self._last_measurement: Optional[dict[str, Any]] = None
        self._last_ts: Optional[str] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_measurement(self) -> Optional[dict[str, Any]]:
        return self._last_measurement

    @property
    def last_ts(self) -> Optional[str]:
        return self._last_ts

    async def start(self, token: str, home_id: str) -> None:
        self.stop()
        self._task = asyncio.create_task(self._run(token, home_id))

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        self._connected = False

    async def _run(self, token: str, home_id: str) -> None:
        backoff = 2
        while True:
            try:
                await self._connect(token, home_id)
                backoff = 2
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                logger.warning("Pulse disconnected: %s — retry in %ds", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _connect(self, token: str, home_id: str) -> None:
        url = "wss://websocket-api.tibber.com/v1-beta/gql/subscriptions"
        logger.info("Pulse: connecting to Tibber WebSocket (home %s)", home_id)

        async with websockets.connect(
            url,
            subprotocols=["graphql-transport-ws"],
            additional_headers={"Authorization": f"Bearer {token}"},
            open_timeout=30,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            logger.info("Pulse: WebSocket opened, sending connection_init")
            await ws.send(json.dumps({
                "type": "connection_init",
                "payload": {"token": token},
            }))

            # Wait for connection_ack
            self._connected = False
            ack_received = False
            deadline = asyncio.get_running_loop().time() + 30
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    raise RuntimeError("Timeout waiting for connection_ack from Tibber")
                msg = json.loads(raw)
                mtype = msg.get("type")
                logger.info("Pulse: handshake message: %s", mtype)
                if mtype == "connection_ack":
                    ack_received = True
                    break
                if mtype in ("ka", "ping"):
                    continue
                raise RuntimeError(f"Unexpected handshake message: {msg}")

            if not ack_received:
                raise RuntimeError("Timeout waiting for connection_ack from Tibber")

            # Subscribe using graphql-transport-ws "subscribe" type
            await ws.send(json.dumps({
                "type": "subscribe",
                "id": "1",
                "payload": {
                    "query": _LIVE_MEASUREMENT_QUERY,
                    "variables": {"homeId": home_id},
                },
            }))
            self._connected = True
            logger.info("Tibber Pulse subscribed for home %s", home_id)

            async for raw in ws:
                msg = json.loads(raw)
                mtype = msg.get("type")
                if mtype == "next":  # graphql-transport-ws data message
                    lm = msg.get("payload", {}).get("data", {}).get("liveMeasurement")
                    if lm:
                        self._last_measurement = lm
                        self._last_ts = lm.get("timestamp")
                        await asyncio.to_thread(self._write_pulse, home_id, lm)
                elif mtype == "ka":
                    pass
                elif mtype == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
                elif mtype == "pong":
                    pass
                elif mtype == "error":
                    logger.error("Pulse subscription error: %s", msg)
                elif mtype == "complete":
                    logger.info("Pulse subscription completed")
                    break

    def _write_pulse(self, home_id: str, data: dict[str, Any]) -> None:
        ts_str = data.get("timestamp", "")
        if not ts_str:
            return
        point = (
            Point("tibber_pulse")
            .tag("home_id", home_id)
            .time(
                datetime.fromisoformat(ts_str.replace("Z", "+00:00")),
                WritePrecision.S,
            )
        )
        for field in _PULSE_FIELDS:
            v = data.get(field)
            if v is not None:
                point = point.field(field, float(v))
        try:
            with _influx_client() as client:
                client.write_api(write_options=SYNCHRONOUS).write(
                    bucket=config.influxdb.bucket, record=point
                )
        except Exception as exc:
            logger.warning("InfluxDB pulse write failed: %s", exc)


# ---------------------------------------------------------------------------
# Hourly REST poller (prices + consumption → InfluxDB)
# ---------------------------------------------------------------------------

class TibberPoller:
    """Polls the Tibber REST API hourly and writes prices/consumption to InfluxDB."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self, token: str, home_id: str) -> None:
        self.stop()
        self._task = asyncio.create_task(self._loop(token, home_id))

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self, token: str, home_id: str) -> None:
        while True:
            try:
                await self._poll(token, home_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Tibber REST poll failed: %s", exc)
            await asyncio.sleep(3600)

    async def _poll(self, token: str, home_id: str) -> None:
        import httpx
        headers = {"Authorization": f"Bearer {token}"}
        gql_url = "https://api.tibber.com/v1-beta/gql"

        async with httpx.AsyncClient(timeout=15.0) as http:
            # Prices
            r = await http.post(
                gql_url,
                json={"query": _PRICE_QUERY.format(home_id=home_id)},
                headers=headers,
            )
            r.raise_for_status()
            price_data = r.json()
            if "errors" not in price_data:
                info = (
                    price_data["data"]["viewer"]["home"]
                    ["currentSubscription"]["priceInfo"]
                )
                entries = info.get("today", []) + info.get("tomorrow", [])
                await asyncio.to_thread(self._write_prices, entries)

            # Consumption
            r = await http.post(
                gql_url,
                json={"query": _CONSUMPTION_QUERY.format(home_id=home_id)},
                headers=headers,
            )
            r.raise_for_status()
            cons_data = r.json()
            if "errors" not in cons_data:
                nodes = (
                    cons_data["data"]["viewer"]["home"]
                    ["consumption"]["nodes"]
                )
                await asyncio.to_thread(self._write_consumption, home_id, nodes)

        logger.info("Tibber REST poll complete")

    def _write_prices(self, entries: list[dict[str, Any]]) -> None:
        points = []
        for e in entries:
            if not e or not e.get("startsAt"):
                continue
            points.append(
                Point("tibber_price")
                .tag("level", e.get("level", ""))
                .tag("currency", e.get("currency", ""))
                .field("total", float(e["total"]))
                .field("energy", float(e["energy"]))
                .field("tax", float(e["tax"]))
                .time(
                    datetime.fromisoformat(e["startsAt"].replace("Z", "+00:00")),
                    WritePrecision.S,
                )
            )
        if not points:
            return
        try:
            with _influx_client() as client:
                client.write_api(write_options=SYNCHRONOUS).write(
                    bucket=config.influxdb.bucket, record=points
                )
        except Exception as exc:
            logger.warning("InfluxDB price write failed: %s", exc)

    def _write_consumption(
        self, home_id: str, nodes: list[dict[str, Any]]
    ) -> None:
        points = []
        for n in nodes:
            if not n or not n.get("from"):
                continue
            points.append(
                Point("tibber_consumption")
                .tag("home_id", home_id)
                .tag("currency", n.get("currency", ""))
                .field("consumption", float(n["consumption"] or 0))
                .field("cost", float(n["cost"] or 0))
                .field("unitPrice", float(n["unitPrice"] or 0))
                .time(
                    datetime.fromisoformat(n["from"].replace("Z", "+00:00")),
                    WritePrecision.S,
                )
            )
        if not points:
            return
        try:
            with _influx_client() as client:
                client.write_api(write_options=SYNCHRONOUS).write(
                    bucket=config.influxdb.bucket, record=points
                )
        except Exception as exc:
            logger.warning("InfluxDB consumption write failed: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

pulse_manager = TibberPulseManager()
rest_poller = TibberPoller()
