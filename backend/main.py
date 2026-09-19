from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import auth
import influx_maintenance
import influx_store
from poller import poller
from routers import areas, backup, config_areas, gateway, history, settings, update
from routers import auth as auth_router
from tibber import router as tibber_router
from tibber_db import get_setting, init_db
from tibber_pulse import pulse_manager, rest_poller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WATCHDOG_INTERVAL = 60
MAINTENANCE_INTERVAL = 6 * 3600

# The only API paths reachable without a session. Everything else under /api/ is
# guarded, so a router added later is protected by default rather than by
# somebody remembering to guard it.
OPEN_PATHS = frozenset({
    "/api/health",
    "/api/auth/status",
    "/api/auth/login",
    "/api/auth/setup",
})


async def _watchdog() -> None:
    """Re-check the long-lived background tasks once a minute.

    Nothing watches the watchdog, so every iteration has to survive whatever
    the checks throw at it — an exception escaping here would quietly take the
    self-healing with it and leave the failure it was meant to catch in place.
    """
    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL)
        try:
            logger.info(
                "watchdog: %d live task(s), %d point(s) queued for InfluxDB",
                len(asyncio.all_tasks()),
                influx_store.pending(),
            )
            influx_store.ensure_running()
            poller.ensure_running()
            pulse_manager.ensure_running()
            rest_poller.ensure_running()
            auth.purge_expired()
        except asyncio.CancelledError:
            raise
        except BaseException:
            logger.exception("Watchdog iteration failed — continuing")


async def _maintenance() -> None:
    """Keep the rollup task installed and prune raw Pulse data it has covered.

    Everything here talks to InfluxDB synchronously, so it runs in worker
    threads; and like the watchdog it has to survive its own failures, since a
    database that is briefly unreachable must not end the loop.
    """
    while True:
        try:
            await asyncio.to_thread(influx_maintenance.ensure_rollup_task)
            cutoff = await asyncio.to_thread(influx_maintenance.prune_raw_pulse)
            if cutoff is None:
                logger.info("maintenance: rollup checked, nothing to prune")
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            logger.warning("InfluxDB maintenance failed: %s", exc)
        await asyncio.sleep(MAINTENANCE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("DynaDash backend starting — launching poller")
    init_db()
    auth.init()
    await influx_store.start()
    await poller.start()
    token = get_setting("tibber_token")
    home_id = get_setting("tibber_home_id")
    if token and home_id:
        logger.info("Starting Tibber services (home %s)", home_id)
        await pulse_manager.start(token, home_id)
        await rest_poller.start(token, home_id)
    watchdog = asyncio.create_task(_watchdog(), name="tibber-watchdog")
    maintenance = asyncio.create_task(_maintenance(), name="influx-maintenance")
    yield
    logger.info("DynaDash backend shutting down")
    watchdog.cancel()
    maintenance.cancel()
    poller.stop()
    pulse_manager.stop()
    rest_poller.stop()
    await influx_store.stop()


app = FastAPI(
    title="DynaDash API",
    description="Home automation dashboard for Dynalite lighting and HVAC systems",
    version="1.0.0",
    lifespan=lifespan,
)

# Limited to localhost and private ranges. A wildcard cannot be combined with
# credentials — browsers reject that pairing — and the session cookie needs
# credentials to work at all.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"^https?://("
        r"localhost|127\.0\.0\.1|\[::1\]|"
        r"10\.[\d.]+|"
        r"192\.168\.[\d.]+|"
        r"172\.(1[6-9]|2\d|3[01])\.[\d.]+|"
        r"[\w-]+\.local"
        r")(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_session(request: Request, call_next):
    """Refuse any API request that does not carry a valid session."""
    path = request.url.path
    if (
        request.method == "OPTIONS"
        or not path.startswith("/api/")
        or path in OPEN_PATHS
    ):
        return await call_next(request)

    if not auth.is_configured():
        # Nothing to check against yet. The browser shows the create-password
        # screen, and only /api/auth/setup will get through until it is done.
        return JSONResponse({"detail": "setup_required"}, status_code=401)

    if not auth.validate_session(request.cookies.get(auth.COOKIE_NAME)):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)

    return await call_next(request)


app.include_router(auth_router.router)
app.include_router(gateway.router)
app.include_router(areas.router)
app.include_router(config_areas.router)
app.include_router(history.router)
app.include_router(settings.router)
app.include_router(backup.router)
app.include_router(tibber_router)
app.include_router(update.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
