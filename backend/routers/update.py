"""The dashboard's self-update endpoints.

The backend runs unprivileged and cannot touch git or systemd. Instead of giving
it sudo — which is setuid, and would rule out NoNewPrivileges on the service — it
drops a request file in its own data directory. A systemd path unit notices the
file and runs scripts/dynadash-admin as root, which writes the outcome back as
JSON. Nothing the caller supplies reaches a command line: the request carries one
of two fixed action words and a nonce used only to match the answer to the
question.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/update")

# Root of the repo (parent of backend/)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data")
REQUEST_FILE = os.path.join(DATA_DIR, "update-request")
STATUS_FILE = os.path.join(DATA_DIR, "update-status.json")

# nginx gives proxied requests 60s, so the wait has to finish inside that.
CHECK_TIMEOUT = 45.0
_POLL_INTERVAL = 0.25
# The helper claims a request by renaming it, which takes milliseconds once the
# path unit fires. A request still sitting untouched after this long means
# nothing is watching, and there is no point waiting out the full timeout.
UNCLAIMED_GRACE = 5.0

_NOT_WIRED = (
    "The update helper is not running. Re-run install.sh, or check "
    "'systemctl status dynadash-update.path'."
)


def _submit(action: str) -> str:
    """Drop a request for the privileged helper and return its nonce."""
    nonce = secrets.token_hex(16)
    tmp = f"{REQUEST_FILE}.{nonce}.tmp"
    with open(tmp, "w") as f:
        f.write(f"{nonce} {action}\n")
    # Rename into place so the path unit never sees a half-written request.
    os.replace(tmp, REQUEST_FILE)
    return nonce


def _read_status(nonce: str) -> Optional[dict[str, Any]]:
    """Return the helper's answer to *nonce*, or None if it has not landed."""
    try:
        with open(STATUS_FILE) as f:
            status = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return status if status.get("nonce") == nonce else None


async def _run_privileged(action: str, timeout: float) -> dict[str, Any]:
    """Submit a request and wait for the helper to answer it."""
    try:
        nonce = await asyncio.to_thread(_submit, action)
    except OSError as exc:
        logger.warning("Could not write the update request: %s", exc)
        raise HTTPException(503, f"Could not write the update request: {exc}")

    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL)
        status = await asyncio.to_thread(_read_status, nonce)
        if status is not None:
            return status

        # Still unclaimed well after the path unit should have fired: say so now
        # rather than making the dashboard sit there for the full timeout.
        if time.monotonic() - started > UNCLAIMED_GRACE:
            if await asyncio.to_thread(os.path.exists, REQUEST_FILE):
                logger.warning("Nothing claimed the %r request — is the path unit enabled?", action)
                raise HTTPException(503, _NOT_WIRED)

    logger.warning("Update helper did not answer a %r request in %.0fs", action, timeout)
    raise HTTPException(503, f"The update ({action}) did not finish within {timeout:.0f}s.")


@router.get("")
async def check_update() -> dict[str, Any]:
    status = await _run_privileged("check", CHECK_TIMEOUT)
    output = status.get("output", "")
    if not status.get("ok"):
        detail = output.strip() or "git fetch failed"
        logger.warning("Update check failed: %s", detail)
        raise HTTPException(503, detail)

    current = latest = ""
    commits: list[dict[str, str]] = []
    for line in output.splitlines():
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


def _request_apply() -> None:
    time.sleep(1)  # let the HTTP response flush before the service restarts
    try:
        _submit("apply")
    except OSError as exc:
        logger.error("Could not request the update: %s", exc)


@router.post("/apply")
async def apply_update(background_tasks: BackgroundTasks) -> dict[str, str]:
    # Deliberately not awaited: applying the update restarts this very process,
    # so there is nobody left to report back to.
    background_tasks.add_task(_request_apply)
    return {"status": "updating"}
