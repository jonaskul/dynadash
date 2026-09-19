"""The API must be closed to anyone without a session.

Driven through the real ASGI app so the middleware is what is being tested,
rather than a stand-in for it.
"""

from __future__ import annotations

from typing import AsyncIterator

import httpx
import pytest

import auth
from main import OPEN_PATHS, app

PASSWORD = "correct-horse-battery"
pytestmark = pytest.mark.usefixtures("temp_db", "fast_scrypt")

# Routes that change lights, expose stored credentials, or run the updater.
GUARDED = [
    ("GET", "/api/areas"),
    ("GET", "/api/gateway"),
    ("GET", "/api/energy/status"),
    ("GET", "/api/energy/settings"),
    ("GET", "/api/config/areas"),
    ("GET", "/api/settings"),
    ("GET", "/api/backup/export"),
    ("GET", "/api/update"),
    ("POST", "/api/update/apply"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/password"),
]


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _sign_in(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/auth/setup", json={"password": PASSWORD})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("method,path", GUARDED)
async def test_guarded_before_a_password_exists(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    r = await client.request(method, path)
    assert r.status_code == 401
    assert r.json()["detail"] == "setup_required"


@pytest.mark.parametrize("method,path", GUARDED)
async def test_guarded_without_a_session(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    await _sign_in(client)
    client.cookies.clear()

    r = await client.request(method, path)
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthorized"


async def test_health_stays_open(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200


async def test_a_forged_cookie_is_refused(client: httpx.AsyncClient) -> None:
    await _sign_in(client)
    client.cookies.clear()
    client.cookies.set("dynadash_session", "forged-token-value")

    r = await client.get("/api/areas")
    assert r.status_code == 401


async def test_setup_then_access(client: httpx.AsyncClient) -> None:
    await _sign_in(client)
    r = await client.get("/api/areas")
    assert r.status_code == 200


async def test_setup_cannot_be_run_twice(client: httpx.AsyncClient) -> None:
    await _sign_in(client)
    r = await client.post("/api/auth/setup", json={"password": "another-long-one"})
    assert r.status_code == 409


async def test_short_passwords_are_refused(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/auth/setup", json={"password": "short"})
    assert r.status_code == 422
    assert not auth.is_configured(), "a rejected password was still stored"


async def test_session_cookie_attributes(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/auth/setup", json={"password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()

    # HttpOnly keeps the token away from any script on the page; Lax keeps it off
    # cross-site requests, which is what would otherwise let another page on the
    # network act as the signed-in user.
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


async def test_login_and_logout(client: httpx.AsyncClient) -> None:
    await _sign_in(client)
    await client.post("/api/auth/logout")
    assert (await client.get("/api/areas")).status_code == 401

    r = await client.post("/api/auth/login", json={"password": PASSWORD})
    assert r.status_code == 200
    assert (await client.get("/api/areas")).status_code == 200


async def test_login_with_the_wrong_password(client: httpx.AsyncClient) -> None:
    await _sign_in(client)
    client.cookies.clear()

    r = await client.post("/api/auth/login", json={"password": "not-the-password"})
    assert r.status_code == 401
    assert (await client.get("/api/areas")).status_code == 401


async def test_repeated_failures_are_locked_out(client: httpx.AsyncClient) -> None:
    await _sign_in(client)
    client.cookies.clear()

    codes = []
    for _ in range(auth.MAX_FAILURES + 2):
        r = await client.post("/api/auth/login", json={"password": "wrong-password"})
        codes.append(r.status_code)

    assert codes[: auth.MAX_FAILURES] == [401] * auth.MAX_FAILURES
    assert 429 in codes[auth.MAX_FAILURES :]

    # The lockout has to hold even for the right password, or it is no lockout.
    r = await client.post("/api/auth/login", json={"password": PASSWORD})
    assert r.status_code == 429


async def test_changing_the_password_signs_other_devices_out(
    client: httpx.AsyncClient,
) -> None:
    await _sign_in(client)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        other.cookies.update(client.cookies)
        assert (await other.get("/api/areas")).status_code == 200

        r = await client.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": "a-brand-new-secret"},
        )
        assert r.status_code == 200

        assert (await other.get("/api/areas")).status_code == 401
        assert (await client.get("/api/areas")).status_code == 200

    r = await client.post("/api/auth/login", json={"password": PASSWORD})
    assert r.status_code == 401, "the old password still works"


async def test_password_change_requires_the_current_one(
    client: httpx.AsyncClient,
) -> None:
    await _sign_in(client)
    r = await client.post(
        "/api/auth/password",
        json={"current_password": "wrong-one-entirely", "new_password": "long-enough-x"},
    )
    assert r.status_code == 401


def _declared_api_operations() -> list[tuple[str, str]]:
    """Every (method, path) the app actually serves under /api/.

    Taken from the OpenAPI schema rather than app.routes, which in this FastAPI
    version keeps included routers as opaque entries instead of flattening them.
    """
    operations: list[tuple[str, str]] = []
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method in methods:
            if method.upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                operations.append((method.upper(), path))
    return operations


def test_the_open_list_is_exactly_what_it_should_be() -> None:
    """Widening the open list is the one way to expose a route by accident.

    The walk below skips whatever is listed here, so this is where growing the
    list has to be noticed and argued for.
    """
    assert OPEN_PATHS == {
        "/api/health",
        "/api/auth/status",
        "/api/auth/login",
        "/api/auth/setup",
    }


def test_the_open_list_only_names_routes_that_exist() -> None:
    declared = {path for _, path in _declared_api_operations()}
    missing = OPEN_PATHS - declared
    assert not missing, f"OPEN_PATHS names routes that do not exist: {missing}"


async def test_every_api_route_is_guarded_or_deliberately_open(
    client: httpx.AsyncClient,
) -> None:
    """A router added later must not end up reachable by accident.

    This walks everything the app serves, so a new endpoint is covered the
    moment it exists — without anyone having to remember to add it here.
    """
    await _sign_in(client)
    client.cookies.clear()

    reachable: list[tuple[str, str]] = []
    for method, path in _declared_api_operations():
        if path in OPEN_PATHS:
            continue
        # Path parameters are never validated: the guard runs first.
        concrete = path.replace("{area_id}", "1").replace("{channel}", "1")
        r = await client.request(method, concrete)
        if r.status_code != 401:
            reachable.append((method, path, r.status_code))  # type: ignore[arg-type]

    assert not reachable, f"reachable without a session: {reachable}"
