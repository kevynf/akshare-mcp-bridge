"""Protocol-level MCP prompts for common AKBridge workflows.

These prompts complement the bundled :mod:`akbridge.skill` resource.  The
skill document is read on demand by the LLM, while prompts are surfaced
directly by MCP clients so users can select curated workflows from their
MCP Prompts interface.
"""

from __future__ import annotations

import json

from mcp.types import GetPromptResult, Prompt, PromptArgument, PromptMessage, TextContent

PROMPT_QUERY_DATA = "akbridge.query_financial_data"
PROMPT_DESCRIBE_API = "akbridge.describe_api"
PROMPT_SEARCH_CATALOG = "akbridge.search_catalog"


def list_prompts() -> list[Prompt]:
    """Return the stable prompt catalogue exposed to MCP clients."""
    return [
        Prompt(
            name=PROMPT_QUERY_DATA,
            title="查询金融数据",
            description=(
                "End-to-end workflow: search the AKShare catalog, describe the "
                "matching interface, then call it with structured output."
            ),
            arguments=[
                PromptArgument(
                    name="question",
                    description=(
                        "Natural-language description of the data you need, "
                        "e.g. 'A股 000001 近三个月日线行情' or 'latest China CPI'."
                    ),
                    required=True,
                ),
                PromptArgument(
                    name="category",
                    description=(
                        "Optional category filter such as stock, fund, macro, bond, "
                        "futures, option, forex, index, crypto, energy, banking."
                    ),
                    required=False,
                ),
                PromptArgument(
                    name="output_mode",
                    description="One of raw, compact, summary. Defaults to compact.",
                    required=False,
                ),
            ],
        ),
        Prompt(
            name=PROMPT_DESCRIBE_API,
            title="查看接口说明",
            description=(
                "Return the canonical schema, signature, parameters, return type "
                "and example call for one AKShare interface."
            ),
            arguments=[
                PromptArgument(
                    name="name",
                    description="Canonical AKShare function name or unique alias.",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name=PROMPT_SEARCH_CATALOG,
            title="检索接口目录",
            description=(
                "Lexical, deterministic search over the AKShare catalog.  Use this "
                "before inventing an interface name."
            ),
            arguments=[
                PromptArgument(
                    name="query",
                    description="Function name, alias, or natural-language keywords.",
                    required=True,
                ),
                PromptArgument(
                    name="category",
                    description="Optional category id such as stock or macro.",
                    required=False,
                ),
                PromptArgument(
                    name="limit",
                    description="Maximum hits (1-50). Defaults to 8.",
                    required=False,
                ),
            ],
        ),
    ]


def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    """Render one prompt as a single user message for the LLM."""
    args = dict(arguments or {})

    if name == PROMPT_QUERY_DATA:
        question = args.get("question", "").strip()
        if not question:
            raise ValueError(f"prompt {name} requires argument 'question'")
        category = args.get("category", "").strip()
        output_mode = (args.get("output_mode") or "compact").strip()
        lines = [
            "请使用 AKBridge 的三个 MCP 工具完成以下数据请求，"
            "严格遵循 search → describe → call 的顺序，不要凭空猜测接口名。",
            "",
            f"用户需求：{question}",
        ]
        if category:
            lines.append(f"建议类别：{category}")
        lines.extend(
            [
                f"输出模式：{output_mode}（如行数较多请用 page/page_size 分页）",
                "",
                "步骤：",
                "1. 调用 akbridge_search，query 用上面的用户需求"
                + (f"，category 设为 {category}" if category else "")
                + "，limit 建议 5-8。",
                "2. 从返回 results 里选最匹配的 1 个接口，"
                "调用 akbridge_describe 确认参数和返回类型。",
                "3. 调用 akbridge_call，name 用 describe 返回的规范 name，"
                "arguments 严格按 schema 构造，"
                f"output_mode 设为 {output_mode}。",
                "4. 如果 truncated=true 或 next_page 非空，向用户说明并询问是否翻页。",
                "5. 如果 side_effect=true，停下来询问用户授权；得到明确授权后，"
                "传 allow_side_effect=true 再调用。",
            ]
        )
        text = "\n".join(lines)
        return GetPromptResult(
            description=f"Query AKShare via search → describe → call: {question[:80]}",
            messages=[PromptMessage(role="user", content=TextContent(type="text", text=text))],
        )

    if name == PROMPT_DESCRIBE_API:
        api_name = args.get("name", "").strip()
        if not api_name:
            raise ValueError(f"prompt {name} requires argument 'name'")
        encoded_name = json.dumps(api_name, ensure_ascii=False)
        text = (
            f"请调用 akbridge_describe 工具，name 设为 {encoded_name}，"
            "include_schema 设为 true，"
            "然后把返回的签名、必填参数、返回类型、side_effect 标记和一个示例调用总结给用户。"
            "如果 describe 报告 UNKNOWN_API，"
            "请改用 akbridge_search 检索相近接口，再向用户列出建议。"
        )
        return GetPromptResult(
            description=f"Describe AKShare interface: {api_name}",
            messages=[PromptMessage(role="user", content=TextContent(type="text", text=text))],
        )

    if name == PROMPT_SEARCH_CATALOG:
        query = args.get("query", "").strip()
        if not query:
            raise ValueError(f"prompt {name} requires argument 'query'")
        category = args.get("category", "").strip()
        limit_raw = (args.get("limit") or "8").strip()
        try:
            limit = max(1, min(int(limit_raw), 50))
        except ValueError:
            limit = 8
        search_arguments: dict[str, str | int] = {"query": query, "limit": limit}
        if category:
            search_arguments["category"] = category
        args_doc = json.dumps(search_arguments, ensure_ascii=False)
        text = (
            f"请调用 akbridge_search，参数 {args_doc}。"
            "对返回的 results，按 score 从高到低列出 name、display_name、category、signature "
            "和 description 首行，并提示用户接下来可以调用 akbridge_describe 查看任一接口详情。"
        )
        return GetPromptResult(
            description=f"Search AKShare catalog: {query}",
            messages=[PromptMessage(role="user", content=TextContent(type="text", text=text))],
        )

    raise ValueError(f"unknown AKBridge prompt: {name}")


def prompt_names() -> tuple[str, ...]:
    """Return prompt names in deterministic order (used by server validation)."""
    return (PROMPT_QUERY_DATA, PROMPT_DESCRIBE_API, PROMPT_SEARCH_CATALOG)
