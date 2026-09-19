"""The self-update request protocol.

The backend is unprivileged, so it asks for an update by dropping a file that a
root-side systemd path unit picks up. What matters here is that the request is
well-formed and atomic, that an answer to somebody else's request is not mistaken
for our own, and that a missing helper fails loudly instead of hanging.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from routers import update


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(update, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(update, "REQUEST_FILE", str(tmp_path / "update-request"))
    monkeypatch.setattr(update, "STATUS_FILE", str(tmp_path / "update-status.json"))
    monkeypatch.setattr(update, "_POLL_INTERVAL", 0.01)
    return tmp_path


def _answer(data_dir: Path, nonce: str, ok: bool, output: str) -> None:
    (data_dir / "update-status.json").write_text(
        json.dumps({"nonce": nonce, "action": "check", "ok": ok, "output": output})
    )


# ---------------------------------------------------------------------------
# The request itself
# ---------------------------------------------------------------------------

def test_a_request_is_a_nonce_and_a_fixed_action(data_dir: Path) -> None:
    nonce = update._submit("check")

    content = (data_dir / "update-request").read_text()
    assert content == f"{nonce} check\n"
    # The helper only echoes the nonce back, but it validates the shape first.
    assert len(nonce) == 32 and all(c in "0123456789abcdef" for c in nonce)


def test_each_request_gets_a_fresh_nonce(data_dir: Path) -> None:
    assert update._submit("check") != update._submit("check")


def test_no_partial_request_is_ever_visible(data_dir: Path) -> None:
    """The path unit fires on the file existing, so it must appear complete."""
    update._submit("apply")

    leftovers = list(data_dir.glob("update-request.*"))
    assert not leftovers, f"temporary files left behind: {leftovers}"
    assert (data_dir / "update-request").read_text().endswith(" apply\n")


# ---------------------------------------------------------------------------
# Matching answers to questions
# ---------------------------------------------------------------------------

def test_a_stale_answer_is_ignored(data_dir: Path) -> None:
    """A status file left from an earlier request must not be read as this one's."""
    _answer(data_dir, "0" * 32, True, "current abc\nlatest abc\n")
    assert update._read_status("f" * 32) is None


def test_a_matching_answer_is_returned(data_dir: Path) -> None:
    _answer(data_dir, "a" * 32, True, "hello")
    status = update._read_status("a" * 32)
    assert status is not None and status["output"] == "hello"


def test_a_missing_or_corrupt_answer_is_not_an_answer(data_dir: Path) -> None:
    assert update._read_status("a" * 32) is None
    (data_dir / "update-status.json").write_text("{not json")
    assert update._read_status("a" * 32) is None


# ---------------------------------------------------------------------------
# check_update
# ---------------------------------------------------------------------------

async def test_check_reports_an_available_update(data_dir: Path) -> None:
    async def helper() -> None:
        while not (data_dir / "update-request").exists():
            await asyncio.sleep(0.01)
        nonce = (data_dir / "update-request").read_text().split()[0]
        _answer(
            data_dir,
            nonce,
            True,
            "current " + "a" * 40 + "\nlatest " + "b" * 40 + "\n"
            "commit " + "b" * 40 + "|Fix the thing|2026-09-19\n",
        )

    task = asyncio.create_task(helper())
    result = await update.check_update()
    await task

    assert result["up_to_date"] is False
    assert result["current_sha"] == "a" * 7
    assert result["latest_sha"] == "b" * 7
    assert result["commits"] == [
        {"sha": "b" * 7, "message": "Fix the thing", "date": "2026-09-19"}
    ]


async def test_check_reports_up_to_date(data_dir: Path) -> None:
    sha = "c" * 40

    async def helper() -> None:
        while not (data_dir / "update-request").exists():
            await asyncio.sleep(0.01)
        nonce = (data_dir / "update-request").read_text().split()[0]
        _answer(data_dir, nonce, True, f"current {sha}\nlatest {sha}\n")

    task = asyncio.create_task(helper())
    result = await update.check_update()
    await task

    assert result["up_to_date"] is True
    assert result["commits"] == []


async def test_a_failed_fetch_surfaces_its_message(data_dir: Path) -> None:
    async def helper() -> None:
        while not (data_dir / "update-request").exists():
            await asyncio.sleep(0.01)
        nonce = (data_dir / "update-request").read_text().split()[0]
        _answer(data_dir, nonce, False, "fatal: could not resolve host github.com")

    task = asyncio.create_task(helper())
    with pytest.raises(HTTPException) as exc:
        await update.check_update()
    await task

    assert exc.value.status_code == 503
    assert "could not resolve host" in str(exc.value.detail)


async def test_an_unclaimed_request_fails_fast_and_names_the_cause(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no path unit nothing consumes the request.

    The request file sitting untouched is the tell, so this must not make the
    dashboard wait out the full timeout before saying what is wrong.
    """
    monkeypatch.setattr(update, "CHECK_TIMEOUT", 30.0)
    monkeypatch.setattr(update, "UNCLAIMED_GRACE", 0.05)

    with pytest.raises(HTTPException) as exc:
        await update.check_update()

    assert exc.value.status_code == 503
    assert "dynadash-update.path" in str(exc.value.detail)


async def test_a_claimed_but_unanswered_request_times_out_differently(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A helper that took the request but never answered is a different fault.

    Blaming the path unit there would send someone looking in the wrong place.
    """
    monkeypatch.setattr(update, "CHECK_TIMEOUT", 0.4)
    monkeypatch.setattr(update, "UNCLAIMED_GRACE", 0.05)

    async def claim_and_go_quiet() -> None:
        while not (data_dir / "update-request").exists():
            await asyncio.sleep(0.01)
        (data_dir / "update-request").unlink()

    task = asyncio.create_task(claim_and_go_quiet())
    with pytest.raises(HTTPException) as exc:
        await update.check_update()
    await task

    assert exc.value.status_code == 503
    assert "dynadash-update.path" not in str(exc.value.detail)
    assert "did not finish" in str(exc.value.detail)


async def test_incomplete_output_is_rejected(data_dir: Path) -> None:
    """A successful run that named no revisions cannot be reported as up to date."""
    async def helper() -> None:
        while not (data_dir / "update-request").exists():
            await asyncio.sleep(0.01)
        nonce = (data_dir / "update-request").read_text().split()[0]
        _answer(data_dir, nonce, True, "something unexpected\n")

    task = asyncio.create_task(helper())
    with pytest.raises(HTTPException) as exc:
        await update.check_update()
    await task

    assert exc.value.status_code == 503
    assert "revision" in str(exc.value.detail)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

async def test_apply_returns_before_the_restart_and_leaves_a_request(
    data_dir: Path,
) -> None:
    """The update restarts this process, so nothing can be awaited afterwards."""
    from fastapi import BackgroundTasks

    tasks = BackgroundTasks()
    result = await update.apply_update(tasks)
    assert result == {"status": "updating"}
    assert not (data_dir / "update-request").exists(), "ran before responding"

    await tasks()
    assert (data_dir / "update-request").read_text().endswith(" apply\n")
