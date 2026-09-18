from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Optional

import httpx
import websockets
from influxdb_client import Point, WritePrecision

import influx_store

logger = logging.getLogger(__name__)

_REST_URL = "https://api.tibber.com/v1-beta/gql"

# Tibber asks API clients to identify themselves, and documents the real-time
# endpoint as discoverable rather than fixed — so we ask for it instead of
# hardcoding a host that can be retired without notice.
_USER_AGENT = "DynaDash/1.0"
_WS_URL_QUERY = "{ viewer { websocketSubscriptionUrl } }"
_WS_URL_FALLBACK = "wss://websocket-api.tibber.com/v1-beta/gql/subscriptions"

# Tibber pushes a liveMeasurement every ~2s. A minute and a half of silence
# means the socket is dead even when it never raised an exception.
_STALE_AFTER = 90.0
_BACKOFF_MIN = 5
_BACKOFF_MAX = 60
# A connection that lasted this long counts as healthy, so the next failure
# starts backing off from scratch again.
_BACKOFF_RESET = 120.0

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


async def _subscription_url(token: str) -> str:
    """Ask Tibber which WebSocket host to use, falling back to the known one."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            r = await http.post(
                _REST_URL,
                json={"query": _WS_URL_QUERY},
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": _USER_AGENT,
                },
            )
            r.raise_for_status()
            url = (r.json().get("data") or {}).get("viewer", {}).get(
                "websocketSubscriptionUrl"
            )
            if url:
                return url
    except Exception as exc:
        logger.warning("Could not look up Pulse WebSocket URL (%s) — using default", exc)
    return _WS_URL_FALLBACK


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
        self._token: Optional[str] = None
        self._home_id: Optional[str] = None
        # Liveness is tracked against our own monotonic clock rather than the
        # meter's timestamp, so neither a drifting meter clock nor a socket that
        # connects and then never delivers anything can hide a stalled feed.
        self._last_activity: Optional[float] = None
        self._last_data: Optional[float] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_measurement(self) -> Optional[dict[str, Any]]:
        return self._last_measurement

    @property
    def last_ts(self) -> Optional[str]:
        return self._last_ts

    @property
    def data_age(self) -> Optional[float]:
        """Seconds since the last measurement arrived, or None if none has."""
        if self._last_data is None:
            return None
        return time.monotonic() - self._last_data

    async def start(self, token: str, home_id: str) -> None:
        self._token = token
        self._home_id = home_id
        self._restart()

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        self._connected = False
        self._last_activity = None

    def _restart(self) -> None:
        self.stop()
        self._task = asyncio.create_task(
            self._run(self._token, self._home_id), name="tibber-pulse"
        )

    def ensure_running(self) -> None:
        if not (self._token and self._home_id):
            return
        task = self._task
        if task is None or task.done():
            logger.warning("Pulse task was dead — restarting")
            self._restart()
            return
        # The task can be alive and still be going nowhere: a half-open TCP
        # connection leaves the read loop waiting on a socket that will never
        # produce another frame, and nothing raises. Only silence reveals it.
        if self._last_activity is None:
            return
        idle = time.monotonic() - self._last_activity
        if idle > _STALE_AFTER:
            logger.warning("Pulse silent for %.0fs — forcing reconnect", idle)
            self._restart()

    async def _run(self, token: str, home_id: str) -> None:
        backoff = _BACKOFF_MIN
        while True:
            started = time.monotonic()
            try:
                await self._connect(token, home_id)
                logger.info("Pulse: stream closed by Tibber")
            except asyncio.CancelledError:
                self._connected = False
                raise
            except BaseException as exc:
                logger.warning("Pulse disconnected: %s", exc)
            self._connected = False
            # A connection that survived a while earns a short backoff again.
            # One that died immediately must not be retried immediately, or a
            # server closing on us turns this loop into a reconnect storm.
            if time.monotonic() - started >= _BACKOFF_RESET:
                backoff = _BACKOFF_MIN
            logger.info("Pulse: reconnecting in %ds", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)

    async def _connect(self, token: str, home_id: str) -> None:
        url = await _subscription_url(token)
        logger.info("Pulse: connecting to %s (home %s)", url, home_id)

        async with websockets.connect(
            url,
            subprotocols=["graphql-transport-ws"],
            additional_headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": _USER_AGENT,
            },
            open_timeout=30,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            self._last_activity = time.monotonic()
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

            # Everything in this loop is CPU-only — the InfluxDB write is handed
            # to a queue rather than awaited. If it ever waited on the database
            # again, unread frames would pile up behind it, pongs among them,
            # and Tibber would drop us on a keepalive timeout.
            async for raw in ws:
                self._last_activity = time.monotonic()
                msg = json.loads(raw)
                mtype = msg.get("type")
                if mtype == "next":  # graphql-transport-ws data message
                    lm = msg.get("payload", {}).get("data", {}).get("liveMeasurement")
                    if lm:
                        self._last_measurement = lm
                        self._last_ts = lm.get("timestamp")
                        self._last_data = time.monotonic()
                        self._queue_pulse(home_id, lm)
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

    def _queue_pulse(self, home_id: str, data: dict[str, Any]) -> None:
        """Hand one measurement to the background writer. Must not block."""
        ts_str = data.get("timestamp", "")
        if not ts_str:
            return
        try:
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
        except Exception as exc:
            logger.warning("Skipping malformed Pulse measurement: %s", exc)
            return
        influx_store.enqueue(point)


# ---------------------------------------------------------------------------
# Hourly REST poller (prices + consumption → InfluxDB)
# ---------------------------------------------------------------------------

class TibberPoller:
    """Polls the Tibber REST API hourly and writes prices/consumption to InfluxDB."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task[None]] = None
        self._token: Optional[str] = None
        self._home_id: Optional[str] = None

    async def start(self, token: str, home_id: str) -> None:
        self._token = token
        self._home_id = home_id
        self.stop()
        self._task = asyncio.create_task(self._loop(token, home_id))

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def ensure_running(self) -> None:
        if self._token and self._home_id:
            if self._task is None or self._task.done():
                logger.warning("REST poller task was dead — restarting")
                self._task = asyncio.create_task(self._loop(self._token, self._home_id))

    async def _loop(self, token: str, home_id: str) -> None:
        while True:
            try:
                await self._poll(token, home_id)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                logger.warning("Tibber REST poll failed: %s", exc)
            await asyncio.sleep(3600)

    async def _poll(self, token: str, home_id: str) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": _USER_AGENT,
        }
        gql_url = _REST_URL

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
            influx_store.write_points(points)
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
            influx_store.write_points(points)
        except Exception as exc:
            logger.warning("InfluxDB consumption write failed: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

pulse_manager = TibberPulseManager()
rest_poller = TibberPoller()
