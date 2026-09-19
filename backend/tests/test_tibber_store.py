"""Prices and consumption are served from InfluxDB, not proxied to Tibber.

Tibber rate-limits a token to roughly 100 requests per five minutes, and the
hourly poller already stores everything these endpoints return — so the tests
that matter are that the stored path is used when it has data, and that Tibber is
still asked when it does not.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import tibber

pytestmark = pytest.mark.usefixtures("temp_db")


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tibber, "_cache", {})


def _forbid_live(monkeypatch: pytest.MonkeyPatch) -> None:
    async def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Tibber should not have been called")

    monkeypatch.setattr(tibber, "_live_prices", explode)
    monkeypatch.setattr(tibber, "_live_consumption", explode)


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

async def test_stored_prices_are_served_without_calling_tibber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_live(monkeypatch)
    day = tibber._local_day_start()
    stored = {
        "current": None,
        "today": [{"startsAt": day.isoformat(), "total": 0.9}],
        "tomorrow": [],
    }
    monkeypatch.setattr(tibber, "_stored_prices", lambda: stored)

    assert await tibber.get_prices() is stored


async def test_tibber_is_asked_when_nothing_is_stored_yet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh install has no stored prices until the first poll runs."""
    monkeypatch.setattr(
        tibber, "_stored_prices", lambda: {"current": None, "today": [], "tomorrow": []}
    )
    called = False

    async def live() -> dict[str, object]:
        nonlocal called
        called = True
        return {"current": None, "today": [{"startsAt": "x"}], "tomorrow": []}

    monkeypatch.setattr(tibber, "_live_prices", live)

    result = await tibber.get_prices()

    assert called
    assert result["today"]


async def test_tibber_is_asked_when_influxdb_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom() -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(tibber, "_stored_prices", boom)

    async def live() -> dict[str, object]:
        return {"current": None, "today": [{"startsAt": "x"}], "tomorrow": []}

    monkeypatch.setattr(tibber, "_live_prices", live)

    result = await tibber.get_prices()
    assert result["today"]


async def test_prices_are_cached_between_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_live(monkeypatch)
    calls = 0

    def counting() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"current": None, "today": [{"startsAt": "x"}], "tomorrow": []}

    monkeypatch.setattr(tibber, "_stored_prices", counting)

    for _ in range(4):
        await tibber.get_prices()

    assert calls == 1


def test_prices_are_split_by_local_calendar_day() -> None:
    """Tibber's today/tomorrow split is by local day, not a rolling 24 hours."""
    day = tibber._local_day_start()
    assert (day.hour, day.minute, day.second) == (0, 0, 0)
    assert day.tzinfo is not None


# ---------------------------------------------------------------------------
# Consumption
# ---------------------------------------------------------------------------

async def test_stored_consumption_is_served_without_calling_tibber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_live(monkeypatch)
    nodes = [{"from": "2026-09-19T10:00:00+02:00", "consumption": 1.0, "cost": 0.9}]
    monkeypatch.setattr(tibber, "_stored_consumption", lambda r, l: nodes)

    assert await tibber.get_consumption(resolution="HOURLY", last=24) is nodes


async def test_consumption_falls_back_to_tibber_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tibber, "_stored_consumption", lambda r, l: [])
    called = False

    async def live(resolution: str, last: int) -> list[dict[str, object]]:
        nonlocal called
        called = True
        return [{"from": "x"}]

    monkeypatch.setattr(tibber, "_live_consumption", live)

    await tibber.get_consumption(resolution="HOURLY", last=24)
    assert called


async def test_an_unknown_resolution_is_rejected() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await tibber.get_consumption(resolution="WEEKLY", last=24)
    assert exc.value.status_code == 422


async def test_each_resolution_and_span_is_cached_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_live(monkeypatch)
    seen: list[tuple[str, int]] = []

    def spy(resolution: str, last: int) -> list[dict[str, object]]:
        seen.append((resolution, last))
        return [{"from": "x"}]

    monkeypatch.setattr(tibber, "_stored_consumption", spy)

    await tibber.get_consumption(resolution="HOURLY", last=24)
    await tibber.get_consumption(resolution="HOURLY", last=24)
    await tibber.get_consumption(resolution="DAILY", last=7)

    assert seen == [("HOURLY", 24), ("DAILY", 7)]


# ---------------------------------------------------------------------------
# Bucketing hourly rows into days and months
# ---------------------------------------------------------------------------

def _rows(start: datetime, hours: int, kwh: float, cost: float, price: float):
    return [
        {
            "time": start + timedelta(hours=i),
            "consumption": kwh,
            "cost": cost,
            "unitPrice": price,
            "currency": "NOK",
        }
        for i in range(hours)
    ]


def test_daily_buckets_sum_consumption_and_cost() -> None:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = _rows(start, 24, kwh=1.5, cost=1.0, price=0.8)

    nodes = tibber._bucket_consumption(rows, "DAILY")

    assert len(nodes) == 1
    assert nodes[0]["consumption"] == pytest.approx(36.0)
    assert nodes[0]["cost"] == pytest.approx(24.0)
    assert nodes[0]["currency"] == "NOK"


def test_daily_buckets_split_on_the_day_boundary() -> None:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = _rows(start, 36, kwh=1.0, cost=1.0, price=1.0)

    nodes = tibber._bucket_consumption(rows, "DAILY")

    assert len(nodes) == 2
    assert nodes[0]["consumption"] == pytest.approx(24.0)
    assert nodes[1]["consumption"] == pytest.approx(12.0)


def test_the_unit_price_is_weighted_by_consumption() -> None:
    """An hour with almost no usage must not drag the average around."""
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = [
        {"time": start, "consumption": 10.0, "cost": 10.0, "unitPrice": 1.0, "currency": "NOK"},
        {"time": start + timedelta(hours=1), "consumption": 0.01, "cost": 0.5,
         "unitPrice": 50.0, "currency": "NOK"},
    ]

    nodes = tibber._bucket_consumption(rows, "DAILY")

    # A plain mean would give 25.5; weighting keeps it close to the real price.
    assert nodes[0]["unitPrice"] == pytest.approx(1.049, abs=0.01)


def test_an_empty_bucket_has_no_unit_price() -> None:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = [
        {"time": start, "consumption": 0.0, "cost": 0.0, "unitPrice": None, "currency": "NOK"}
    ]

    nodes = tibber._bucket_consumption(rows, "DAILY")

    assert nodes[0]["unitPrice"] is None


def test_missing_values_do_not_break_bucketing() -> None:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = [
        {"time": start, "consumption": None, "cost": None, "unitPrice": None, "currency": None},
        {"time": start + timedelta(hours=1), "consumption": 2.0, "cost": 1.0,
         "unitPrice": 0.5, "currency": "NOK"},
    ]

    nodes = tibber._bucket_consumption(rows, "DAILY")

    assert nodes[0]["consumption"] == pytest.approx(2.0)
    assert nodes[0]["cost"] == pytest.approx(1.0)
    assert nodes[0]["currency"] == "NOK"
