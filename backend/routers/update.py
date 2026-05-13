from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

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
    fetch = await asyncio.to_thread(
        subprocess.run,
        ["git", "fetch", "origin", "main", "--depth=50"],
        cwd=APP_DIR, capture_output=True, text=True, timeout=30,
    )
    if fetch.returncode != 0:
        detail = fetch.stderr.strip() or "git fetch failed — check network connectivity"
        logger.warning("git fetch failed: %s", detail)
        raise HTTPException(status_code=503, detail=detail)

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
    # systemd-run places the process in its own transient unit/cgroup so it
    # survives when update.sh restarts the dynadash-backend service (which
    # would otherwise kill child processes via cgroup teardown).
    subprocess.Popen(
        ["systemd-run", "--no-block", "--unit=dynadash-gui-update",
         "bash", "-c", cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@router.post("/apply")
async def apply_update(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(_run_update)
    return {"status": "updating"}
