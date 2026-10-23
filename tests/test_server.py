from __future__ import annotations

import asyncio
import json
import time

import pytest
from mcp.server.transport_security import TransportSecuritySettings
from starlette.testclient import TestClient

from akbridge.catalog import ApiFunction, signature_to_schema
from akbridge.errors import AKBridgeError, ErrorCode
from akbridge.reliability import CallExecutor, RetryPolicy
from akbridge.server import create_http_app, create_server, create_sse_app, invoke_api_async


def test_server_can_be_created() -> None:
    assert create_server() is not None


def test_router_and_optional_sse_contracts_can_be_created() -> None:
    server = create_server(mode="router")
    assert server.akbridge_mode == "router"  # type: ignore[attr-defined]
    app = create_sse_app(mode="router")
    assert {route.path for route in app.routes} == {"/sse", "/messages"}


def test_async_provider_timeout_returns_without_human_intervention() -> None:
    def slow() -> int:
        time.sleep(0.1)
        return 1

    api = ApiFunction(
        name="slow",
        function=slow,
        description="slow",
        input_schema=signature_to_schema(slow),
        signature="() -> int",
    )

    async def exercise() -> None:
        with pytest.raises(AKBridgeError) as excinfo:
            await invoke_api_async(
                api,
                {},
                executor=CallExecutor(retry_policy=RetryPolicy(max_attempts=1)),
                row_limit=10,
                call_timeout=0.01,
            )
        err = excinfo.value
        assert err.code == ErrorCode.UPSTREAM_TIMEOUT
        assert err.retry_hint is not None
        payload = json.loads(str(err))
        assert payload["error"]["code"] == "UPSTREAM_TIMEOUT"
        assert "AKBridge call exceeded" in payload["error"]["message"]

    asyncio.run(exercise())


def test_default_mode_is_router() -> None:
    server = create_server()
    assert server.akbridge_mode == "router"  # type: ignore[attr-defined]


def test_streamable_http_app_uses_explicit_dns_rebinding_protection() -> None:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.routing import Mount

    app = create_http_app(mode="router", allowed_hosts=["localhost:*"])
    assert any(isinstance(route, Mount) and route.path == "/mcp" for route in app.routes)
    manager = app.state.akbridge_http_session_manager
    assert isinstance(manager, StreamableHTTPSessionManager)
    assert manager.security_settings == TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*"],
        allowed_origins=[],
    )


def test_default_streamable_http_hosts_allow_localhost_with_and_without_ports() -> None:
    app = create_http_app(mode="router")
    allowed_hosts = app.state.akbridge_http_session_manager.security_settings.allowed_hosts
    assert {"localhost", "localhost:*"} <= set(allowed_hosts)
    assert {"127.0.0.1", "127.0.0.1:*"} <= set(allowed_hosts)
    assert {"[::1]", "[::1]:*"} <= set(allowed_hosts)


def test_streamable_http_bearer_token_is_opt_in() -> None:
    app = create_http_app(mode="router", bearer_token="test-token", allowed_hosts=["testserver"])
    with TestClient(app) as client:
        response = client.post("/mcp", json={}, headers={"Host": "testserver"})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_streamable_http_accepts_bearer_token_and_initialize() -> None:
    app = create_http_app(mode="router", bearer_token="test-token", allowed_hosts=["testserver"])
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            headers={
                "Host": "testserver",
                "Authorization": "bearer test-token",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "audit", "version": "1"},
                },
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert '"name":"akbridge"' in response.text


def test_streamable_http_rejects_unlisted_origin() -> None:
    app = create_http_app(mode="router", allowed_hosts=["testserver"])
    with TestClient(app) as client:
        response = client.get("/mcp", headers={"Host": "testserver", "Origin": "https://evil.test"})
        assert response.status_code == 403
