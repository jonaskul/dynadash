"""The systemd unit template.

The sandbox cannot be exercised from a test — that needs a real systemd — so
these pin down the directives that are easy to drop by accident and expensive to
debug afterwards.
"""

from __future__ import annotations

from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[2] / "systemd" / "dynadash-backend.service.in"


@pytest.fixture(scope="module")
def unit() -> list[str]:
    return [line.strip() for line in UNIT.read_text().splitlines()]


def test_the_service_does_not_run_as_root(unit: list[str]) -> None:
    assert "User=@SERVICE_USER@" in unit
    assert "User=root" not in unit


@pytest.mark.parametrize(
    "directive",
    [
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "PrivateTmp=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "RestrictSUIDSGID=yes",
        "LockPersonality=yes",
        "SystemCallArchitectures=native",
    ],
)
def test_sandbox_directives_are_present(unit: list[str], directive: str) -> None:
    assert directive in unit


def test_the_data_directory_is_the_only_writable_path(unit: list[str]) -> None:
    writable = [line for line in unit if line.startswith("ReadWritePaths=")]
    assert writable == ["ReadWritePaths=@BACKEND_DIR@/data"]


def test_dns_still_works_inside_the_sandbox(unit: list[str]) -> None:
    """glibc's getaddrinfo opens a netlink socket to enumerate interfaces.

    Without AF_NETLINK name resolution can fail, which takes the Tibber
    connection down with it — the exact failure this sandbox must not cause.
    """
    families = [line for line in unit if line.startswith("RestrictAddressFamilies=")]
    assert len(families) == 1
    allowed = families[0].split("=", 1)[1].split()
    assert "AF_NETLINK" in allowed
    assert "AF_INET" in allowed and "AF_INET6" in allowed


def test_bytecode_writing_is_switched_off(unit: list[str]) -> None:
    """The code tree is read-only, so Python would retry the write every import."""
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in unit


def test_the_updater_is_reached_without_anything_setuid() -> None:
    """NoNewPrivileges only holds while nothing in the path needs sudo."""
    systemd_dir = UNIT.parent
    assert (systemd_dir / "dynadash-update.path").is_file()
    assert (systemd_dir / "dynadash-update.service").is_file()

    path_unit = (systemd_dir / "dynadash-update.path").read_text()
    assert "PathExists=@BACKEND_DIR@/data/update-request" in path_unit
    assert "Unit=dynadash-update.service" in path_unit

    service = (systemd_dir / "dynadash-update.service").read_text()
    assert "handle-request" in service
    assert "sudo" not in service
