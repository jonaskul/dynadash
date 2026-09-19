from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

import auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class PasswordIn(BaseModel):
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


def _client(request: Request) -> str:
    # nginx sets X-Real-IP; the socket address is the fallback for direct hits.
    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.SESSION_TTL,
        httponly=True,
        samesite="lax",
        path="/",
        # Secure is deliberately off: the dashboard is served over plain HTTP on
        # the LAN, and a Secure cookie would never be sent back. Turn this on
        # together with HTTPS if the dashboard is ever exposed beyond the LAN.
        secure=False,
    )


def _require_length(password: str) -> None:
    if len(password) < auth.MIN_PASSWORD_LENGTH:
        raise HTTPException(
            422,
            f"Password must be at least {auth.MIN_PASSWORD_LENGTH} characters.",
        )


@router.get("/status")
async def auth_status(request: Request) -> dict[str, Any]:
    """Whether a password exists, and whether this caller is signed in."""
    return {
        "configured": auth.is_configured(),
        "authenticated": auth.validate_session(
            request.cookies.get(auth.COOKIE_NAME)
        ),
    }


@router.post("/setup")
async def setup_password(body: PasswordIn, response: Response) -> dict[str, Any]:
    """Set the first password. Only possible while none exists."""
    if auth.is_configured():
        raise HTTPException(409, "A password is already set.")
    _require_length(body.password)
    hashed = await asyncio.to_thread(auth.hash_password, body.password)
    auth.set_password_hash(hashed)
    token = await asyncio.to_thread(auth.create_session)
    _set_session_cookie(response, token)
    logger.info("Dashboard password created — API is now protected")
    return {"ok": True}


@router.post("/login")
async def login(
    body: PasswordIn, request: Request, response: Response
) -> dict[str, Any]:
    if not auth.is_configured():
        raise HTTPException(409, "No password has been set yet.")

    client = _client(request)
    wait = auth.lockout_remaining(client)
    if wait > 0:
        raise HTTPException(
            429, f"Too many failed attempts. Try again in {int(wait) + 1}s."
        )

    stored = auth.stored_hash() or ""
    # Hashing is deliberately slow, so it belongs in a worker thread rather than
    # on the event loop.
    ok = await asyncio.to_thread(auth.verify_password, body.password, stored)
    if not ok:
        auth.record_failure(client)
        logger.warning("Failed dashboard login from %s", client)
        raise HTTPException(401, "Incorrect password.")

    auth.clear_failures(client)
    token = await asyncio.to_thread(auth.create_session)
    _set_session_cookie(response, token)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, Any]:
    await asyncio.to_thread(
        auth.delete_session, request.cookies.get(auth.COOKIE_NAME)
    )
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/password")
async def change_password(
    body: ChangePasswordIn, response: Response
) -> dict[str, Any]:
    _require_length(body.new_password)
    stored = auth.stored_hash() or ""
    ok = await asyncio.to_thread(auth.verify_password, body.current_password, stored)
    if not ok:
        raise HTTPException(401, "Current password is incorrect.")

    hashed = await asyncio.to_thread(auth.hash_password, body.new_password)
    auth.set_password_hash(hashed)
    # Every existing session is dropped, including this one: a password change
    # is how you lock out a device you no longer trust.
    await asyncio.to_thread(auth.delete_all_sessions)
    token = await asyncio.to_thread(auth.create_session)
    _set_session_cookie(response, token)
    logger.info("Dashboard password changed — all other sessions signed out")
    return {"ok": True}
