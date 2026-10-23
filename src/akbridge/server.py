"""AKBridge MCP server with full-catalog and model-friendly router modes."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import sys
from collections.abc import Mapping
from typing import Any

import akshare
import jsonschema
import mcp.server.stdio
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.lowlevel.server import ReadResourceContents
from mcp.server.models import InitializationOptions
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    GetPromptResult,
    Prompt,
    Resource,
    ResourceTemplate,
    TextContent,
    Tool,
    ToolAnnotations,
)

from . import __version__
from .catalog import ApiFunction, coerce_arguments, discover_functions
from .documents import load_builtin_document_chunks, load_document_chunks
from .errors import AKBridgeError, ErrorCode, wrap_exception
from .observability import configure_logging
from .prompts import get_prompt, list_prompts, prompt_names
from .reliability import (
    CallExecutor,
    RateLimiter,
    RetryPolicy,
    TTLCache,
    proxy_environment,
    redact_secrets,
)
from .router import DOC_URI_PREFIX, ROUTER_TOOL_NAMES, CatalogIndex, router_tool_definitions
from .serialization import to_jsonable
from .skill import SKILL_TEXT, SKILL_URI

VALID_MODES = {"all", "router", "hybrid"}
VALID_TRANSPORTS = {"stdio", "sse", "http"}
METRICS_URI = "akbridge://metrics"
ALL_MODE_WARNING_THRESHOLD = 50  # warn when exposing more than this many tools


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    """Parse a comma-separated environment variable into trimmed values."""
    raw = os.getenv(name)
    if raw is None:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _apply_proxy_aliases() -> None:
    # AKBRIDGE_* variables are explicit opt-in aliases and never overwrite a
    # conventional proxy already supplied by the parent process.
    environ = proxy_environment()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        if environ.get(key) and not os.environ.get(key):
            os.environ[key] = environ[key]


def _default_executor() -> CallExecutor:
    cache_ttl = max(0.0, _env_float("AKBRIDGE_CACHE_TTL", 0.0))
    cache = (
        TTLCache(
            maxsize=max(1, _env_int("AKBRIDGE_CACHE_SIZE", 256)),
            ttl=cache_ttl,
        )
        if cache_ttl > 0
        else None
    )
    return CallExecutor(
        retry_policy=RetryPolicy.from_env(),
        cache=cache,
        rate_limiter=RateLimiter(max(0.0, _env_float("AKBRIDGE_RATE_LIMIT_SECONDS", 0.0))),
        failure_threshold=max(1, _env_int("AKBRIDGE_CIRCUIT_FAILURE_THRESHOLD", 5)),
        recovery_timeout=max(0.0, _env_float("AKBRIDGE_CIRCUIT_RECOVERY_SECONDS", 30.0)),
        logger=configure_logging(),
    )


def _json_content(payload: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, default=str))]


def _json_safe(value: Any) -> Any:
    """Normalize arbitrary serializer output to JSON primitives for MCP fields."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _first_line(text: str, *, limit: int = 200) -> str:
    line = (text or "").strip().splitlines()[0] if text else ""
    return line[:limit]


def _side_effect_description(api: ApiFunction, *, describe_available: bool) -> str:
    """Compact tool description that warns the LLM before mutating calls."""
    headline = _first_line(api.description)
    detail_hint = (
        "Call akbridge_describe for the full schema and examples."
        if describe_available
        else "Review the declared input schema and source documentation before calling."
    )
    if api.side_effect:
        return (
            f"⚠️ SIDE EFFECT: this interface may mutate global state, submit credentials "
            f"or trigger login flows; require explicit user authorization before calling. "
            f"{headline} {detail_hint}"
        )
    return f"{headline} {detail_hint}"


def _validate_api_arguments(api: ApiFunction, arguments: Any) -> None:
    """Validate provider arguments and raise a structured schema error."""
    try:
        jsonschema.validate(instance=arguments, schema=api.input_schema)
    except jsonschema.ValidationError as exc:
        raise AKBridgeError(
            ErrorCode.SCHEMA_VIOLATION,
            f"Input validation failed for {api.name}: "
            "arguments do not satisfy the declared schema.",
            retry_hint=(
                "Call akbridge_describe to review the API schema, then retry with "
                "arguments matching its declared types and constraints."
            ),
            details={
                "api": api.name,
                "path": [str(part) for part in exc.absolute_path],
                "validator": exc.validator,
            },
        ) from exc


def build_mcp_tools(catalog: Mapping[str, ApiFunction], *, mode: str) -> list[Tool]:
    """Build the exact MCP tool list without starting a transport.

    Maintenance uses this pure construction step to validate every generated
    input schema offline before a client or provider is involved.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"unsupported mode: {mode}; choose all, router, or hybrid")
    tools: list[Tool] = []
    if mode in {"router", "hybrid"}:
        for item in router_tool_definitions():
            tools.append(
                Tool(
                    name=item["name"],
                    title=item.get("title"),
                    description=item["description"],
                    inputSchema=item["inputSchema"],
                    outputSchema=item.get("outputSchema"),
                    annotations=ToolAnnotations(
                        title=item.get("title"),
                        readOnlyHint=item["name"] != "akbridge_call",
                        destructiveHint=item["name"] == "akbridge_call",
                        idempotentHint=item["name"] != "akbridge_call",
                        openWorldHint=item["name"] == "akbridge_call",
                    ),
                    _meta=item.get("meta"),
                )
            )
    if mode in {"all", "hybrid"}:
        for api in catalog.values():
            description = (
                _side_effect_description(api, describe_available=mode in {"router", "hybrid"})
                if api.side_effect
                else _first_line(api.description)
            )
            meta: dict[str, Any] = {"category": api.category, "side_effect": api.side_effect}
            if api.side_effect:
                meta["x-requires-confirmation"] = True
            if api.source_url:
                meta["documentation_uri"] = api.source_url
            input_schema = api.input_schema
            if api.side_effect:
                input_schema = {
                    **api.input_schema,
                    "properties": {
                        **api.input_schema.get("properties", {}),
                        "allow_side_effect": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "Required explicit acknowledgement after user authorization. "
                                "This flag alone does not establish consent."
                            ),
                        },
                    },
                }
            tools.append(
                Tool(
                    name=api.name,
                    title=api.display_name or api.name,
                    description=description,
                    inputSchema=input_schema,
                    annotations=ToolAnnotations(
                        title=api.display_name or api.name,
                        readOnlyHint=not api.side_effect,
                        destructiveHint=api.side_effect,
                        idempotentHint=not api.side_effect,
                        openWorldHint=True,
                    ),
                    _meta=meta,
                )
            )
    return tools


def invoke_api(
    api: ApiFunction,
    arguments: Mapping[str, Any] | None,
    *,
    executor: CallExecutor,
    row_limit: int,
    output_mode: str = "raw",
    page: int = 1,
    page_size: int | None = None,
    include_metadata: bool = False,
) -> Any:
    """Coerce, execute and serialize one catalog entry.

    This synchronous helper is public so acceptance and offline tests can
    exercise exactly the same path as the MCP handler without a client or LLM.
    """
    call_arguments = coerce_arguments(api.function, dict(arguments or {}))
    value = executor.call(api.name, api.function, call_arguments, side_effect=api.side_effect)
    payload = to_jsonable(
        value,
        row_limit=row_limit,
        mode=output_mode,
        page=page,
        page_size=page_size,
        include_metadata=include_metadata,
    )
    # Credential helper APIs must not echo a configured token over MCP.
    return redact_secrets(payload, key_hint=api.name)


async def invoke_api_async(
    api: ApiFunction,
    arguments: Mapping[str, Any] | None,
    *,
    executor: CallExecutor,
    row_limit: int,
    output_mode: str = "raw",
    page: int = 1,
    page_size: int | None = None,
    include_metadata: bool = False,
    call_timeout: float | None = None,
) -> Any:
    """Async MCP boundary with a response timeout around the sync provider call."""
    coroutine = asyncio.to_thread(
        invoke_api,
        api,
        arguments,
        executor=executor,
        row_limit=row_limit,
        output_mode=output_mode,
        page=page,
        page_size=page_size,
        include_metadata=include_metadata,
    )
    if call_timeout is None or call_timeout <= 0:
        return await coroutine
    try:
        return await asyncio.wait_for(coroutine, timeout=call_timeout)
    except TimeoutError as exc:
        raise AKBridgeError(
            ErrorCode.UPSTREAM_TIMEOUT,
            f"AKBridge call exceeded {call_timeout}s: {api.name}",
            retry_hint=(
                "Increase --call-timeout, narrow the date range, or retry with "
                "output_mode='summary' to reduce provider work."
            ),
            details={"api": api.name, "timeout_seconds": call_timeout},
        ) from exc


def create_server(
    *,
    row_limit: int = 5000,
    mode: str | None = None,
    output_mode: str | None = None,
    catalog: dict[str, ApiFunction] | None = None,
    executor: CallExecutor | None = None,
    call_timeout: float | None = None,
    document_index_path: str | None = None,
) -> Server:
    """Create an MCP server.

    ``router`` (the default) exposes three stable tools that search and call the
    local semantic catalog; ``all`` preserves the original one-tool-per-AKShare-
    function surface; ``hybrid`` publishes both for migration and debugging.
    """
    if row_limit < 1:
        raise ValueError("row_limit must be at least 1")
    selected_mode = (mode or os.getenv("AKBRIDGE_MODE", "router")).casefold()
    if selected_mode not in VALID_MODES:
        raise ValueError(f"unsupported mode: {selected_mode}; choose all, router, or hybrid")
    _apply_proxy_aliases()
    catalog = discover_functions() if catalog is None else catalog
    if selected_mode in {"all", "hybrid"} and len(catalog) > ALL_MODE_WARNING_THRESHOLD:
        print(
            f"akbridge: warning: mode={selected_mode!r} exposes {len(catalog)} tools; "
            "this may exceed MCP client tool limits.  Consider --mode router.",
            file=sys.stderr,
        )
    document_index_path = document_index_path or os.getenv("AKBRIDGE_DOCUMENT_INDEX")
    akshare_version = str(getattr(akshare, "__version__", "unknown"))
    documents = (
        load_document_chunks(document_index_path, expected_version=akshare_version)
        if document_index_path
        else load_builtin_document_chunks(expected_version=akshare_version)
    )
    index = CatalogIndex(catalog, documents)
    call_executor = executor or _default_executor()
    default_output = output_mode or os.getenv(
        "AKBRIDGE_OUTPUT_MODE", "compact" if selected_mode == "router" else "raw"
    )
    if default_output not in {"raw", "compact", "summary"}:
        raise ValueError("output_mode must be raw, compact, or summary")
    effective_timeout = (
        call_timeout if call_timeout is not None else _env_float("AKBRIDGE_CALL_TIMEOUT", 120.0)
    )
    effective_timeout = effective_timeout if effective_timeout and effective_timeout > 0 else None
    server = Server("akbridge")

    # Expose observability and catalog handles for embedders without adding
    # them to the MCP wire protocol.
    server.akbridge_catalog = catalog  # type: ignore[attr-defined]
    server.akbridge_index = index  # type: ignore[attr-defined]
    server.akbridge_executor = call_executor  # type: ignore[attr-defined]
    server.akbridge_mode = selected_mode  # type: ignore[attr-defined]
    server.akbridge_call_timeout = effective_timeout  # type: ignore[attr-defined]
    published_tools = build_mcp_tools(catalog, mode=selected_mode)
    tool_schemas = {tool.name: tool.inputSchema for tool in published_tools}

    async def invoke_in_thread(
        api: ApiFunction,
        call_arguments: Mapping[str, Any] | None,
        *,
        mode_value: str,
        page: int = 1,
        page_size: int | None = None,
        include_metadata: bool = False,
    ) -> Any:
        return await invoke_api_async(
            api,
            call_arguments,
            executor=call_executor,
            row_limit=row_limit,
            output_mode=mode_value,
            page=page,
            page_size=page_size,
            include_metadata=include_metadata,
            call_timeout=effective_timeout,
        )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return build_mcp_tools(catalog, mode=selected_mode)

    @server.call_tool(validate_input=False)
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> tuple[list[TextContent], dict[str, Any]]:
        supplied = dict(arguments or {})
        if name not in tool_schemas:
            unavailable_router_tool = name in ROUTER_TOOL_NAMES
            unavailable_direct_api = name in catalog
            if unavailable_router_tool or unavailable_direct_api:
                retry_hint = (
                    "Start AKBridge with --mode router or --mode hybrid to use router tools."
                    if unavailable_router_tool
                    else "Use akbridge_search and akbridge_call, or start AKBridge with --mode all."
                )
                raise AKBridgeError(
                    ErrorCode.TOOL_NOT_AVAILABLE,
                    f"Tool {name!r} is not available in mode {selected_mode!r}.",
                    retry_hint=retry_hint,
                    details={"requested": name, "mode": selected_mode},
                )
        # Check side effects before schema validation so the user receives the
        # authorization gate even when required provider arguments are absent.
        direct_api = catalog.get(name) if name not in ROUTER_TOOL_NAMES else None
        if direct_api and direct_api.side_effect and not supplied.get("allow_side_effect", False):
            raise AKBridgeError(
                ErrorCode.SIDE_EFFECT_DENIED,
                f"Calling {direct_api.name} may modify global state or credentials.",
                retry_hint=(
                    "Explain the side effect and obtain explicit user authorization. "
                    "Only then retry with allow_side_effect=true."
                ),
                details={"api": direct_api.name, "side_effect": True},
            )
        schema = tool_schemas.get(name)
        if schema is not None:
            try:
                jsonschema.validate(instance=supplied, schema=schema)
            except jsonschema.ValidationError as exc:
                path = [str(part) for part in exc.absolute_path]
                raise AKBridgeError(
                    ErrorCode.SCHEMA_VIOLATION,
                    "Input validation failed: arguments do not satisfy the declared schema.",
                    retry_hint=(
                        "Call akbridge_describe to review the schema, then retry with "
                        "arguments matching the declared types and constraints."
                    ),
                    details={"path": path, "validator": exc.validator},
                ) from exc

        if name == "akbridge_search":
            try:
                payload = index.search_payload(
                    supplied.get("query", ""),
                    category=supplied.get("category"),
                    limit=supplied.get("limit", 8),
                )
            except Exception as exc:
                raise wrap_exception(exc, retry_hint="Adjust query or category filter.") from exc
            payload = _json_safe(payload)
            return _json_content(payload), payload

        if name == "akbridge_describe":
            requested = supplied.get("name") or supplied.get("api")
            if not requested:
                raise AKBridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    "akbridge_describe requires the 'name' argument",
                    retry_hint="Call akbridge_search to discover candidate names first.",
                )
            try:
                payload = index.describe(
                    str(requested), include_schema=supplied.get("include_schema", True)
                )
            except KeyError as exc:
                suggestions = [item["name"] for item in index.suggestions(str(requested), limit=5)]
                raise AKBridgeError(
                    ErrorCode.UNKNOWN_API,
                    f"Unknown AKShare API: {requested}",
                    suggestions=suggestions,
                    retry_hint="Call akbridge_search with natural-language keywords.",
                    details={"requested": str(requested)},
                ) from exc
            except Exception as exc:
                raise wrap_exception(exc) from exc
            payload = _json_safe(payload)
            return _json_content(payload), payload

        if name == "akbridge_call":
            requested = supplied.get("name") or supplied.get("api")
            if not requested:
                raise AKBridgeError(
                    ErrorCode.INVALID_ARGUMENT,
                    "akbridge_call requires the 'name' argument",
                    retry_hint="Call akbridge_describe first to confirm the canonical name.",
                )
            api = index.resolve(str(requested))
            if api is None:
                suggestions = [item["name"] for item in index.suggestions(str(requested), limit=5)]
                raise AKBridgeError(
                    ErrorCode.UNKNOWN_API,
                    f"Unknown AKShare API: {requested}",
                    suggestions=suggestions,
                    retry_hint=(
                        "Use akbridge_search to find candidates, then akbridge_describe "
                        "to confirm the canonical name and schema."
                    ),
                    details={"requested": str(requested)},
                )
            if api.side_effect and not supplied.get("allow_side_effect", False):
                raise AKBridgeError(
                    ErrorCode.SIDE_EFFECT_DENIED,
                    f"Calling {api.name} may modify global state or credentials.",
                    retry_hint=(
                        "Explain the side effect and obtain explicit user authorization. "
                        "Only then retry with allow_side_effect=true."
                    ),
                    details={"api": api.name, "side_effect": True},
                )
            _validate_api_arguments(api, supplied.get("arguments", {}))
            mode_value = supplied.get("output_mode", default_output)
            try:
                result = await invoke_in_thread(
                    api,
                    supplied.get("arguments", {}),
                    mode_value=mode_value,
                    page=int(supplied.get("page", 1)),
                    page_size=(
                        int(supplied["page_size"])
                        if supplied.get("page_size") is not None
                        else None
                    ),
                    include_metadata=bool(supplied.get("include_metadata", True)),
                )
            except AKBridgeError:
                raise
            except Exception as exc:
                retry_hint = (
                    "Check the input_schema via akbridge_describe and retry; "
                    "if the provider is failing, consider a fallback or reduce page size."
                )
                raise wrap_exception(exc, retry_hint=retry_hint) from exc
            payload: dict[str, Any] = {
                "name": api.name,
                "requested_name": str(requested),
                "output_mode": mode_value,
                "result": result,
            }
            # Metrics are opt-in: by_api accumulates forever and would otherwise
            # grow every response.  The akbridge://metrics resource is the
            # canonical place for full diagnostics.
            if bool(supplied.get("include_metrics", False)):
                payload["metrics"] = call_executor.metrics.snapshot()
            payload = _json_safe(payload)
            return _json_content(payload), payload

        # ``all`` / ``hybrid`` direct-AKShare tool path.
        api = catalog.get(name)
        if api is None:
            suggestions = [item["name"] for item in index.suggestions(name, limit=5)]
            raise AKBridgeError(
                ErrorCode.UNKNOWN_API,
                f"Unknown AKShare API: {name}",
                suggestions=suggestions,
                retry_hint=(
                    "In --mode router use akbridge_search to discover candidates; "
                    "in --mode all check list_tools for the exact name."
                ),
                details={"requested": name},
            )
        if api.side_effect and not supplied.get("allow_side_effect", False):
            raise AKBridgeError(
                ErrorCode.SIDE_EFFECT_DENIED,
                f"Calling {api.name} may modify global state or credentials.",
                retry_hint=(
                    "Explain the side effect and obtain explicit user authorization. "
                    "Only then retry with allow_side_effect=true."
                ),
                details={"api": api.name, "side_effect": True},
            )
        supplied.pop("allow_side_effect", None)
        _validate_api_arguments(api, supplied)
        try:
            result = await invoke_in_thread(api, supplied, mode_value=default_output)
        except AKBridgeError:
            raise
        except Exception as exc:
            raise wrap_exception(exc) from exc
        # Direct-tool calls keep the legacy wire shape (result only). Structured
        # output is reserved for the stable router envelopes with declared schemas.
        return _json_content(result)

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        resources = [
            Resource(
                uri=SKILL_URI,
                name="akbridge-skill",
                title="AKBridge 运行规程",
                description="Deterministic instructions for searching and calling AKBridge.",
                mimeType="text/markdown",
            ),
            Resource(
                uri=METRICS_URI,
                name="akbridge-metrics",
                title="AKBridge Metrics",
                description="Process-local AKBridge call counters and durations.",
                mimeType="application/json",
            ),
        ]
        return resources

    @server.list_resource_templates()
    async def list_resource_templates() -> list[ResourceTemplate]:
        return [
            ResourceTemplate(
                uriTemplate=f"{DOC_URI_PREFIX}{{chunk_id}}",
                name="akshare-documentation-chunk",
                title="AKShare Documentation Chunk",
                description=(
                    "Read one AKShare documentation chunk. Replace {chunk_id} with the "
                    "percent-encoded chunk id returned by akbridge_search."
                ),
                mimeType="text/markdown",
            )
        ]

    @server.read_resource()
    async def read_resource(uri: Any) -> list[ReadResourceContents]:
        uri_str = str(uri)
        if uri_str == SKILL_URI:
            return [ReadResourceContents(content=SKILL_TEXT, mime_type="text/markdown")]
        if uri_str == METRICS_URI:
            return [
                ReadResourceContents(
                    content=json.dumps(call_executor.metrics.snapshot(), ensure_ascii=False),
                    mime_type="application/json",
                )
            ]
        if uri_str.startswith(DOC_URI_PREFIX):
            from urllib.parse import unquote

            chunk_id = unquote(uri_str[len(DOC_URI_PREFIX) :])
            chunk = index.document_chunk(chunk_id)
            if chunk is None:
                raise AKBridgeError(
                    ErrorCode.UNKNOWN_RESOURCE,
                    f"Unknown AKBridge documentation chunk: {chunk_id}",
                    retry_hint="Call akbridge_search to find documentation chunks and their URIs.",
                    details={"uri": uri_str},
                )
            # Surface upstream URL so an LLM can cross-reference without
            # fetching remote content during a session.
            header = (
                f"# {chunk.get('title') or chunk_id}\n\n"
                f"Source: {chunk.get('source_url') or 'unknown'}\n"
                f"APIs: {', '.join(chunk.get('api_names', [])) or '—'}\n\n"
                "---\n\n"
            )
            return [
                ReadResourceContents(
                    content=header + chunk.get("text", ""),
                    mime_type="text/markdown",
                )
            ]
        raise AKBridgeError(
            ErrorCode.UNKNOWN_RESOURCE,
            f"Unknown AKBridge resource: {uri_str}",
            retry_hint="Call list_resources to enumerate available URIs.",
        )

    @server.list_prompts()
    async def _list_prompts() -> list[Prompt]:
        return list_prompts() if selected_mode in {"router", "hybrid"} else []

    @server.get_prompt()
    async def _get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        if selected_mode == "all":
            raise AKBridgeError(
                ErrorCode.TOOL_NOT_AVAILABLE,
                "MCP workflow prompts require router tools, which are not enabled in mode 'all'.",
                retry_hint="Start AKBridge with --mode router or --mode hybrid to use MCP Prompts.",
                details={"requested": name, "mode": selected_mode},
            )
        try:
            return get_prompt(name, arguments)
        except ValueError as exc:
            code = (
                ErrorCode.UNKNOWN_PROMPT
                if name not in prompt_names()
                else ErrorCode.INVALID_ARGUMENT
            )
            raise AKBridgeError(
                code,
                str(exc),
                retry_hint=(
                    "Call prompts/list to see available prompts."
                    if code == ErrorCode.UNKNOWN_PROMPT
                    else "Provide all required arguments shown by prompts/list."
                ),
                details={"requested": name},
            ) from exc

    return server


async def run_stdio(
    *, row_limit: int, mode: str = "router", output_mode: str | None = None
) -> None:
    server = create_server(row_limit=row_limit, mode=mode, output_mode=output_mode)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="akbridge",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def create_sse_app(
    *,
    row_limit: int = 5000,
    mode: str | None = None,
    output_mode: str | None = None,
) -> Any:
    """Build an optional Starlette SSE app without starting a listener.

    .. deprecated::
        The MCP specification has superseded SSE with Streamable HTTP.  Use
        :func:`create_http_app` for new deployments; SSE is kept for backward
        compatibility and will be removed in a future release.
    """
    try:
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Mount, Route
    except ImportError as exc:  # pragma: no cover - depends on installation extras
        raise RuntimeError("SSE transport requires starlette and mcp SSE dependencies") from exc

    server = create_server(row_limit=row_limit, mode=mode, output_mode=output_mode)
    sse_path = os.getenv("AKBRIDGE_SSE_PATH", "/sse")
    message_path = os.getenv("AKBRIDGE_MESSAGE_PATH", "/messages/")
    transport = SseServerTransport(message_path)

    async def handle_sse(request: Any) -> Response:
        async with transport.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        return Response()

    return Starlette(
        routes=[
            Route(sse_path, endpoint=handle_sse, methods=["GET"]),
            Mount(message_path, app=transport.handle_post_message),
        ]
    )


async def run_sse(
    *,
    row_limit: int,
    mode: str = "router",
    output_mode: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the legacy HTTP/SSE transport (deprecated; prefer :func:`run_http`)."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on installation extras
        raise RuntimeError("SSE transport requires uvicorn") from exc
    app = create_sse_app(row_limit=row_limit, mode=mode, output_mode=output_mode)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()


def create_http_app(
    *,
    row_limit: int = 5000,
    mode: str | None = None,
    output_mode: str | None = None,
    json_response: bool = False,
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
    bearer_token: str | None = None,
) -> Any:
    """Build a Starlette app that serves the Streamable HTTP MCP transport.

    Streamable HTTP is the recommended MCP HTTP transport since 2025-03-26,
    replacing the legacy SSE transport.  A single endpoint (default ``/mcp``)
    accepts POST requests carrying JSON-RPC frames and upgrades to a streamed
    response when the server has more to say.
    """
    try:
        from contextlib import asynccontextmanager

        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.routing import Mount
    except ImportError as exc:  # pragma: no cover - depends on installation extras
        raise RuntimeError(
            "Streamable HTTP transport requires the 'mcp' SDK HTTP extras and starlette"
        ) from exc

    server = create_server(row_limit=row_limit, mode=mode, output_mode=output_mode)
    manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=json_response,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts
            or _env_list(
                "AKBRIDGE_HTTP_ALLOWED_HOSTS",
                [
                    "localhost",
                    "localhost:*",
                    "127.0.0.1",
                    "127.0.0.1:*",
                    "[::1]",
                    "[::1]:*",
                ],
            ),
            allowed_origins=allowed_origins or _env_list("AKBRIDGE_HTTP_ALLOWED_ORIGINS", []),
        ),
    )
    http_path = os.getenv("AKBRIDGE_HTTP_PATH", "/mcp")
    expected_token = bearer_token or os.getenv("AKBRIDGE_HTTP_BEARER_TOKEN")

    async def handle_mcp(scope: Any, receive: Any, send: Any) -> None:
        if expected_token:
            authorization = next(
                (
                    value.decode("latin-1")
                    for key, value in scope.get("headers", [])
                    if key.lower() == b"authorization"
                ),
                "",
            )
            scheme, _, supplied_token = authorization.partition(" ")
            if scheme.casefold() != "bearer" or not hmac.compare_digest(
                supplied_token.encode("utf-8"), expected_token.encode("utf-8")
            ):
                from starlette.responses import Response

                response = Response(
                    "Unauthorized",
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await manager.handle_request(scope, receive, send)

    @asynccontextmanager
    async def lifespan(_app: Any):
        async with manager.run():
            yield

    app = Starlette(
        routes=[Mount(http_path, app=handle_mcp)],
        lifespan=lifespan,
    )
    app.state.akbridge_http_session_manager = manager
    return app


async def run_http(
    *,
    row_limit: int,
    mode: str = "router",
    output_mode: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    json_response: bool = False,
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
    bearer_token: str | None = None,
) -> None:
    """Run the Streamable HTTP MCP transport (recommended for network deployments)."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on installation extras
        raise RuntimeError("Streamable HTTP transport requires uvicorn") from exc
    app = create_http_app(
        row_limit=row_limit,
        mode=mode,
        output_mode=output_mode,
        json_response=json_response,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
        bearer_token=bearer_token,
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Expose AKShare over MCP")
    parser.add_argument("--row-limit", type=int, default=5000)
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default=os.getenv("AKBRIDGE_MODE", "router"),
        help=(
            "Tool surface. 'router' (default) exposes three stable tools; 'all' "
            "exposes one tool per AKShare function (large); 'hybrid' exposes both."
        ),
    )
    parser.add_argument("--output-mode", choices=["raw", "compact", "summary"])
    parser.add_argument(
        "--transport",
        choices=sorted(VALID_TRANSPORTS),
        default=os.getenv("AKBRIDGE_TRANSPORT", "stdio"),
        help=(
            "Wire transport. 'stdio' (default) is the standard MCP transport; "
            "'http' is the recommended network transport (Streamable HTTP); "
            "'sse' is legacy and deprecated."
        ),
    )
    parser.add_argument("--host", default=os.getenv("AKBRIDGE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=_env_int("AKBRIDGE_PORT", 8000))
    parser.add_argument(
        "--call-timeout", type=float, default=_env_float("AKBRIDGE_CALL_TIMEOUT", 120.0)
    )
    parser.add_argument(
        "--http-json-response",
        action="store_true",
        default=os.getenv("AKBRIDGE_HTTP_JSON_RESPONSE", "0") == "1",
        help=(
            "Force the HTTP transport to return plain JSON responses instead of "
            "SSE streams.  Useful for clients without SSE support."
        ),
    )
    parser.add_argument(
        "--http-allowed-host",
        action="append",
        default=None,
        help=(
            "Allowed HTTP Host header (repeatable). Defaults to localhost, 127.0.0.1, "
            "and [::1] on any port; configure this when binding to a network interface."
        ),
    )
    parser.add_argument(
        "--http-allowed-origin",
        action="append",
        default=None,
        help=(
            "Allowed browser Origin (repeatable). Cross-origin requests are denied by "
            "default; use an exact origin such as https://mcp.example.com."
        ),
    )
    parser.add_argument(
        "--document-index",
        help="Path to a local index built with akbridge-docs; never fetched at request time.",
    )
    args = parser.parse_args()
    if args.document_index:
        os.environ["AKBRIDGE_DOCUMENT_INDEX"] = args.document_index
    os.environ["AKBRIDGE_CALL_TIMEOUT"] = str(args.call_timeout)
    if args.transport == "sse":
        print(
            "akbridge: warning: --transport sse is deprecated; prefer --transport http.",
            file=sys.stderr,
        )
        asyncio.run(
            run_sse(
                row_limit=args.row_limit,
                mode=args.mode,
                output_mode=args.output_mode,
                host=args.host,
                port=args.port,
            )
        )
    elif args.transport == "http":
        asyncio.run(
            run_http(
                row_limit=args.row_limit,
                mode=args.mode,
                output_mode=args.output_mode,
                host=args.host,
                port=args.port,
                json_response=args.http_json_response,
                allowed_hosts=args.http_allowed_host,
                allowed_origins=args.http_allowed_origin,
            )
        )
    else:
        asyncio.run(
            run_stdio(row_limit=args.row_limit, mode=args.mode, output_mode=args.output_mode)
        )


if __name__ == "__main__":
    main()
