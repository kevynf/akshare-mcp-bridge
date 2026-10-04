# AKBridge Automated Validation and Maintenance

[简体中文](automated-validation-and-maintenance.zh-CN.md)

This document defines AKBridge's automated maintenance boundaries. Default commands are
deterministic: they do not call an LLM, wait for human input, or treat temporary provider outages as
MCP adapter regressions.

## Validation layers

| Layer | Command | Provider access | Failure meaning |
| --- | --- | ---: | --- |
| Local contract | `akbridge-maintain ci --strict` | No | Discovery, schema, catalog, or routing regression. |
| Offline per-interface | `akbridge-accept run --offline` | No | A local adapter contract failed. |
| Provider probe | `akbridge-maintain ci --strict --provider` | Yes | Upstream network, anti-scraping, credentials, data format, or runtime change. |

The first two layers are the stable commit and scheduled CI gates. The third runs in a separate
scheduled workflow, fails strictly only on MCP/Schema regressions and isolated worker failures, and
commits its acceptance assets without rewriting the contract baseline.

## Upgrade workflow

1. Upgrade `akshare` or `mcp` and the lock file on an isolated branch.
2. Run the strict offline gate and the full offline acceptance to generate the manifest, semantic catalog, and report.
3. Inspect `artifacts/maintenance/latest.json`: added interfaces are informational; removed interfaces, signature changes, and schema changes are regressions and exit nonzero in strict mode.
4. Run `--provider` only when upstream availability needs assessment, and classify failures by the ledger scope.
5. Same-major AKShare upgrades and same-minor MCP patch upgrades may merge automatically once the gate passes; major bumps, MCP minor bumps, and unusual changes require human review.
6. When the gate passes and the regenerated baseline artifacts differ from the committed ones, CI regenerates and commits `artifacts/acceptance/manifest.json` and `artifacts/catalog.json`; removals, signature changes, and schema changes fail the gate before any refresh and stay manual.

## Commands

Generate an auditable baseline:

```powershell
.venv\Scripts\python.exe -m akbridge.maintenance manifest `
  --output artifacts\acceptance\manifest.json
.venv\Scripts\python.exe -m akbridge.maintenance catalog `
  --output artifacts\catalog.json
```

Strict offline check (append `--check-latest` in scheduled jobs to query the latest AKShare release
on PyPI; network unavailability is reported as `unavailable` rather than a regression, and
`--fail-on-update` makes a newly available release fail the gate):

```powershell
.venv\Scripts\python.exe -m akbridge.maintenance ci --strict `
  --baseline artifacts\acceptance\manifest.json `
  --current artifacts\maintenance\manifest.json `
  --catalog artifacts\catalog.json `
  --report artifacts\maintenance\latest.json
```

Offline per-interface acceptance, report rendering, and baseline comparison:

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance run --offline --workers 4 `
  --output artifacts\acceptance\runs\offline.json
.venv\Scripts\python.exe -m akbridge.acceptance report `
  --run artifacts\acceptance\runs\offline.json
.venv\Scripts\python.exe -m akbridge.maintenance diff --strict `
  --baseline artifacts\acceptance\manifest.json `
  --current artifacts\maintenance\manifest.json
```

The report writes `SUMMARY.md` and `SUMMARY.en.md`, the machine-readable `summary.json`, the status
image, and the per-interface `ledger.csv`; its documentation section records document-chunk count,
required-field completeness, public-interface coverage, and unlinked interfaces.

Useful flags for `akbridge-accept run`: `--limit` bounds this run, `--resume` continues the previous
progress, `--retry-status timeout` re-runs timed-out interfaces, `--name` (repeatable) restricts the
run to named interfaces, and `--timeout`/`--workers` control the per-interface timeout and
concurrency; `akbridge-accept manifest` regenerates the manifest at any time:

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance run --resume --limit 100 --timeout 30 --workers 4
.venv\Scripts\python.exe -m akbridge.acceptance run --name stock_zh_a_hist --name macro_china_cpi --timeout 30
.venv\Scripts\python.exe -m akbridge.acceptance manifest
```

## Exit codes and reports

`akbridge-maintain ci --strict` exits nonzero when the discovered interface count falls below its
minimum, when interfaces are removed beyond `--max-removed`, when an existing signature or
input-schema hash changes, or when catalog, schema, MCP tool (`all`/`router` contract), or routing
validation fails.

Reports contain a stable `current_fingerprint`: the same AKShare version and local code produce the
same fingerprint, and generation time is excluded. Metadata-hash changes are recorded without
counting as regressions. The fingerprint is only stable per interpreter — the gate and the baseline
must be generated and compared under the repository's canonical interpreter, Python 3.14, because
interpreters render PEP 604 unions in the same signature differently (`str | None` versus
`Optional[str]`) and produce false regressions. Scheduled gate jobs pin this invariant through
`UV_PYTHON: "3.14"`.

## Provider probes

Third-party data sources have CAPTCHAs, rate limits, logins, geography restrictions, and transient
failures. AKBridge separates these into the `provider_success`, `upstream_transport`,
`upstream_response`, `upstream_timeout`, and `akshare_runtime` scopes instead of reporting them as
MCP schema failures. Probes may retry automatically, but must never tamper with interface arguments,
fabricate empty data, or overwrite the contract baseline. Credentials come from environment
variables, and reports and structured logs redact tokens, passwords, cookies, and API keys.

## GitHub Actions

Scheduled tasks run on GitHub-hosted runners and never create local scheduled jobs or resident
processes. Times below are Beijing time (UTC+8); Dependabot uses `Asia/Shanghai` directly.

| Task | Trigger | Beijing time | Repository effect |
| --- | --- | --- | --- |
| Offline tests, per-interface acceptance, strict gate, documentation index, build | Push or PR; every Monday | On push/PR; Mondays 12:00 | Uploads reports; commits a baseline refresh when the regenerated artifacts differ from the committed ones |
| Dependency checks (akshare, mcp) | Dependabot daily | Daily 12:00 | Updates `pyproject.toml` and `uv.lock` and opens PRs, at most 3 open |
| Controlled auto-merge | After the PR's maintenance run succeeds | No fixed time | Squash-merges same-major AKShare upgrades and same-minor MCP patch upgrades; keeps everything else open with a reason |
| Full provider acceptance | 1st and 15th monthly | 12:00 | Commits the status image, acceptance summaries, and per-interface ledger |
| Dependency-driven release | After a push or the weekly maintenance run succeeds | No fixed time | Bumps the patch version, then tags and creates the Release in the same job before publishing |

Four constraints worth knowing:

- **`GITHUB_TOKEN` pushes do not trigger workflows.** The baseline refresh and the Release are
  therefore finished inside the job that starts them, not through an event chain; an auto-merged
  dependency upgrade also does not start the maintenance pipeline, which the next push or the weekly
  schedule covers.
- **Releases follow dependency drift.** HEAD's pins are compared with the last release tag and the
  version is bumped only when they differ; the release step checks the ancestry of its target commit,
  and a concurrency group plus a remote-version check keeps repeated triggers to one release commit.
  To release without a dependency change, bump the version manually and push to the default branch.
- **Failed publishes are retried through `workflow_dispatch`** (input `release_tag`) on
  `publish-pypi.yml`, because a Release created with `GITHUB_TOKEN` emits no `release` event, so a
  failed `workflow_call` has no other retry path.
- **Auto-merge requires** the author to be `dependabot[bot]`, only `pyproject.toml` and `uv.lock` to
  change, exactly one exact-pin dependency to move, and no other `pyproject.toml` edit. MCP is the
  protocol library, so minor upgrades may change protocol behavior and stay manual.

Enable read and write workflow permissions and require the maintenance `offline-contract` check on
the default branch. Branch rules that also demand human approval are not bypassed: the PR stays open
and Actions records the reason.

The `allow` list also contains pyjwt and urllib3: they are transitive dependencies with open alerts, and without those entries Dependabot would never open pull requests for them. Pull requests that touch only `uv.lock` (transitive or security updates) are kept open with a recorded reason instead of failing the check; failures remain limited to out-of-scope files, unrelated `pyproject.toml` edits, and downgrades.
