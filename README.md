<div align="center">
  <!-- mcp-name: io.github.kevynf/akbridge -->
  <h1>AKBridge</h1>
  <p><strong>将 AKShare 公共接口自动接入 MCP。</strong></p>
  <p>
    <a href="https://github.com/kevynf/akshare-mcp-bridge/blob/master/README.md">简体中文</a> |
    <a href="https://github.com/kevynf/akshare-mcp-bridge/blob/master/README.en.md">English</a>
  </p>
  <p>
    <a href="https://github.com/kevynf/akshare-mcp-bridge/actions/workflows/akbridge-maintenance.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/kevynf/akbridge/akbridge-maintenance.yml?branch=master&amp;label=CI"></a>
    <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
    <a href="https://pypi.org/project/akbridge/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/akbridge?label=PyPI"></a>
    <a href="https://pypi.org/project/akbridge/"><img alt="AKShare dependency" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fpypi.org%2Fpypi%2Fakbridge%2Fjson&amp;query=%24.info.requires_dist%5B0%5D&amp;label=AKShare"></a>
    <a href="https://modelcontextprotocol.io/"><img alt="MCP stdio 与 SSE" src="https://img.shields.io/badge/MCP-stdio%20%7C%20SSE-6f42c1"></a>
    <a href="LICENSE"><img alt="MIT 许可证" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
  </p>
</div>

<p align="center">
  <a href="#安装">安装</a> |
  <a href="#客户端配置">客户端配置</a> |
  <a href="#调用示例">调用示例</a>
</p>

将 AKShare 公共接口自动暴露为 MCP 工具，并提供路由检索、结构化输出、逐接口验收以及自动化验收与维护。当前 AKShare 基线版本、接口数量和验收结果见[中文验收汇总](artifacts/acceptance/SUMMARY.md)与[English acceptance summary](artifacts/acceptance/SUMMARY.en.md)。

## 为什么选择 AKBridge

AKShare 覆盖广泛的金融数据接口，但直接接入 AI 助手仍需处理 Python 调用、函数选择、参数构造、DataFrame 转换和版本变化。AKBridge 把这些工作收敛为一个可安装、可检索、可验收的 MCP 服务，适合构建金融研究助手、行情分析 Agent 或数据检索工具：

- 覆盖 AKShare 完整公共接口，而不是长期手工维护少量工具；
- 只向 LLM 暴露三个稳定的路由工具，降低上千个接口带来的上下文压力；
- 提供统一的 JSON 输出、分页、摘要和错误分类，而不是直接处理不同形态的 Python 返回值；
- 在 AKShare 更新后自动发现接口变化，并通过逐接口验收判断是否仍可安全使用。

AKBridge 不替代 AKShare：AKShare 负责数据获取，AKBridge 负责把这些能力可靠地交给 MCP 客户端、Agent 或其他工具。第三方数据源自身的登录、验证码、反爬、限流和网络限制仍然存在，并会被单独报告。

## 验收状态

![AKBridge 最新验收状态](https://raw.githubusercontent.com/kevynf/akshare-mcp-bridge/master/artifacts/acceptance/status.svg)

状态图由验收报告命令自动生成，详细结果见[中文验收汇总](artifacts/acceptance/SUMMARY.md)、[English acceptance summary](artifacts/acceptance/SUMMARY.en.md)和[逐接口明细](artifacts/acceptance/ledger.csv)。

GitHub Actions 与 Dependabot 自动检查 AKShare 与 mcp 更新：AKShare 的同主版本升级与 mcp 的同主版本 patch 升级在完整验收通过后自动合并，依赖固定版本变化还会自动发布新版本。频率、门禁与仓库配置见[自动化验收与维护说明](docs/automated-validation-and-maintenance.zh-CN.md)。

## 功能

- 自动发现 AKShare 公共可调用接口，按函数签名生成 MCP 输入 Schema，无需手工维护上千个适配器。
- 支持 `DataFrame`、`Series`、日期和常见 NumPy 标量的 JSON 转换，以及 DataFrame JSON 入参与时间索引转换。
- 提供逐接口隔离验收、超时控制、并发执行、验收参数集和断点续跑。
- 生成逐接口 CSV 明细以及 JSON、Markdown 汇总报告。
- 提供本地语义目录、确定性检索和三工具路由模式。
- 支持 `raw`、`compact`、`summary` 三种输出模式、分页、字段类型和单位提示。
- 提供重试、限速、缓存、熔断、代理配置、敏感信息脱敏以及自动化验收与维护门禁。

## 安装

推荐使用 [`uv`](https://docs.astral.sh/uv/getting-started/installation/) 安装命令行工具，它会为 AKBridge 管理隔离的 Python 3.11+ 环境。普通用户从 PyPI 安装最新发布版：

```powershell
uv tool install akbridge
uv tool update-shell
```

重新打开终端后验证：

```powershell
akbridge --help
akbridge --mode router
```

第二条命令启动 stdio MCP 服务并等待客户端连接，终端看起来没有输出是正常现象，可按 `Ctrl+C` 停止。安装默认分支的开发版本用 `uv tool install --force "git+https://github.com/kevynf/akbridge.git"`；升级和卸载分别是 `uv tool upgrade akbridge` 与 `uv tool uninstall akbridge`。

参与开发或需要修改代码时才克隆仓库：

```powershell
git clone https://github.com/kevynf/akbridge.git
cd akbridge
uv sync --group dev
uv run --no-sync akbridge --mode router
```

stdio 服务启动后不会显示网页、菜单或命令提示符，MCP 客户端通过标准输入输出与该进程通信。

## 两种工具模式

`all` 是默认模式，保留所有已发现的 AKShare 原始函数工具，适合兼容已有客户端、逐接口验收和人工精确调用。实际连接 LLM 时建议使用 `router` 模式，它只公布三个稳定工具：

| 工具 | 用途 |
| --- | --- |
| `akbridge_search` | 在本地语义目录中检索接口、别名、类别和用途，返回小型 RAG 上下文。 |
| `akbridge_describe` | 返回一个接口的签名、参数、示例、返回类型、数据源链接和副作用标记。 |
| `akbridge_call` | 解析规范名称或唯一别名，调用接口，并选择输出模式和分页。 |

```powershell
akbridge --mode router
```

检索器从 AKShare 公开函数自动生成 `一级分类 → 源码模块 → 接口` 路由树，例如 `stock → stock_feature.stock_hist_em → stock_zh_a_hist`。函数名、签名、别名和 docstring 构成默认的确定性词法证据，不调用 LLM、嵌入服务或远程向量数据库。MCP 资源 `akbridge://skill` 提供同一套运行时调用规程，它随服务暴露，不会自动安装成客户端 Skill。

### AKShare 文档词法路由

正式发布的 wheel 和 sdist 会在 GitHub Actions 中，根据固定的 AKShare 版本解析对应的 `release-vX.Y.Z` 标签和 commit SHA，自动构建并包含文档索引；`router` 模式默认加载包内索引，服务搜索期间不会联网。文档块只关联 AKShare 顶层公开函数，补充自然语言术语和排序证据，不决定领域或模块结构；搜索结果会返回命中的文档标题和来源链接。

源码开发时可手动重建或覆盖索引：

```powershell
akbridge-docs build --ref <akshare-commit-sha> --output artifacts\akshare-docs.json
akbridge --mode router --document-index artifacts\akshare-docs.json
```

## 客户端配置

选择使用的 MCP 客户端，跳转到对应配置：[Cherry Studio](#cherry-studio)、[Codex](#codex-配置)或[其他客户端](#其他-mcp-客户端)。

### Cherry Studio

Cherry Studio 可以通过 stdio 直接启动 AKBridge，不需要额外的适配服务，推荐使用 `router` 模式。

**协议安装**：将下面的地址复制到浏览器地址栏或 Windows“运行”窗口，打开 Cherry Studio 后检查安装预览并确认。如果没有打开自定义协议，请改用下方的 JSON 导入。

```text
cherrystudio://mcp/install?servers=eyJtY3BTZXJ2ZXJzIjp7ImFrYnJpZGdlIjp7InR5cGUiOiJzdGRpbyIsImNvbW1hbmQiOiJ1dngiLCJhcmdzIjpbImFrYnJpZGdlIiwiLS1tb2RlIiwicm91dGVyIl19fX0%3D
```

Cherry Studio 会以未启用、未信任状态导入配置，仍需由用户确认并启用。

**从 JSON 导入**：打开 `设置 → MCP → MCP 服务器 → 添加 → 从 JSON 导入`，粘贴：

```json
{
  "mcpServers": {
    "akbridge": {
      "type": "stdio",
      "command": "uvx",
      "args": ["akbridge", "--mode", "router"]
    }
  }
}
```

启用服务并确认状态正常后，将 AKBridge 绑定到需要使用它的 Agent。首次启动时 `uvx` 可能需要下载并创建运行环境，会比后续启动更慢。

### Codex 配置

在 Codex MCP 配置中加入：

```toml
[mcp_servers.akbridge]
command = "akbridge"
args = ["--mode", "router"]
startup_timeout_sec = 30
tool_timeout_sec = 120
```

保存配置并重启 Codex，客户端初始化成功后即可看到 AKShare 工具。

### 其他 MCP 客户端

支持 JSON MCP 配置的客户端（Claude Desktop 及兼容客户端）可以使用：

```json
{
  "mcpServers": {
    "akbridge": {
      "command": "akbridge",
      "args": ["--mode", "router"]
    }
  }
}
```

## 调用示例

连接 MCP 服务后，用户可以直接描述数据需求，无需预先知道 AKShare 函数名：

```text
查询股票代码 000001 从 2026-01-01 到 2026-08-06 的前复权日线行情。
```

类似的自然语言请求还有“获取 A 股实时行情”“查询中国 CPI 数据”“获取开放式基金净值”“查询国内期货实时行情”。MCP 客户端中的 LLM 负责把需求转换为下方的检索、描述和结构化调用；AKBridge 本身不使用 LLM，每个工具的参数来自对应 AKShare 函数签名，具体含义以工具描述和 AKShare 文档为准。

## 路由调用与结果格式

典型顺序是先检索、再描述、最后调用：

```json
{"query": "A股历史行情", "limit": 5}
{"name": "stock_zh_a_hist"}
```

```json
{
  "name": "stock_zh_a_hist",
  "arguments": {
    "symbol": "000001",
    "period": "daily",
    "start_date": "20260101",
    "end_date": "20260806",
    "adjust": "qfq"
  },
  "output_mode": "compact",
  "page": 1,
  "page_size": 100
}
```

| 输出模式 | 适用场景 | 返回内容 |
| --- | --- | --- |
| `raw` | 兼容已有直接工具调用 | 原始 JSON 结构，默认最多 5,000 行。 |
| `compact` | 常规分析 | 行数据、分页信息、字段类型和按列名推断的单位提示。 |
| `summary` | 先判断数据是否适用 | 行数、列、空值统计、数值摘要和少量预览，不返回完整大表。 |

字段和单位提示由结果列名和 dtype 自动推断，属于辅助元数据，不替代 AKShare 或数据源的正式定义。

## DataFrame 入参

少数计算接口需要 `pandas.DataFrame`，MCP 客户端可以传入记录数组：

```json
{
  "data": {
    "index_column": "date",
    "rows": [
      {"date": "2026-01-05T09:30:00", "Open": 10.0, "High": 10.3, "Low": 9.9, "Close": 10.2}
    ]
  }
}
```

`index_column` 指定转换为 DataFrame 索引的列，ISO 日期字符串会自动转换为 `DatetimeIndex`。

## 逐接口验收

接口清单由发现机制自动生成，记录 AKShare 版本、接口总数、函数签名、输入 Schema 哈希以及自动生成的显示名、类别、别名、用途、示例、返回元数据、副作用标记和数据源链接，落在 `artifacts/acceptance/manifest.json`；`artifacts/catalog.json` 是同一目录的紧凑 RAG 导出。常用命令：

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance manifest
.venv\Scripts\python.exe -m akbridge.acceptance run --limit 20 --timeout 30 --workers 4
.venv\Scripts\python.exe -m akbridge.acceptance run --resume --retry-status timeout --timeout 60
```

`--limit` 控制本次验收数量，`--resume` 继续上次进度，`--retry-status timeout` 复验超时接口，`--name` 只验收指定接口；必填验收参数位于 `artifacts/acceptance/fixtures.json`。完整参数与断点续跑细节见[自动化验收与维护说明](docs/automated-validation-and-maintenance.zh-CN.md)。

### 验收状态取值

| 状态 | 含义 |
| --- | --- |
| `passed` | 接口成功返回非空结果 |
| `passed_empty` | 接口成功执行，但当前返回空结果或无返回值 |
| `failed` | AKShare 或上游数据源返回运行错误 |
| `timeout` | 接口在指定时间内没有完成 |
| `fixture_required` | 缺少必填验收参数 |
| `worker_failed` | MCP 适配或隔离执行进程发生错误 |
| `adapter_passed` | 仅验证发现、Schema 和适配契约；没有访问第三方数据源 |

MCP 适配验收与数据源可用性分开统计：只要接口已被发现、生成 Schema，并成功进入 AKShare 调用路径且没有 `fixture_required` 或 `worker_failed`，就视为 MCP 适配通过。上游失败不会被隐藏或伪装成成功。

### 生成报告

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance report
```

报告写入 `artifacts/acceptance/` 下的 `SUMMARY.md`/`SUMMARY.en.md`（双语汇总）、`summary.json`（机器可读）、`status.svg`（README 状态图）、`ledger.csv`（逐项结果）和 `manifest.json`（完整清单）。当前基线的精确版本、接口数量和各状态统计见[验收汇总](artifacts/acceptance/SUMMARY.md)，失败范围分为上游网络、上游响应、AKShare 运行错误和上游超时，详细原因见逐接口明细。报告由验收命令生成，升级 AKShare 时无需手工同步 README 中的数字。

## 自动化验收与维护

默认离线门禁不访问第三方数据源，也不需要人或 LLM：

```powershell
.venv\Scripts\python.exe -m akbridge.maintenance ci --strict `
  --baseline artifacts\acceptance\manifest.json `
  --current artifacts\maintenance\manifest.json `
  --catalog artifacts\catalog.json `
  --report artifacts\maintenance\latest.json
```

它会重新发现全部接口、构造并验证全部 `all` 工具和固定的 3 个 `router` 工具、验证输入 Schema 和 router 索引、生成语义目录、比较接口新增/删除/签名/Schema 差异，并在接口删除或签名/Schema 回归时返回非零退出码。定时任务可加 `--check-latest` 查询 PyPI 最新 AKShare 版本，网络不可用只记录为 `unavailable`，需要让发现新版本时任务失败再加 `--fail-on-update`。

只验证适配契约而不访问数据源：

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance run --offline --workers 4
```

全量数据源验收反映上游网站、验证码、登录和限流状态，而不是 MCP 适配是否正确，应单独作为网络探测任务：

```powershell
.venv\Scripts\python.exe -m akbridge.maintenance ci --provider --timeout 60 --workers 4
```

[自动化维护工作流](.github/workflows/akbridge-maintenance.yml)每周运行离线流程并上传报告，[数据源探测工作流](.github/workflows/akbridge-provider-probe.yml)每月 1 日和 15 日各执行一次全量隔离验收。完整规则见[自动化验收与维护说明](docs/automated-validation-and-maintenance.zh-CN.md)。

## 可靠性与安全

只读接口可通过环境变量启用进程内缓存、限速、重试和熔断：

```powershell
$env:AKBRIDGE_CACHE_TTL = "60"
$env:AKBRIDGE_RATE_LIMIT_SECONDS = "0.2"
$env:AKBRIDGE_MAX_ATTEMPTS = "2"
$env:AKBRIDGE_CIRCUIT_FAILURE_THRESHOLD = "5"
$env:AKBRIDGE_CALL_TIMEOUT = "120"
```

代理支持标准 `HTTP_PROXY`/`HTTPS_PROXY`，也支持 `AKBRIDGE_HTTP_PROXY`、`AKBRIDGE_HTTPS_PROXY`、`AKBRIDGE_ALL_PROXY`、`AKBRIDGE_NO_PROXY` 专用别名。令牌、密码、Cookie、API Key 在验收日志和结构化诊断中会被脱敏；`set_*`、登录和配置类接口被标记为非只读，不缓存也不自动重试。备用数据源不按名称自动猜测，只能通过 `CallExecutor.register_fallback()` 为已确认语义等价的接口显式注册。

运行中的进程通过 MCP 资源 `akbridge://metrics` 提供调用次数、失败数、重试数、缓存命中和耗时计数；`AKBRIDGE_JSON_LOGS=1` 可将重试诊断以 JSON Lines 写入 stderr，不污染 stdio MCP 协议。

需要通过网络部署时可选 SSE 传输，默认只绑定本机，对外暴露前应由反向代理配置 TLS、认证和访问控制：

```powershell
.venv\Scripts\python.exe -m akbridge.server --transport sse --mode router --host 127.0.0.1 --port 8000
```

## 测试

```powershell
.venv\Scripts\python.exe -m pytest -q
```

覆盖函数发现、Schema 生成、语义检索、DataFrame 转换、三种结果模式、重试/缓存/熔断/脱敏、manifest 门禁、离线验收，以及真实 MCP stdio 客户端握手和复杂工具调用。验收参数集完全位于本地，不需要人工步骤、LLM 或第三方网络请求。

## 常见问题

**服务启动后没有输出？** 这是 stdio MCP 服务的正常行为，请由 MCP 客户端启动和管理服务，不要期待浏览器页面。

**某个工具返回网络错误？** AKShare 依赖多个第三方数据网站。先增加工具超时并重试；如果持续失败，查看 `ledger.csv` 中的错误类型，判断是连接失败、上游格式变化还是 AKShare 解析错误。

**返回数据过大？** 服务默认最多序列化 5,000 行，并在结果中返回 `row_count` 和 `truncated`，可启动时调整：

```powershell
.venv\Scripts\python.exe -m akbridge.server --row-limit 1000
```

**升级 AKShare 后接口数量变化？** 重新运行 `manifest` 和全量验收。运行时发现机制会自动暴露新增的公共可调用接口，但仍应检查签名变化及数据源回归。

## 当前限制与后续方向

当前限制：

- 内置 Skill 是随 MCP 服务暴露的通用运行时调用规程，不会自动安装成客户端模块，尚无面向不同客户端和金融领域的可安装 Skills。
- RAG 只有接口目录和词法检索，缺少金融知识、术语映射、向量召回与重排。

后续方向：

- 提供面向主流 LLM 客户端和 Agent 框架的可安装、可组合金融 Skills。
- 为高频接口补充人工校准的工具说明、参数语义、调用示例和结果摘要。
- 建设带来源和版本的金融知识库与中英文术语适配层。
- 提供混合 RAG 检索和自动化验收，持续评估知识召回、接口选择与参数完整度。

## 文档与贡献

- [自动化验收与维护](docs/automated-validation-and-maintenance.zh-CN.md) / [Automated validation and maintenance](docs/automated-validation-and-maintenance.en.md)
- [安全策略](SECURITY.md) / [Security policy](SECURITY.en.md)

欢迎提交 Issue 和 Pull Request，提交前请先阅读[贡献指南](CONTRIBUTING.md)。

## 许可证

AKBridge 使用 [MIT License](LICENSE) 开源。
