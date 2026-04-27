from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

import httpx

from dynalite import DynaliteClient, DynaliteError

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

DATA_DIR = Path(__file__).parent.parent / "data"
GATEWAY_FILE = DATA_DIR / "gateway.json"


class GatewayConfigIn(BaseModel):
    ip: str
    scheme: str = "http"
    verify_ssl: bool = True
    username: str = ""
    password: str = ""


class GatewayConfigOut(BaseModel):
    ip: str
    scheme: str = "http"
    verify_ssl: bool = True
    username: str = ""


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
    return GatewayConfigOut(
        ip=data["ip"],
        scheme=data.get("scheme", "http"),
        verify_ssl=data.get("verify_ssl", True),
        username=data.get("username", ""),
    )


@router.post("", response_model=GatewayConfigOut)
async def save_gateway(body: GatewayConfigIn) -> GatewayConfigOut:
    """Persist gateway connection settings."""
    _save({"ip": body.ip, "scheme": body.scheme, "verify_ssl": body.verify_ssl,
           "username": body.username, "password": body.password})
    return GatewayConfigOut(ip=body.ip, scheme=body.scheme, verify_ssl=body.verify_ssl,
                            username=body.username)


@router.post("/test", response_model=TestResult)
async def test_gateway(body: GatewayConfigIn) -> TestResult:
    """Test connectivity to the given gateway without saving settings."""
    client = DynaliteClient(ip=body.ip, scheme=body.scheme, verify_ssl=body.verify_ssl,
                            username=body.username, password=body.password)
    try:
        await client.test_connection()
        return TestResult(success=True, message="Connection successful.")
    except DynaliteError as exc:
        return TestResult(success=False, message=str(exc))
    except Exception as exc:
        return TestResult(success=False, message=f"Unexpected error: {exc}")


@router.get("/probe/influx")
async def probe_influx() -> dict:
    """Test InfluxDB connectivity and return bucket info."""
    from influx import _client
    from config import config as app_config
    try:
        with _client() as client:
            health = client.health()
            buckets_api = client.buckets_api()
            bucket = buckets_api.find_bucket_by_name(app_config.influxdb.bucket)
            return {
                "health": health.status,
                "bucket": bucket.name if bucket else None,
                "bucket_found": bucket is not None,
                "org": app_config.influxdb.org,
            }
    except Exception as e:
        return {"error": str(e)}


@router.get("/probe/{area_id}")
async def probe_gateway(area_id: int) -> dict:
    """Return raw CGI responses for all thermostat queries on area_id — for debugging."""
    data = _load()
    if data is None:
        return {"error": "No gateway configured"}
    base = f"{data.get('scheme', 'http')}://{data['ip']}"
    verify = data.get("verify_ssl", True)
    headers: dict = {}
    if data.get("username"):
        import base64
        creds = base64.b64encode(f"{data['username']}:{data.get('password','')}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"

    results: dict = {}
    queries = {
        "preset":      {"a": area_id, "p": ""},
        "temperature": {"a": area_id, "tptr": 1, "j": 255},
        "setpoint_tpsp": {"a": area_id, "tpsp": 1, "j": 255},
        "setpoint_temperaturesetpoint": {"a": area_id, "temperaturesetpoint": 1, "j": 255},
    }
    async with httpx.AsyncClient(timeout=5.0, verify=verify) as client:
        for name, params in queries.items():
            try:
                r = await client.get(f"{base}/GetDyNet.cgi", params=params, headers=headers)
                results[name] = {"status": r.status_code, "body": r.text}
            except Exception as e:
                results[name] = {"error": str(e)}
    return results


@router.delete("", status_code=204)
async def delete_gateway() -> None:
    """Remove the gateway configuration."""
    if GATEWAY_FILE.exists():
        GATEWAY_FILE.unlink()
