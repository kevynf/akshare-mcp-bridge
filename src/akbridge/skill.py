"""The bundled, deterministic model-facing usage guide exposed as a resource."""

from __future__ import annotations

SKILL_URI = "akbridge://skill"

SKILL_TEXT = """# AKBridge Agent 运行规程

## 1. 调用顺序

- 先调用 `akbridge_search`，按接口名、数据主题或类别检索候选接口。
- 再调用 `akbridge_describe`，确认规范名称、必填参数、签名、返回类型和 `side_effect`。
- 最后调用 `akbridge_call`，只使用已确认的规范名称；参数必须放在 `arguments` 中。

## 2. 路由优先级

- 优先使用精确接口名或唯一别名；自然语言需求必须先检索，不能猜接口名。
- 文档命中只补充术语和排序证据，不改变源码目录的类别或模块路由。
- 候选不唯一或缺少必填参数时，先澄清，不要直接调用。

## 3. 文档索引

- 有包内或本地文档索引时，用它补充搜索结果；搜索期间不联网。
- `--document-index` 只覆盖默认索引；索引缺失时回退到内置源码目录路由。
- 搜索结果中的 `documentation[].uri` 可通过 `resources/read` 读取对应 AKShare 文档块；
  资源模板通过 `resources/templates/list` 发布。
- 文档结果不代表数据源当前可用，仍需通过描述和实际调用确认。

## 4. 验证与回退

- 大表优先使用 `output_mode=summary` 或 `compact`，再用 `page` 和 `page_size` 翻页。
- `akbridge_call` 默认不返回 metrics；需要时传 `include_metrics=true`，或读取 `akbridge://metrics`。
- `side_effect=true` 可能修改全局配置或提交凭据，调用前必须获得用户明确授权。
- 仅在授权后对副作用接口传 `allow_side_effect=true`；该标志本身不代表用户授权。
- 工具错误的 `content[0].text` 是含稳定 `error.code`、建议和恢复提示的 JSON；
  按错误码恢复，不要盲目重试。

## 5. MCP Prompts

- `akbridge.query_financial_data` 引导完整的 search → describe → call 流程。
- `akbridge.describe_api` 查询单个接口的 schema 和说明。
- `akbridge.search_catalog` 检索接口目录。
- 客户端展示 prompt 的名称和触发方式各异；优先使用客户端的 MCP Prompts 界面。

以上流程是确定性的本地路由规则，不调用 LLM、嵌入服务或远程向量数据库。
"""
