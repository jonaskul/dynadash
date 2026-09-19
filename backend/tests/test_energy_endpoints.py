"""The energy endpoints must be cheap enough to poll every two seconds."""

from __future__ import annotations

import time

import pytest

import influx_store
import tibber
from influx_maintenance import RAW_MEASUREMENT, ROLLUP_MEASUREMENT

pytestmark = pytest.mark.usefixtures("temp_db")


@pytest.fixture(autouse=True)
def _no_live_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a Pulse manager with nothing in it, and no cache."""
    monkeypatch.setattr(tibber.pulse_manager, "_last_measurement", None)
    monkeypatch.setattr(tibber.pulse_manager, "_last_data", None)
    monkeypatch.setattr(tibber.pulse_manager, "_last_ts", None)
    monkeypatch.setattr(tibber.pulse_manager, "_connected", False)
    monkeypatch.setattr(tibber, "_cache", {})


def _forbid_queries(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def spy(flux: str):
        seen.append(flux)
        raise AssertionError("InfluxDB should not have been queried")

    monkeypatch.setattr(influx_store, "query", spy)
    return seen


async def test_live_power_comes_from_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reading is already in RAM from the WebSocket; querying for it is waste."""
    _forbid_queries(monkeypatch)
    monkeypatch.setattr(
        tibber.pulse_manager, "_last_measurement", {"power": 4305.0}
    )
    monkeypatch.setattr(tibber.pulse_manager, "_last_data", time.monotonic())
    monkeypatch.setattr(tibber.pulse_manager, "_connected", True)

    result = await tibber.energy_status()

    assert result["current_power"] == 4305.0
    assert result["pulse_connected"] is True


async def test_pulse_is_not_reported_live_when_data_has_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tibber.pulse_manager, "_connected", True)
    monkeypatch.setattr(tibber.pulse_manager, "_last_data", time.monotonic() - 120)
    monkeypatch.setattr(tibber.pulse_manager, "_last_measurement", {"power": 1.0})
    monkeypatch.setattr(influx_store, "query", lambda flux: [])

    result = await tibber.energy_status()

    assert result["pulse_connected"] is False


async def test_a_nonsense_power_reading_does_not_break_the_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_queries(monkeypatch)
    monkeypatch.setattr(
        tibber.pulse_manager, "_last_measurement", {"power": "not-a-number"}
    )
    monkeypatch.setattr(tibber.pulse_manager, "_last_data", time.monotonic())

    result = await tibber.energy_status()

    assert result["current_power"] is None


async def test_the_stored_price_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """At a two-second poll an uncached price lookup is a query every two seconds."""
    calls = 0

    def counting_price():
        nonlocal calls
        calls += 1
        return {"total": 0.976, "level": "CHEAP", "currency": "NOK"}

    monkeypatch.setattr(tibber, "_last_price", counting_price)
    monkeypatch.setattr(tibber, "get_setting", lambda k, d=None: "set")
    monkeypatch.setattr(tibber.pulse_manager, "_last_measurement", {"power": 1.0})
    monkeypatch.setattr(tibber.pulse_manager, "_last_data", time.monotonic())

    for _ in range(5):
        await tibber.energy_status()

    assert calls == 1, f"price was queried {calls} times across five polls"


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def test_every_range_is_downsampled_to_a_few_hundred_points() -> None:
    span = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}
    window = {"10s": 10, "1m": 60, "5m": 300, "30m": 1800}

    assert set(tibber._WINDOW) == set(tibber._VALID_RANGES)
    for range_, seconds in span.items():
        points = seconds / window[tibber._WINDOW[range_]]
        assert points <= 400, f"{range_} still returns {points:.0f} points"


def test_long_ranges_read_the_rollup_and_short_ranges_the_raw_data() -> None:
    assert tibber._pulse_measurement("1h") == RAW_MEASUREMENT
    assert tibber._pulse_measurement("6h") == RAW_MEASUREMENT
    assert tibber._pulse_measurement("24h") == ROLLUP_MEASUREMENT
    assert tibber._pulse_measurement("7d") == ROLLUP_MEASUREMENT


@pytest.mark.parametrize("endpoint", ["history_power", "history_cost", "history_phases"])
async def test_history_endpoints_reject_an_unknown_range(endpoint: str) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await getattr(tibber, endpoint)(range="30d")
    assert exc.value.status_code == 422


@pytest.mark.parametrize("range_", ["1h", "6h", "24h", "7d"])
async def test_history_queries_name_the_right_measurement(
    range_: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def spy(flux: str):
        captured.append(flux)
        return []

    monkeypatch.setattr(influx_store, "query", spy)

    await tibber.history_power(range=range_)

    assert captured, "no query was issued"
    flux = captured[0]
    assert f'r._measurement == "{tibber._pulse_measurement(range_)}"' in flux
    assert f"every: {tibber._WINDOW[range_]}" in flux
    # An un-aggregated long range is what made these queries unusable.
    assert "aggregateWindow" in flux
