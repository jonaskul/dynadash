from __future__ import annotations

import base64
from typing import Optional

import httpx


class DynaliteError(Exception):
    """Raised when communication with the Dynalite gateway fails."""


class DynaliteConnectionError(DynaliteError):
    """Raised when the gateway cannot be reached at the network level."""


class DynaliteClient:
    """Async HTTP client for the Dynalite Ethernet Gateway CGI API.

    Use as an async context manager to reuse a single TCP connection across
    all requests in a poll cycle, avoiding repeated TLS handshakes.
    """

    def __init__(
        self,
        ip: str,
        scheme: str = "http",
        verify_ssl: bool = True,
        username: str = "",
        password: str = "",
    ) -> None:
        self.base_url = f"{scheme}://{ip}"
        self._verify_ssl = verify_ssl
        self._headers: dict[str, str] = {}
        if username:
            creds = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._headers["Authorization"] = f"Basic {creds}"
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "DynaliteClient":
        self._http = httpx.AsyncClient(timeout=5.0, verify=self._verify_ssl)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(text: str) -> dict[str, str]:
        if text.strip() == ".":
            return {}
        result: dict[str, str] = {}
        for line in text.strip().splitlines():
            line = line.strip()
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
        return result

    async def _get(self, endpoint: str, params: dict[str, str | int]) -> dict[str, str]:
        url = f"{self.base_url}/{endpoint}"
        http = self._http
        close_after = False
        if http is None:
            http = httpx.AsyncClient(timeout=5.0, verify=self._verify_ssl)
            close_after = True
        try:
            response = await http.get(url, params=params, headers=self._headers)
            response.raise_for_status()
            return self._parse_response(response.text)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise DynaliteConnectionError(f"Cannot reach gateway: {exc}") from exc
        except httpx.HTTPError as exc:
            raise DynaliteError(f"Gateway request failed: {exc}") from exc
        finally:
            if close_after:
                await http.aclose()

    async def _post(self, endpoint: str, params: dict[str, str | int]) -> dict[str, str]:
        url = f"{self.base_url}/{endpoint}"
        http = self._http
        close_after = False
        if http is None:
            http = httpx.AsyncClient(timeout=5.0, verify=self._verify_ssl)
            close_after = True
        try:
            response = await http.post(url, params=params, headers=self._headers)
            response.raise_for_status()
            return self._parse_response(response.text)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise DynaliteConnectionError(f"Cannot reach gateway: {exc}") from exc
        except httpx.HTTPError as exc:
            raise DynaliteError(f"Gateway request failed: {exc}") from exc
        finally:
            if close_after:
                await http.aclose()

    async def _set(self, params: dict[str, str | int]) -> dict[str, str]:
        return await self._get("SetDyNet.cgi", params)

    async def _query(self, params: dict[str, str | int]) -> dict[str, str]:
        return await self._get("GetDyNet.cgi", params)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_preset(self, area: int) -> Optional[int]:
        result = await self._query({"a": area, "p": ""})
        if "p" in result and result["p"]:
            try:
                return int(result["p"])
            except ValueError:
                return None
        return None

    async def get_channel_level(self, area: int, channel: int) -> Optional[float]:
        result = await self._query({"a": area, "c": channel, "j": 255})
        if "l" in result:
            try:
                return float(result["l"])
            except ValueError:
                return None
        return None

    async def get_temperature(self, area: int) -> Optional[float]:
        result = await self._query({"a": area, "tptr": 1, "j": 255})
        if "t" in result:
            try:
                return float(result["t"])
            except ValueError:
                return None
        return None

    async def get_setpoint(self, area: int) -> Optional[float]:
        result = await self._query({"a": area, "tpsp": 1, "j": 255})
        if "t" in result:
            try:
                return float(result["t"])
            except ValueError:
                return None
        return None

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def set_preset(self, area: int, preset: int, fade_ms: int = 1000) -> None:
        await self._set({"a": area, "p": preset, "f": fade_ms, "j": 255})

    async def set_level(
        self, area: int, channel: int, level: float, fade_ms: int = 500
    ) -> None:
        await self._set({"a": area, "c": channel, "l": int(level), "f": fade_ms, "j": 255})

    async def set_setpoint(self, area: int, setpoint: float) -> None:
        sign = "+" if setpoint >= 0 else "-"
        formatted = f"{sign}{abs(setpoint):05.2f}"
        await self._set({"a": area, "tpsp": formatted, "j": 255})

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self) -> None:
        await self.get_preset(area=1)
