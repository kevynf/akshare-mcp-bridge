<div align="center">
  <!-- mcp-name: io.github.kevynf/akbridge -->
  <h1>AKBridge</h1>
  <p><strong>Automatically connect AKShare public interfaces to MCP.</strong></p>
  <p>
    <a href="https://github.com/kevynf/akshare-mcp-bridge/blob/master/README.md">简体中文</a> |
    <a href="https://github.com/kevynf/akshare-mcp-bridge/blob/master/README.en.md">English</a>
  </p>
  <p>
    <a href="https://github.com/kevynf/akshare-mcp-bridge/actions/workflows/akbridge-maintenance.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/kevynf/akshare-mcp-bridge/akbridge-maintenance.yml?branch=master&amp;label=CI"></a>
    <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white">
    <a href="https://pypi.org/project/akbridge/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/akbridge?label=PyPI"></a>
    <a href="https://pypi.org/project/akbridge/"><img alt="AKShare dependency" src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fpypi.org%2Fpypi%2Fakbridge%2Fjson&amp;query=%24.info.requires_dist%5B0%5D&amp;label=AKShare"></a>
    <a href="https://modelcontextprotocol.io/"><img alt="MCP stdio and SSE" src="https://img.shields.io/badge/MCP-stdio%20%7C%20SSE-6f42c1"></a>
    <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
  </p>
</div>

<p align="center">
  <a href="#installation">Installation</a> |
  <a href="#client-configuration">Client configuration</a> |
  <a href="#usage-example">Usage example</a>
</p>

Automatically exposes AKShare public interfaces as MCP tools, and provides routed retrieval,
structured output, per-interface acceptance, and automated validation and maintenance. The current
AKShare baseline version, interface count, and acceptance results are in the
[Chinese acceptance summary](artifacts/acceptance/SUMMARY.md) and the
[English acceptance summary](artifacts/acceptance/SUMMARY.en.md).

## Why choose AKBridge

AKShare covers a broad set of financial data interfaces, but connecting them directly to an AI
assistant still requires Python invocation, function selection, argument construction, DataFrame
conversion, and handling upstream changes. AKBridge consolidates that work into an installable,
searchable, and validated MCP service, suitable for building financial research assistants,
market-analysis agents, or data retrieval tools:

- Covers the complete set of AKShare public interfaces instead of a small, manually maintained tool
  set;
- Exposes only three stable router tools to the LLM, reducing the context pressure of thousands of
  interfaces;
- Provides unified JSON output, pagination, summaries, and error classification instead of handling
  different shapes of Python return values;
- Discovers interface changes automatically after AKShare updates and judges whether each interface
  is still safe to use through per-interface acceptance.

AKBridge does not replace AKShare: AKShare retrieves the data, and AKBridge delivers those
capabilities reliably to MCP clients, agents, and other tools. The login, CAPTCHA, anti-scraping,
rate-limit, and network restrictions of third-party data sources themselves still apply and are
reported separately.

## Acceptance status

![Latest AKBridge acceptance status](https://raw.githubusercontent.com/kevynf/akshare-mcp-bridge/master/artifacts/acceptance/status.svg)

The status image is generated automatically by the acceptance report command. For detailed results,
see the [Chinese acceptance summary](artifacts/acceptance/SUMMARY.md), the
[English acceptance summary](artifacts/acceptance/SUMMARY.en.md), and the
[per-interface ledger](artifacts/acceptance/ledger.csv).

GitHub Actions and Dependabot check AKShare and mcp updates automatically: same-major AKShare
upgrades and same-major mcp patch upgrades merge automatically after the full acceptance gate
passes, and a change in pinned dependency versions also publishes a new release automatically. For
schedules, gates, and repository configuration, see the
[automated validation and maintenance guide](docs/automated-validation-and-maintenance.en.md).

## Features

- Automatically discovers AKShare public callable interfaces and generates MCP input schemas from
  function signatures, with no need to manually maintain thousands of adapters.
- Supports JSON conversion of `DataFrame`, `Series`, dates, and common NumPy scalars, as well as
  DataFrame JSON input and time-index conversion.
- Provides per-interface isolated acceptance, timeout control, concurrent execution, acceptance
  parameter sets, and resumable runs.
- Generates per-interface CSV details and JSON and Markdown summary reports.
- Provides a local semantic catalog, deterministic retrieval, and a three-tool routing mode.
- Supports `raw`, `compact`, and `summary` output modes, pagination, and field type and unit hints.
- Provides retries, rate limiting, caching, circuit breaking, proxy configuration, sensitive
  information redaction, and automated validation and maintenance gates.

## Installation

Installing the command-line tool with [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
is recommended; it manages an isolated Python 3.11+ environment for AKBridge. Regular users install
the latest release from PyPI:

```powershell
uv tool install akbridge
uv tool update-shell
```

After reopening the terminal, verify:

```powershell
akbridge --help
akbridge --mode router
```

The second command starts the stdio MCP server and waits for a client connection; it is normal for
the terminal to show no output, and `Ctrl+C` stops it. Use
`uv tool install --force "git+https://github.com/kevynf/akshare-mcp-bridge.git"` to install the development
version from the default branch; upgrade and uninstall are `uv tool upgrade akbridge` and
`uv tool uninstall akbridge`.

Clone the repository only when contributing or modifying the code:

```powershell
git clone https://github.com/kevynf/akshare-mcp-bridge.git
cd akbridge
uv sync --group dev
uv run --no-sync akbridge --mode router
```

After the stdio service starts, no web page, menu, or command prompt is shown; the MCP client
communicates with the process through standard input and output.

## Two tool modes

`all` is the default mode; it keeps all discovered AKShare raw function tools, which suits existing
clients, per-interface acceptance, and precise manual calls. When connecting to an LLM, use `router`
mode, which publishes only three stable tools:

| Tool | Purpose |
| --- | --- |
| `akbridge_search` | Searches interfaces, aliases, categories, and purposes in the local semantic catalog and returns a small RAG context. |
| `akbridge_describe` | Returns an interface's signature, arguments, examples, return type, data source links, and side-effect flags. |
| `akbridge_call` | Resolves canonical names or unique aliases, calls the interface, and selects the output mode and pagination. |

```powershell
akbridge --mode router
```

The retriever automatically builds a `top-level category -> source module -> interface` routing tree
from AKShare public functions, for example `stock -> stock_feature.stock_hist_em ->
stock_zh_a_hist`. Function names, signatures, aliases, and docstrings form the default deterministic
lexical evidence; no LLM, embedding service, or remote vector database is called. The MCP resource
`akbridge://skill` provides the same runtime calling rules; it is exposed with the service and is
not automatically installed as a client Skill.

### AKShare documentation lexical routing

Published wheels and sdists automatically build and include a documentation index in GitHub Actions
by resolving the `release-vX.Y.Z` tag and commit SHA corresponding to the pinned AKShare version;
`router` mode loads the packaged index by default, and no network access occurs during service
searches. Documentation chunks relate only to AKShare top-level public functions, adding
natural-language terms and ranking evidence; they do not determine domain or module structure, and
search results return the matching document titles and source links.

The index can be rebuilt or overridden manually in source checkouts:

```powershell
akbridge-docs build --ref <akshare-commit-sha> --output artifacts\akshare-docs.json
akbridge --mode router --document-index artifacts\akshare-docs.json
```

## Client configuration

Choose the MCP client in use and jump to its configuration:
[Cherry Studio](#cherry-studio), [Codex](#codex-configuration), or
[other MCP clients](#other-mcp-clients).

### Cherry Studio

Cherry Studio can launch AKBridge directly over stdio, with no additional adapter service; router
mode is recommended.

**Protocol installation**: Copy the address below into the browser address bar or the Windows Run
window, check the installation preview after Cherry Studio opens, and confirm. If the custom
protocol does not open, use the JSON import below.

```text
cherrystudio://mcp/install?servers=eyJtY3BTZXJ2ZXJzIjp7ImFrYnJpZGdlIjp7InR5cGUiOiJzdGRpbyIsImNvbW1hbmQiOiJ1dngiLCJhcmdzIjpbImFrYnJpZGdlIiwiLS1tb2RlIiwicm91dGVyIl19fX0%3D
```

Cherry Studio imports the configuration in a disabled, untrusted state; the user still has to
confirm and enable it.

**Import from JSON**: Open `Settings -> MCP -> MCP Servers -> Add -> Import from JSON`, and paste:

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

After enabling the service and confirming it is healthy, bind AKBridge to the Agent that needs it.
On the first launch, `uvx` may need to download and create the runtime environment, which is slower
than later launches.

### Codex configuration

Add to the Codex MCP configuration:

```toml
[mcp_servers.akbridge]
command = "akbridge"
args = ["--mode", "router"]
startup_timeout_sec = 30
tool_timeout_sec = 120
```

Save the configuration and restart Codex; the AKShare tools are visible after successful client
initialization.

### Other MCP clients

Clients that support JSON MCP configuration (Claude Desktop and compatible clients) can use:

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

## Usage example

After connecting to the MCP service, users can describe their data needs directly, without knowing
AKShare function names in advance:

```text
Query the forward-adjusted daily quotes of stock code 000001 from 2026-01-01 to 2026-08-06.
```

Similar natural-language requests include "Get real-time A-share quotes", "Query China CPI data",
"Get open-end fund net values", and "Query domestic futures real-time quotes". The LLM in the MCP
client converts the request into the retrieval, description, and structured calls below; AKBridge
itself does not use an LLM, each tool's arguments come from the corresponding AKShare function
signature, and the exact meanings are defined by the tool descriptions and AKShare documentation.

## Routing and result format

The typical order is to search first, then describe, and finally call:

```json
{"query": "A-share historical quotes", "limit": 5}
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

| Output mode | When to use | Returned content |
| --- | --- | --- |
| `raw` | Compatible with existing direct tool calls | The original JSON structure, at most 5,000 rows by default. |
| `compact` | Regular analysis | Row data, pagination information, field types, and unit hints inferred from column names. |
| `summary` | Deciding first whether the data is applicable | Row count, columns, null statistics, numeric summary, and a small preview; the full large table is not returned. |

Field and unit hints are inferred automatically from the result column names and dtype; they are
auxiliary metadata and do not replace the official definitions of AKShare or the data source.

## DataFrame arguments

A few computation interfaces require a `pandas.DataFrame`; the MCP client can pass an array of
records:

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

`index_column` specifies the column converted to the DataFrame index; ISO date strings are converted
to `DatetimeIndex` automatically.

## Per-interface acceptance

The interface inventory is generated automatically by the discovery mechanism and records the
AKShare version, total interface count, function signatures, input schema hashes, and the
automatically generated display names, categories, aliases, purposes, examples, return metadata,
side-effect flags, and data source links in `artifacts/acceptance/manifest.json`; 
`artifacts/catalog.json` is the compact RAG export of the same directory. Common commands:

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance manifest
.venv\Scripts\python.exe -m akbridge.acceptance run --limit 20 --timeout 30 --workers 4
.venv\Scripts\python.exe -m akbridge.acceptance run --resume --retry-status timeout --timeout 60
```

`--limit` bounds this run, `--resume` continues the previous progress, `--retry-status timeout`
re-verifies the timed-out interfaces, and `--name` restricts the run to named interfaces. Required
acceptance arguments live in `artifacts/acceptance/fixtures.json`. The full flag set and resume
details are in the [automated validation and maintenance guide](docs/automated-validation-and-maintenance.en.md).

### Acceptance status values

| Status | Meaning |
| --- | --- |
| `passed` | The interface returned a non-empty result successfully |
| `passed_empty` | The interface executed successfully but currently returns an empty result or no return value |
| `failed` | AKShare or the upstream data source returned a runtime error |
| `timeout` | The interface did not complete within the specified time |
| `fixture_required` | A required acceptance argument is missing |
| `worker_failed` | An error occurred in MCP adaptation or the isolated execution process |
| `adapter_passed` | Only discovery, schema, and adapter contracts are verified; no third-party data source is accessed |

MCP adapter acceptance and data source availability are counted separately: an interface counts as
passing MCP adapter acceptance as long as it has been discovered, generated a schema, and
successfully entered the AKShare call path without `fixture_required` or `worker_failed`. Upstream
failures are not hidden or disguised as success.

### Generate reports

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance report
```

The report writes `SUMMARY.md`/`SUMMARY.en.md` (bilingual summaries), `summary.json`
(machine-readable), `status.svg` (the README status image), `ledger.csv` (per-interface results),
and `manifest.json` (the complete inventory), all under `artifacts/acceptance/`. The exact version
of the current baseline, the interface count, and the per-status statistics are in the
[acceptance summary](artifacts/acceptance/SUMMARY.md); the failure scope is divided into upstream
network, upstream response, AKShare runtime errors, and upstream timeout, with detailed reasons in
the per-interface ledger. The report is generated by the acceptance command, so the figures in this
README do not need manual updates when upgrading AKShare.

## Automated validation and maintenance

The default offline gate does not access third-party data sources and needs neither a human nor an
LLM:

```powershell
.venv\Scripts\python.exe -m akbridge.maintenance ci --strict `
  --baseline artifacts\acceptance\manifest.json `
  --current artifacts\maintenance\manifest.json `
  --catalog artifacts\catalog.json `
  --report artifacts\maintenance\latest.json
```

It rediscovers all interfaces, constructs and validates all `all` tools and the fixed 3 `router`
tools, verifies input schemas and the router index, generates the semantic catalog, compares
interface additions/removals/signature/schema differences, and returns a non-zero exit code when an
interface is removed or a signature/schema regression occurs. Scheduled jobs can add `--check-latest`
to query the latest AKShare version on PyPI; when the network is unavailable it is only recorded as
`unavailable`, and `--fail-on-update` is required to make the job fail when a new version is
discovered.

To verify adapter contracts only, without accessing data sources:

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance run --offline --workers 4
```

Full data-source acceptance reflects upstream website, CAPTCHA, login, and rate-limit status rather
than whether the MCP adaptation is correct, and should be run separately as a network probe task:

```powershell
.venv\Scripts\python.exe -m akbridge.maintenance ci --provider --timeout 60 --workers 4
```

The [automated maintenance workflow](.github/workflows/akbridge-maintenance.yml) runs the offline
process weekly and uploads the report, and the
[provider probe workflow](.github/workflows/akbridge-provider-probe.yml) performs a full isolated
acceptance on the 1st and 15th of each month. The full rules are in the
[automated validation and maintenance guide](docs/automated-validation-and-maintenance.en.md).

## Reliability and security

Read-only interfaces can enable in-process caching, rate limiting, retries, and circuit breaking
through environment variables:

```powershell
$env:AKBRIDGE_CACHE_TTL = "60"
$env:AKBRIDGE_RATE_LIMIT_SECONDS = "0.2"
$env:AKBRIDGE_MAX_ATTEMPTS = "2"
$env:AKBRIDGE_CIRCUIT_FAILURE_THRESHOLD = "5"
$env:AKBRIDGE_CALL_TIMEOUT = "120"
```

Proxy support covers the standard `HTTP_PROXY`/`HTTPS_PROXY`, as well as the dedicated aliases
`AKBRIDGE_HTTP_PROXY`, `AKBRIDGE_HTTPS_PROXY`, `AKBRIDGE_ALL_PROXY`, and `AKBRIDGE_NO_PROXY`.
Tokens, passwords, cookies, and API keys are redacted in acceptance logs and structured
diagnostics; `set_*`, login, and configuration interfaces are marked as non-read-only and are neither
cached nor retried automatically. Fallback data sources are not guessed by name; they can only be
registered explicitly through `CallExecutor.register_fallback()` for interfaces confirmed to be
semantically equivalent.

A running process exposes call counts, failures, retries, cache hits, and latency counts through the
MCP resource `akbridge://metrics`; `AKBRIDGE_JSON_LOGS=1` writes retry diagnostics to stderr as
JSON Lines, without polluting the stdio MCP protocol.

The optional SSE transport is available when network deployment is needed; it binds to the local
machine only by default, and a reverse proxy should provide TLS, authentication, and access control
before exposing it externally:

```powershell
.venv\Scripts\python.exe -m akbridge.server --transport sse --mode router --host 127.0.0.1 --port 8000
```

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Coverage includes function discovery, schema generation, semantic retrieval, DataFrame conversion,
the three result modes, retries/caching/circuit breaking/redaction, manifest gating, offline
acceptance, and a real MCP stdio client handshake and complex tool calls. The acceptance parameter
sets are entirely local; no manual step, LLM, or third-party network request is needed.

## FAQ

**No output after the service starts?** This is the normal behavior of a stdio MCP service; the
service should be started and managed by the MCP client, and no browser page should be expected.

**A tool returns a network error?** AKShare depends on multiple third-party data websites. First
increase the tool timeout and retry; if the failure persists, check the error type in `ledger.csv`
to determine whether it is a connection failure, an upstream format change, or an AKShare parsing
error.

**Returned data too large?** The server serializes at most 5,000 rows by default and returns
`row_count` and `truncated` in the result; adjust at startup:

```powershell
.venv\Scripts\python.exe -m akbridge.server --row-limit 1000
```

**Interface count changed after upgrading AKShare?** Re-run `manifest` and full acceptance. The
runtime discovery mechanism automatically exposes newly added public callable interfaces, but
signature changes and data-source regressions should still be checked.

## Current limitations and future directions

Current limitations:

- The bundled Skill is a general runtime calling procedure exposed with the MCP service; it is not
  automatically installed as a client module, and installable Skills for different clients and
  financial domains are not available yet.
- RAG only has an interface catalog and lexical retrieval, lacking financial knowledge, terminology
  mapping, vector recall, and reranking.

Future directions:

- Provide installable, composable financial Skills for major LLM clients and Agent frameworks.
- Add manually curated tool descriptions, parameter semantics, examples, and result summaries for
  frequently used interfaces.
- Build a source-backed and versioned financial knowledge base with a Chinese-English terminology
  adaptation layer.
- Provide hybrid RAG retrieval and automated acceptance to continuously assess knowledge recall,
  interface selection, and parameter completeness.

## Documentation and contributing

- [Automated validation and maintenance](docs/automated-validation-and-maintenance.en.md) /
  [automated validation and maintenance (Simplified Chinese)](docs/automated-validation-and-maintenance.zh-CN.md)
- [Security policy](SECURITY.en.md) / [security policy (Simplified Chinese)](SECURITY.md)

Issues and pull requests are welcome. Read the [contribution guide](CONTRIBUTING.en.md) before
submitting changes.

## License

AKBridge is open source under the [MIT License](LICENSE).
