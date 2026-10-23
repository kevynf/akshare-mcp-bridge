"""Tests for the protocol-level MCP prompts exposed by the server."""

from __future__ import annotations

import pytest
from mcp.types import Prompt

from akbridge.prompts import (
    PROMPT_DESCRIBE_API,
    PROMPT_QUERY_DATA,
    PROMPT_SEARCH_CATALOG,
    get_prompt,
    list_prompts,
    prompt_names,
)


def test_list_prompts_returns_three_stable_prompts() -> None:
    prompts = list_prompts()
    assert all(isinstance(item, Prompt) for item in prompts)
    names = {item.name for item in prompts}
    assert names == {PROMPT_QUERY_DATA, PROMPT_DESCRIBE_API, PROMPT_SEARCH_CATALOG}
    assert names == set(prompt_names())


def test_each_prompt_has_titles_and_arguments() -> None:
    for prompt in list_prompts():
        assert prompt.title
        assert prompt.description
        assert prompt.arguments is not None
        # At least one required argument for each workflow.
        assert any(arg.required for arg in prompt.arguments)


def test_query_data_prompt_renders_workflow_text() -> None:
    result = get_prompt(
        PROMPT_QUERY_DATA,
        {"question": "A股 000001 历史日线", "category": "stock", "output_mode": "summary"},
    )
    assert result.messages
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert "akbridge_search" in text
    assert "akbridge_describe" in text
    assert "akbridge_call" in text
    assert "A股 000001 历史日线" in text
    assert "stock" in text
    assert "summary" in text


def test_query_data_prompt_requires_question() -> None:
    with pytest.raises(ValueError, match="question"):
        get_prompt(PROMPT_QUERY_DATA, {})


def test_describe_api_prompt_includes_canonical_name() -> None:
    result = get_prompt(PROMPT_DESCRIBE_API, {"name": "stock_zh_a_hist"})
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert "stock_zh_a_hist" in text
    assert "akbridge_describe" in text


def test_search_catalog_prompt_clamps_limit() -> None:
    result = get_prompt(PROMPT_SEARCH_CATALOG, {"query": "CPI", "limit": "999"})
    text = result.messages[0].content.text  # type: ignore[union-attr]
    assert '"limit": 50' in text
    assert "CPI" in text


def test_unknown_prompt_raises() -> None:
    with pytest.raises(ValueError, match="unknown AKBridge prompt"):
        get_prompt("akbridge.nonexistent", {})
