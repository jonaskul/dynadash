"""Rollup and pruning.

Pruning is a permanent delete, so most of what matters here is when it refuses
to run: the raw points must never be removed before the rollup holds them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import influx_maintenance as maint
from config import config


@pytest.fixture(autouse=True)
def _retention_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.retention, "raw_pulse_days", 35)
    monkeypatch.setattr(config.retention, "prune_raw", True)
    monkeypatch.setattr(config.retention, "rollup_every_minutes", 5)


NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _rollup_at(monkeypatch: pytest.MonkeyPatch, when: datetime | None) -> None:
    monkeypatch.setattr(maint, "latest_rollup_time", lambda: when)


# ---------------------------------------------------------------------------
# When pruning refuses to run
# ---------------------------------------------------------------------------

def test_no_pruning_while_the_rollup_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no rollup, the raw points are the only copy there is."""
    _rollup_at(monkeypatch, None)
    assert maint.prune_cutoff(NOW) is None


def test_no_pruning_when_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.retention, "prune_raw", False)
    _rollup_at(monkeypatch, NOW)
    assert maint.prune_cutoff(NOW) is None


def test_no_pruning_when_the_retention_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.retention, "raw_pulse_days", 0)
    _rollup_at(monkeypatch, NOW)
    assert maint.prune_cutoff(NOW) is None


def test_a_stalled_rollup_task_stops_the_pruning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the task stopped weeks ago, pruning must stop where it stopped.

    Otherwise the delete boundary keeps advancing on age alone and eats raw data
    the rollup never recorded.
    """
    stalled = NOW - timedelta(days=40)
    _rollup_at(monkeypatch, stalled)

    cutoff = maint.prune_cutoff(NOW)

    assert cutoff is not None
    assert cutoff < stalled, "pruned past what the rollup holds"
    by_age = NOW - timedelta(days=35)
    assert cutoff < by_age


def test_a_healthy_rollup_prunes_on_age(monkeypatch: pytest.MonkeyPatch) -> None:
    _rollup_at(monkeypatch, NOW)

    cutoff = maint.prune_cutoff(NOW)

    assert cutoff == NOW - timedelta(days=35)


def test_the_cutoff_always_keeps_a_margin_behind_the_rollup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even a rollup that is up to date must not be pruned right up to its edge."""
    monkeypatch.setattr(config.retention, "raw_pulse_days", 1)
    _rollup_at(monkeypatch, NOW)

    cutoff = maint.prune_cutoff(NOW)

    assert cutoff is not None
    assert NOW - cutoff >= maint._PRUNE_SAFETY_MARGIN


def test_prune_is_skipped_entirely_when_there_is_no_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cutoff must mean no call into the delete API at all."""
    _rollup_at(monkeypatch, None)
    called = False

    def explode():
        nonlocal called
        called = True
        raise AssertionError("delete must not be reached")

    monkeypatch.setattr(maint.influx_store, "get_client", explode)

    assert maint.prune_raw_pulse() is None
    assert not called


# ---------------------------------------------------------------------------
# What the delete is scoped to
# ---------------------------------------------------------------------------

def test_the_delete_touches_only_raw_pulse(monkeypatch: pytest.MonkeyPatch) -> None:
    _rollup_at(monkeypatch, NOW)
    captured: dict[str, object] = {}

    class FakeDeleteApi:
        def delete(self, **kwargs: object) -> None:
            captured.update(kwargs)

    class FakeClient:
        def delete_api(self) -> FakeDeleteApi:
            return FakeDeleteApi()

    monkeypatch.setattr(maint.influx_store, "get_client", lambda: FakeClient())

    maint.prune_raw_pulse()

    assert captured["predicate"] == f'_measurement="{maint.RAW_MEASUREMENT}"'
    assert captured["bucket"] == config.influxdb.bucket
    # The rollup, prices, consumption, temperatures and levels must all survive.
    assert maint.ROLLUP_MEASUREMENT not in str(captured["predicate"])


# ---------------------------------------------------------------------------
# The rollup Flux
# ---------------------------------------------------------------------------

def test_counters_are_rolled_up_with_last_and_gauges_with_mean() -> None:
    """Averaging a monotonically rising total would turn it into nonsense."""
    flux = maint._rollup_flux(5)

    counters, _, gauges = flux.partition("gauges =")
    assert "fn: last" in counters
    assert "fn: mean" in gauges
    assert "fn: mean" not in counters
    assert "fn: last" not in gauges


def test_the_rollup_reads_raw_and_writes_the_rollup_measurement() -> None:
    flux = maint._rollup_flux(5)

    assert f'r._measurement == "{maint.RAW_MEASUREMENT}"' in flux
    assert f'value: "{maint.ROLLUP_MEASUREMENT}"' in flux
    assert f'to(bucket: "{config.influxdb.bucket}")' in flux
    assert "every: 1m" in flux


def test_the_rollup_looks_further_back_than_its_interval() -> None:
    """Overlapping runs rewrite the same windows, so a missed run self-heals."""
    flux = maint._rollup_flux(5)
    assert "range(start: -15m)" in flux
    assert "every: 5m" in flux


def test_the_task_is_named_so_it_can_be_found_and_updated() -> None:
    assert f'name: "{maint.TASK_NAME}"' in maint._rollup_flux(5)
