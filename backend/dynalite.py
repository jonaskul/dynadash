from __future__ import annotations

from typing import Optional

import httpx


class DynaliteError(Exception):
    """Raised when communication with the Dynalite gateway fails."""


class DynaliteClient:
    """Async HTTP client for the Dynalite Ethernet Gateway CGI API."""

    def __init__(self, ip: str) -> None:
        self.base_url = f"http://{ip}"

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(text: str) -> dict[str, str]:
        """Parse a plain-text key=value response into a dict."""
        result: dict[str, str] = {}
        for line in text.strip().splitlines():
            line = line.strip()
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
        return result

    async def _get(self, endpoint: str, params: dict[str, str | int]) -> dict[str, str]:
        url = f"{self.base_url}/{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return self._parse_response(response.text)
        except httpx.HTTPError as exc:
            raise DynaliteError(f"Gateway request failed: {exc}") from exc

    async def _set(self, params: dict[str, str | int]) -> dict[str, str]:
        return await self._get("SetDyNet.cgi", params)

    async def _query(self, params: dict[str, str | int]) -> dict[str, str]:
        return await self._get("GetDyNet.cgi", params)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_preset(self, area: int) -> Optional[int]:
        """Return the active preset number for *area*, or None if unknown."""
        result = await self._query({"a": area, "p": 65535, "j": 255})
        if "p" in result:
            try:
                return int(result["p"])
            except ValueError:
                return None
        return None

    async def get_channel_level(self, area: int, channel: int) -> Optional[float]:
        """Return the level (0–100) for *channel* in *area*."""
        result = await self._query({"a": area, "c": channel, "j": 255})
        if "l" in result:
            try:
                return float(result["l"])
            except ValueError:
                return None
        return None

    async def get_temperature(self, area: int) -> Optional[float]:
        """Return the current measured temperature for *area*."""
        result = await self._query({"a": area, "tptr": 1, "j": 255})
        if "t" in result:
            try:
                return float(result["t"])
            except ValueError:
                return None
        return None

    async def get_setpoint(self, area: int) -> Optional[float]:
        """Return the current temperature setpoint for *area*."""
        result = await self._query({"a": area, "temperaturesetpoint": 1, "j": 255})
        if "tpsp" in result:
            try:
                return float(result["tpsp"])
            except ValueError:
                return None
        return None

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def set_preset(self, area: int, preset: int, fade_ms: int = 1000) -> None:
        """Activate *preset* in *area* with the given fade time."""
        await self._set({"a": area, "p": preset, "f": fade_ms, "j": 255})

    async def set_level(
        self, area: int, channel: int, level: float, fade_ms: int = 500
    ) -> None:
        """Set *channel* in *area* to *level* percent."""
        await self._set({"a": area, "c": channel, "l": int(level), "f": fade_ms, "j": 255})

    async def set_setpoint(self, area: int, setpoint: float) -> None:
        """Set the temperature setpoint for *area*."""
        sign = "+" if setpoint >= 0 else "-"
        formatted = f"{sign}{abs(setpoint):05.2f}"
        await self._set({"a": area, "tpsp": formatted, "j": 255})

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_connection(self) -> None:
        """Perform a minimal read to verify gateway reachability and credentials.

        Raises DynaliteError if the gateway cannot be reached or rejects auth.
        """
        await self._query({"a": 1, "p": 65535, "j": 255})
