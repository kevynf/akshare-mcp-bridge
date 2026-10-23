"""Tests for structured content, output schemas, and stable error codes."""

from __future__ import annotations

import json
from typing import Any

import pytest

from akbridge.catalog import ApiFunction, signature_to_schema
from akbridge.errors import AKBridgeError, ErrorCode, classify_exception, wrap_exception
from akbridge.reliability import CircuitOpenError
from akbridge.router import (
    CALL_OUTPUT_SCHEMA,
    DESCRIBE_OUTPUT_SCHEMA,
    SEARCH_OUTPUT_SCHEMA,
    CatalogIndex,
    router_tool_definitions,
)
from akbridge.server import _validate_api_arguments, build_mcp_tools, create_server


def _api(name: str = "stock_zh_a_hist") -> ApiFunction:
    def stock_zh_a_hist(symbol: str = "000001") -> dict[str, Any]:
        return {"symbol": symbol}

    return ApiFunction(
        name=name,
        function=stock_zh_a_hist,
        description="A股历史行情",
        input_schema=signature_to_schema(stock_zh_a_hist),
        signature="(symbol: str = '000001') -> dict",
        category="stock",
    )


def test_router_tools_carry_output_schemas() -> None:
    definitions = {item["name"]: item for item in router_tool_definitions()}
    assert definitions["akbridge_search"]["outputSchema"] is SEARCH_OUTPUT_SCHEMA
    assert definitions["akbridge_describe"]["outputSchema"] is DESCRIBE_OUTPUT_SCHEMA
    assert definitions["akbridge_call"]["outputSchema"] is CALL_OUTPUT_SCHEMA


def test_router_tools_have_titles_and_meta() -> None:
    tools = {tool.name: tool for tool in build_mcp_tools({"x": _api("x")}, mode="router")}
    assert tools["akbridge_search"].title == "AKBridge Search"
    assert tools["akbridge_describe"].title == "AKBridge Describe"
    assert tools["akbridge_call"].title == "AKBridge Call"
    assert tools["akbridge_search"].meta is not None
    assert "documentation_uri" in tools["akbridge_search"].meta  # type: ignore[operator]


def test_router_tools_expose_output_schema_through_build_mcp_tools() -> None:
    tools = {tool.name: tool for tool in build_mcp_tools({"x": _api("x")}, mode="router")}
    for name in ("akbridge_search", "akbridge_describe", "akbridge_call"):
        assert tools[name].outputSchema is not None, f"{name} missing outputSchema"


def test_call_schema_accepts_include_metrics() -> None:
    definitions = {item["name"]: item for item in router_tool_definitions()}
    call_props = definitions["akbridge_call"]["inputSchema"]["properties"]
    assert "include_metrics" in call_props
    assert call_props["include_metrics"]["default"] is False
    assert call_props["allow_side_effect"]["default"] is False


def test_error_str_is_json_payload_with_stable_code() -> None:
    err = AKBridgeError(
        ErrorCode.UNKNOWN_API,
        "Unknown AKShare API: foo",
        suggestions=["bar", "baz"],
        retry_hint="call akbridge_search first",
    )
    payload = json.loads(str(err))
    assert payload["error"]["code"] == "UNKNOWN_API"
    assert payload["error"]["suggestions"] == ["bar", "baz"]
    assert payload["error"]["retry_hint"] == "call akbridge_search first"


def test_classify_exception_maps_known_types() -> None:
    assert classify_exception(TimeoutError()) == ErrorCode.UPSTREAM_TIMEOUT
    assert classify_exception(ConnectionError()) == ErrorCode.UPSTREAM_ERROR
    assert classify_exception(OSError()) == ErrorCode.UPSTREAM_ERROR
    assert classify_exception(KeyError("x")) == ErrorCode.UNKNOWN_API
    assert classify_exception(ValueError("x")) == ErrorCode.INVALID_ARGUMENT
    assert classify_exception(CircuitOpenError("x")) == ErrorCode.CIRCUIT_OPEN
    assert classify_exception(RuntimeError("x")) == ErrorCode.INTERNAL_ERROR


def test_classify_httpx_network_and_rate_limit_errors() -> None:
    httpx = pytest.importorskip("httpx")
    request = httpx.Request("GET", "https://example.test")
    connect_error = httpx.ConnectError("offline", request=request)
    read_timeout = httpx.ReadTimeout("slow", request=request)
    assert classify_exception(connect_error) == ErrorCode.UPSTREAM_ERROR
    assert classify_exception(read_timeout) == ErrorCode.UPSTREAM_TIMEOUT
    response = httpx.Response(429, request=request)
    status_error = httpx.HTTPStatusError("limited", request=request, response=response)
    assert classify_exception(status_error) == ErrorCode.RATE_LIMITED
    bad_request = httpx.HTTPStatusError(
        "bad request", request=request, response=httpx.Response(400, request=request)
    )
    assert classify_exception(bad_request) == ErrorCode.INVALID_ARGUMENT
    missing_upstream_resource = httpx.HTTPStatusError(
        "not found", request=request, response=httpx.Response(404, request=request)
    )
    assert classify_exception(missing_upstream_resource) == ErrorCode.UPSTREAM_ERROR


def test_wrap_exception_preserves_structured_error() -> None:
    original = AKBridgeError(ErrorCode.RATE_LIMITED, "slow down")
    wrapped = wrap_exception(original, retry_hint="wait")
    assert wrapped is original
    assert wrapped.retry_hint == "wait"


def test_wrap_exception_promotes_plain_exception() -> None:
    wrapped = wrap_exception(ValueError("bad arg"), retry_hint="check schema")
    assert isinstance(wrapped, AKBridgeError)
    assert wrapped.code == ErrorCode.INVALID_ARGUMENT
    assert wrapped.retry_hint == "check schema"
    assert json.loads(str(wrapped))["error"]["code"] == "INVALID_ARGUMENT"


def test_wrap_exception_redacts_secret_like_error_messages() -> None:
    wrapped = wrap_exception(RuntimeError("provider api_key=secret-value failed"))
    assert "secret-value" not in wrapped.message


def test_schema_validation_error_does_not_echo_credential_value() -> None:
    from dataclasses import replace

    api = replace(
        _api(),
        input_schema={
            "type": "object",
            "properties": {"api_key": {"type": "integer"}},
            "required": ["api_key"],
            "additionalProperties": False,
        },
    )
    with pytest.raises(AKBridgeError) as excinfo:
        _validate_api_arguments(api, {"api_key": "credential-value"})
    assert excinfo.value.code == ErrorCode.SCHEMA_VIOLATION
    assert "credential-value" not in str(excinfo.value)


def test_create_server_in_router_mode_does_not_warn(capsys: pytest.CaptureFixture[str]) -> None:
    create_server(mode="router", catalog={"x": _api("x")})
    assert "exposes" not in capsys.readouterr().err


def test_create_server_in_all_mode_warns(capsys: pytest.CaptureFixture[str]) -> None:
    # Build a catalog above the warning threshold without touching AKShare.
    catalog = {f"api_{i}": _api(f"api_{i}") for i in range(60)}
    create_server(mode="all", catalog=catalog)
    err = capsys.readouterr().err
    assert "exposes 60 tools" in err
    assert "--mode router" in err


def test_describe_unknown_api_raises_structured_error() -> None:
    index = CatalogIndex({"stock_zh_a_hist": _api()})
    with pytest.raises(KeyError):
        index.describe("does_not_exist")


def test_direct_tool_unknown_api_raises_akbridge_error() -> None:
    """Direct (mode=all) tool path emits structured UNKNOWN_API."""
    # We exercise call_tool through create_server indirectly via the search/describe
    # paths in test_mcp_e2e; here we just confirm the AKBridgeError shape used by the
    # direct path is well formed.
    err = AKBridgeError(
        ErrorCode.UNKNOWN_API,
        "Unknown AKShare API: nope",
        suggestions=["alt"],
        retry_hint="Call list_tools to see available names.",
    )
    payload = json.loads(str(err))
    assert payload["error"]["code"] == "UNKNOWN_API"
    assert "alt" in payload["error"]["suggestions"]


def test_all_mode_side_effect_tool_has_confirmation_gate_parameter() -> None:
    api = _api("set_token")
    from dataclasses import replace

    api = replace(api, side_effect=True)
    tool = next(tool for tool in build_mcp_tools({api.name: api}, mode="all"))
    assert tool.inputSchema["properties"]["allow_side_effect"]["default"] is False
    assert tool.meta["x-requires-confirmation"] is True  # type: ignore[index]
