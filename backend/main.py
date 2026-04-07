from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from poller import poller
from routers import areas, config_areas, gateway, history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("DynaDash backend starting — launching poller")
    poller.start()
    yield
    logger.info("DynaDash backend shutting down — stopping poller")
    poller.stop()


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


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
