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
ADMIN_HELPER = os.path.join(APP_DIR, "scripts", "dynadash-admin")


def _admin(action: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run one privileged update action through the root-owned helper.

    The backend is unprivileged, so git and systemd are reached via sudo against
    a fixed script with a fixed set of actions. Nothing the caller supplies ends
    up in the command line.
    """
    return subprocess.run(
        ["sudo", "-n", ADMIN_HELPER, action],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _fail(result: subprocess.CompletedProcess[str], what: str) -> None:
    detail = (result.stderr or result.stdout or "").strip()
    if "sudo" in detail and "password" in detail.lower():
        detail = (
            "The backend is not allowed to run the update helper. "
            "Re-run install.sh to reinstall /etc/sudoers.d/dynadash."
        )
    logger.warning("%s failed: %s", what, detail)
    raise HTTPException(status_code=503, detail=detail or f"{what} failed")


@router.get("")
async def check_update() -> dict[str, Any]:
    fetch = await asyncio.to_thread(_admin, "fetch")
    if fetch.returncode != 0:
        _fail(fetch, "git fetch")

    revs = await asyncio.to_thread(_admin, "revs")
    if revs.returncode != 0:
        _fail(revs, "git rev-parse")

    current = latest = ""
    commits: list[dict[str, str]] = []
    for line in revs.stdout.splitlines():
        if line.startswith("current "):
            current = line[8:].strip()
        elif line.startswith("latest "):
            latest = line[7:].strip()
        elif line.startswith("commit "):
            parts = line[7:].split("|", 2)
            if len(parts) == 3:
                commits.append(
                    {"sha": parts[0][:7], "message": parts[1], "date": parts[2]}
                )

    if not current or not latest:
        raise HTTPException(503, "Could not determine the installed revision.")

    return {
        "up_to_date": current == latest,
        "current_sha": current[:7],
        "latest_sha": latest[:7],
        "commits": commits,
    }


def _run_update() -> None:
    import time
    time.sleep(1)  # let the HTTP response flush before the service restarts
    result = _admin("apply")
    if result.returncode != 0:
        logger.error(
            "Update could not be started: %s",
            (result.stderr or result.stdout or "").strip(),
        )


@router.post("/apply")
async def apply_update(background_tasks: BackgroundTasks) -> dict[str, str]:
    background_tasks.add_task(_run_update)
    return {"status": "updating"}
