from time import time

from app import APP_VERSION
from app.protocol.constants import PROTOCOL_VERSION
from httpx import AsyncClient


async def test_health_contract(client: AsyncClient) -> None:
    before = int(time() * 1000)
    response = await client.get("/health")
    after = int(time() * 1000)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": APP_VERSION,
        "protocolVersion": PROTOCOL_VERSION,
        "serverTime": response.json()["serverTime"],
    }
    assert before <= response.json()["serverTime"] <= after


async def test_api_v1_rejects_missing_protocol_header(client: AsyncClient) -> None:
    response = await client.get("/api/v1/not-implemented")

    assert response.status_code == 426
    assert response.json() == {
        "code": "PROTOCOL_VERSION_UNSUPPORTED",
        "message": "客户端协议版本不受支持，服务端要求版本 1。",
        "retryable": False,
        "details": {
            "expectedProtocolVersion": 1,
            "receivedProtocolVersion": None,
        },
    }


async def test_api_v1_allows_supported_protocol_header(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/not-implemented",
        headers={"X-Protocol-Version": str(PROTOCOL_VERSION)},
    )

    assert response.status_code == 404


async def test_api_v1_allows_configured_cors_preflight(client: AsyncClient) -> None:
    response = await client.options(
        "/api/v1/rooms",
        headers={
            "Origin": "http://127.0.0.1:1420",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-protocol-version",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert "x-protocol-version" in response.headers["access-control-allow-headers"].lower()
