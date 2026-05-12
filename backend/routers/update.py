from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from typing import Any

from fastapi import APIRouter, BackgroundTasks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/update")

# Root of the repo (parent of backend/)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=APP_DIR, capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip()


@router.get("")
async def check_update() -> dict[str, Any]:
    await asyncio.to_thread(
        subprocess.run,
        ["git", "fetch", "origin", "main", "--depth=50"],
        cwd=APP_DIR, capture_output=True, timeout=30,
    )
    current = await asyncio.to_thread(_git, "rev-parse", "HEAD")
    latest = await asyncio.to_thread(_git, "rev-parse", "FETCH_HEAD")

    commits: list[dict[str, str]] = []
    if current != latest:
        log = await asyncio.to_thread(
            _git,
            "log", f"{current}..FETCH_HEAD",
            "--pretty=format:%H|%s|%as",  # %as = author date short (YYYY-MM-DD)
        )
        for line in log.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"sha": parts[0][:7], "message": parts[1], "date": parts[2]})

    return {
        "up_to_date": current == latest,
        "current_sha": current[:7],
        "latest_sha": latest[:7],
        "commits": commits,
    }


def _run_update() -> None:
    import time
    time.sleep(1)  # let the HTTP response flush before we restart
    cmd = (
        f"git -C {APP_DIR} reset --hard FETCH_HEAD && "
        f"bash {APP_DIR}/update.sh --skip-pull --force"
    )
    subprocess.Popen(["bash", "-c", cmd], cwd=APP_DIR)


@router.post("/apply")
async def apply_update(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(_run_update)
    return {"status": "updating"}
