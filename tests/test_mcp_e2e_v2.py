"""End-to-end MCP stdio tests for v0.2.0 capabilities.

These tests launch a real akbridge MCP server in a subprocess and verify the
wire protocol exposes structured content, prompts, and documentation chunks
as first-class MCP primitives.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import akshare
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _router_params(document_index: Path | None = None) -> StdioServerParameters:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    if document_index is not None:
        environment["AKBRIDGE_DOCUMENT_INDEX"] = str(document_index)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "akbridge.server", "--mode", "router"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=environment,
        encoding="utf-8",
    )


def test_router_tools_expose_output_schema_over_stdio() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
            by_name = {tool.name: tool for tool in tools.tools}
            for name in ("akbridge_search", "akbridge_describe", "akbridge_call"):
                assert name in by_name
                assert by_name[name].outputSchema is not None, f"{name} missing outputSchema"
            # Titles are surfaced to MCP clients.
            assert by_name["akbridge_search"].title == "AKBridge Search"
            assert by_name["akbridge_call"].title == "AKBridge Call"

    asyncio.run(exercise())


def test_structured_content_matches_unstructured_payload() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            search = await session.call_tool(
                "akbridge_search", {"query": "stock_zh_a_hist", "limit": 1}
            )
            assert not search.isError
            assert search.structuredContent is not None
            unstructured = json.loads(search.content[0].text)  # type: ignore[union-attr]
            assert search.structuredContent == unstructured
            assert search.structuredContent["results"][0]["name"] == "stock_zh_a_hist"

    asyncio.run(exercise())


def test_prompts_are_listed_and_rendered() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            prompts = await session.list_prompts()
            names = {item.name for item in prompts.prompts}
            assert "akbridge.query_financial_data" in names
            assert "akbridge.describe_api" in names
            assert "akbridge.search_catalog" in names

            rendered = await session.get_prompt(
                "akbridge.query_financial_data",
                {"question": "A股 000001 历史日线"},
            )
            assert rendered.messages
            text = rendered.messages[0].content.text  # type: ignore[union-attr]
            assert "akbridge_search" in text
            assert "akbridge_describe" in text
            assert "akbridge_call" in text
            assert "A股 000001 历史日线" in text

    asyncio.run(exercise())


def test_unknown_prompt_returns_structured_error() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            try:
                await session.get_prompt("akbridge.does_not_exist", {})
            except Exception as exc:  # mcp.shared.exceptions.McpError
                # The error message stringifies the JSON payload raised by the server.
                text = str(exc)
                # Should mention either the prompt name or the structured code.
                assert "does_not_exist" in text or "UNKNOWN_PROMPT" in text
            else:
                raise AssertionError("expected an error for unknown prompt")

    asyncio.run(exercise())


def test_known_prompt_missing_required_argument_is_invalid_argument() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            try:
                await session.get_prompt("akbridge.query_financial_data", {})
            except Exception as exc:  # mcp.shared.exceptions.McpError
                assert "INVALID_ARGUMENT" in str(exc)
            else:
                raise AssertionError("expected an error for a missing required prompt argument")

    asyncio.run(exercise())


def test_unknown_api_returns_structured_error_code() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool("akbridge_call", {"name": "definitely_not_an_api_xyz"})
            assert result.isError
            text = result.content[0].text  # type: ignore[union-attr]
            payload = json.loads(text)
            assert payload["error"]["code"] == "UNKNOWN_API"
            assert "suggestions" in payload["error"]
            assert "retry_hint" in payload["error"]

    asyncio.run(exercise())


def test_invalid_router_arguments_return_structured_schema_error() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool("akbridge_search", {"query": "CPI", "limit": 0})
            assert result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload["error"]["code"] == "SCHEMA_VIOLATION"
            assert "retry_hint" in payload["error"]

    asyncio.run(exercise())


def test_router_side_effect_call_requires_explicit_gate_flag() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool("akbridge_call", {"name": "set_token"})
            assert result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload["error"]["code"] == "SIDE_EFFECT_DENIED"

    asyncio.run(exercise())


def test_router_mode_rejects_unpublished_direct_api_tool() -> None:
    async def exercise() -> None:
        async with stdio_client(_router_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool("volatility_yz_rv", {})
            assert result.isError
            payload = json.loads(result.content[0].text)  # type: ignore[union-attr]
            assert payload["error"]["code"] == "TOOL_NOT_AVAILABLE"
            assert payload["error"]["details"]["mode"] == "router"

    asyncio.run(exercise())


def test_documentation_resource_is_searchable_and_readable(tmp_path: Path) -> None:
    index_path = tmp_path / "docs.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "akshare_version": str(akshare.__version__),
                "chunks": [
                    {
                        "id": "quotes chunk:1",
                        "title": "Quote documentation",
                        "path": "quotes.md",
                        "source_url": "https://example.test/quotes",
                        "text": "Documentation for stock_zh_a_hist and historical quotes.",
                        "api_names": ["stock_zh_a_hist"],
                        "categories": ["stock"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    async def exercise() -> None:
        async with (
            stdio_client(_router_params(index_path)) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            templates = await session.list_resource_templates()
            doc_template = next(
                (
                    item
                    for item in templates.resourceTemplates
                    if item.uriTemplate == "akbridge://docs/{chunk_id}"
                ),
                None,
            )
            assert doc_template is not None
            assert "percent-encoded chunk id" in doc_template.description
            search = await session.call_tool(
                "akbridge_search", {"query": "stock_zh_a_hist", "limit": 1}
            )
            assert not search.isError
            payload = search.structuredContent
            uri = payload["results"][0]["documentation"][0]["uri"]  # type: ignore[index]
            assert "%20" in uri and "%3A" in uri
            document = await session.read_resource(uri)
            text = document.contents[0].text  # type: ignore[union-attr]
            assert "Quote documentation" in text
            assert "stock_zh_a_hist" in text

    asyncio.run(exercise())
