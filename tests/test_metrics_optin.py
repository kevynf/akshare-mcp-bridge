"""Metrics are opt-in on ``akbridge_call`` to keep default responses small."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _server_params() -> StdioServerParameters:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "akbridge.server", "--mode", "router"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=environment,
        encoding="utf-8",
    )


def _fixture() -> dict[str, object]:
    fixture_path = Path(__file__).resolve().parents[1] / "artifacts/acceptance/fixtures.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))["volatility_yz_rv"]


def test_metrics_omitted_by_default_and_included_on_request() -> None:
    async def exercise() -> None:
        async with stdio_client(_server_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            fixture = _fixture()

            default_call = await session.call_tool(
                "akbridge_call",
                {
                    "name": "volatility_yz_rv",
                    "arguments": fixture,
                    "output_mode": "summary",
                },
            )
            assert not default_call.isError
            default_payload = json.loads(default_call.content[0].text)
            assert "metrics" not in default_payload

            explicit_call = await session.call_tool(
                "akbridge_call",
                {
                    "name": "volatility_yz_rv",
                    "arguments": fixture,
                    "output_mode": "summary",
                    "include_metrics": True,
                },
            )
            assert not explicit_call.isError
            explicit_payload = json.loads(explicit_call.content[0].text)
            assert "metrics" in explicit_payload
            assert explicit_payload["metrics"]["calls"] >= 1

    asyncio.run(exercise())


def test_metrics_resource_always_available() -> None:
    async def exercise() -> None:
        async with stdio_client(_server_params()) as streams, ClientSession(*streams) as session:
            await session.initialize()
            fixture = _fixture()
            await session.call_tool(
                "akbridge_call",
                {
                    "name": "volatility_yz_rv",
                    "arguments": fixture,
                    "output_mode": "summary",
                },
            )
            metrics = await session.read_resource("akbridge://metrics")
            text = metrics.contents[0].text  # type: ignore[union-attr]
            snapshot = json.loads(text)
            assert snapshot["calls"] >= 1
            assert "by_api" in snapshot

    asyncio.run(exercise())
