from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from dynalite import DynaliteClient, DynaliteError

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

DATA_DIR = Path(__file__).parent.parent / "data"
GATEWAY_FILE = DATA_DIR / "gateway.json"


class GatewayConfigIn(BaseModel):
    ip: str
    scheme: str = "http"


class GatewayConfigOut(BaseModel):
    ip: str
    scheme: str = "http"


class TestResult(BaseModel):
    success: bool
    message: str


def _load() -> Optional[dict[str, str]]:
    if not GATEWAY_FILE.exists():
        return None
    try:
        return json.loads(GATEWAY_FILE.read_text())
    except Exception:
        return None


def _save(data: dict[str, str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GATEWAY_FILE.write_text(json.dumps(data, indent=2))


@router.get("", response_model=Optional[GatewayConfigOut])
async def get_gateway() -> Optional[GatewayConfigOut]:
    """Return the current gateway config."""
    data = _load()
    if data is None:
        return None
    return GatewayConfigOut(ip=data["ip"], scheme=data.get("scheme", "http"))


@router.post("", response_model=GatewayConfigOut)
async def save_gateway(body: GatewayConfigIn) -> GatewayConfigOut:
    """Persist gateway connection settings."""
    _save({"ip": body.ip, "scheme": body.scheme})
    return GatewayConfigOut(ip=body.ip, scheme=body.scheme)


@router.post("/test", response_model=TestResult)
async def test_gateway(body: GatewayConfigIn) -> TestResult:
    """Test connectivity to the given gateway without saving settings."""
    client = DynaliteClient(ip=body.ip, scheme=body.scheme)
    try:
        await client.test_connection()
        return TestResult(success=True, message="Connection successful.")
    except DynaliteError as exc:
        return TestResult(success=False, message=str(exc))
    except Exception as exc:
        return TestResult(success=False, message=f"Unexpected error: {exc}")


@router.delete("", status_code=204)
async def delete_gateway() -> None:
    """Remove the gateway configuration."""
    if GATEWAY_FILE.exists():
        GATEWAY_FILE.unlink()
