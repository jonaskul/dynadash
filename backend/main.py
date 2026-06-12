from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from poller import poller
from routers import areas, backup, config_areas, gateway, history, settings, update
from tibber import router as tibber_router
from tibber_db import get_setting, init_db
from tibber_pulse import pulse_manager, rest_poller

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _watchdog() -> None:
    while True:
        await asyncio.sleep(60)
        logger.info("asyncio live tasks: %d", len(asyncio.all_tasks()))
        pulse_manager.ensure_running()
        rest_poller.ensure_running()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("DynaDash backend starting — launching poller")
    init_db()
    await poller.start()
    token = get_setting("tibber_token")
    home_id = get_setting("tibber_home_id")
    if token and home_id:
        logger.info("Starting Tibber services (home %s)", home_id)
        await pulse_manager.start(token, home_id)
        await rest_poller.start(token, home_id)
    watchdog = asyncio.create_task(_watchdog(), name="tibber-watchdog")
    yield
    logger.info("DynaDash backend shutting down")
    watchdog.cancel()
    poller.stop()
    pulse_manager.stop()
    rest_poller.stop()


app = FastAPI(
    title="DynaDash API",
    description="Home automation dashboard for Dynalite lighting and HVAC systems",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow all origins — this runs on a private LAN with no external exposure.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
