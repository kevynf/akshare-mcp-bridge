# AKBridge 自动化验收与维护

[English](automated-validation-and-maintenance.en.md)

本文定义 AKBridge 的自动维护边界。所有默认命令都是确定性程序：不调用 LLM、不等待人工输入，
也不把外部数据源的短暂不可用误判为 MCP 适配回归。

## 分层检查

| 层级 | 命令 | 访问数据源 | 失败含义 |
| --- | --- | ---: | --- |
| 本地契约 | `akbridge-maintain ci --strict` | 否 | 发现、Schema、目录或路由契约回归 |
| 离线逐接口 | `akbridge-accept run --offline` | 否 | 单个接口的本地适配契约未通过 |
| 数据源探测 | `akbridge-maintain ci --strict --provider` | 是 | 上游网络、反爬、凭据、数据格式或 AKShare 运行时变化 |

前两层是提交和定时 CI 的稳定门禁。第三层在独立计划任务中运行，只把 MCP/Schema 回归和隔离进程
故障作为严格失败条件，其验收资产由机器人提交，但不改写契约基线。

## 升级流程

1. 在隔离分支升级 `akshare` 或 `mcp` 及锁文件。
2. 运行严格离线门禁与全量离线验收，生成 manifest、语义目录和报告。
3. 检查 `artifacts/maintenance/latest.json`：新增接口是信息项；删除、签名或 Schema 变化是回归项，严格模式返回非零退出码。
4. 需要评估上游可用性时再运行 `--provider`，按 `ledger.csv` 的错误范围归类问题。
5. 门禁通过后，AKShare 的同主版本升级与 mcp 的同主版本 patch 升级可自动合并；跨主版本、mcp 的 minor 升级与异常变更必须人工审核。
6. 门禁通过、且重新生成的基线工件与已提交内容不一致时，CI 自动重新生成并提交 `artifacts/acceptance/manifest.json` 与 `artifacts/catalog.json`；删除、签名或 Schema 变化会先于刷新失败，保持人工把关。

## 命令

生成可审计基线：

```powershell
.venv\Scripts\python.exe -m akbridge.maintenance manifest `
  --output artifacts\acceptance\manifest.json
.venv\Scripts\python.exe -m akbridge.maintenance catalog `
  --output artifacts\catalog.json
```

严格离线检查（定时任务附加 `--check-latest` 查询 PyPI 最新 AKShare 版本；网络不可用记为
`unavailable`，不误报回归，需要门禁失败时再加 `--fail-on-update`）：

```powershell
.venv\Scripts\python.exe -m akbridge.maintenance ci --strict `
  --baseline artifacts\acceptance\manifest.json `
  --current artifacts\maintenance\manifest.json `
  --catalog artifacts\catalog.json `
  --report artifacts\maintenance\latest.json
```

离线逐接口验收与报告，以及基线差异比较：

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance run --offline --workers 4 `
  --output artifacts\acceptance\runs\offline.json
.venv\Scripts\python.exe -m akbridge.acceptance report `
  --run artifacts\acceptance\runs\offline.json
.venv\Scripts\python.exe -m akbridge.maintenance diff --strict `
  --baseline artifacts\acceptance\manifest.json `
  --current artifacts\maintenance\manifest.json
```

报告写入 `SUMMARY.md` 与 `SUMMARY.en.md`、机器可读的 `summary.json`、状态图和逐接口
`ledger.csv`；其中的文档部分记录文档块数量、必填字段完整率、公开接口关联覆盖率和未关联接口。

`akbridge-accept run` 的常用参数：`--limit` 控制本次验收数量，`--resume` 继续上次进度，
`--retry-status timeout` 复验超时接口，`--name` 只验收指定接口（可重复），`--timeout` 与
`--workers` 控制单接口超时与并发；`akbridge-accept manifest` 可随时重新生成清单。示例：

```powershell
.venv\Scripts\python.exe -m akbridge.acceptance run --resume --limit 100 --timeout 30 --workers 4
.venv\Scripts\python.exe -m akbridge.acceptance run --name stock_zh_a_hist --name macro_china_cpi --timeout 30
.venv\Scripts\python.exe -m akbridge.acceptance manifest
```

## 退出码与报告

`akbridge-maintain ci --strict` 在以下情况返回非零退出码：

- 接口数低于最小阈值，或接口被删除且超过 `--max-removed`；
- 既有接口的 Python 签名或输入 Schema 哈希变化；
- 目录、输入 Schema、MCP 工具（`all`/`router` 契约）或路由索引验证失败。

报告包含稳定的 `current_fingerprint`：相同 AKShare 版本与本地代码生成相同指纹，生成时间不参与
计算；`metadata_hash` 变化只记录，不判定回归。指纹只对解释器稳定——门禁与基线必须在仓库规范
解释器 Python 3.14 下生成和比较，因为不同解释器对同一签名的 PEP 604 联合类型渲染不同
（`str | None` 与 `Optional[str]`），会产生假回归；定时门禁作业通过 `UV_PYTHON: "3.14"`
固定该不变量。

## 数据源探测

第三方数据源具有验证码、限流、登录、地理网络和临时故障等特性。AKBridge 将这些问题分离到
`provider_success`、`upstream_transport`、`upstream_response`、`upstream_timeout` 和
`akshare_runtime` 范围，不写成 MCP Schema 失败。探测可自动重试，但不得篡改接口参数、伪造空
数据或覆盖契约基线。凭据经环境变量提供，报告与结构化日志对 token、密码、Cookie 和 API Key
脱敏。

## GitHub Actions

定时任务在 GitHub 托管运行器上执行，不在本机创建定时任务或常驻进程；时间按北京时间（UTC+8）
列出，Dependabot 直接使用 `Asia/Shanghai`。

| 任务 | 触发方式 | 北京时间 | 仓库行为 |
| --- | --- | --- | --- |
| 离线测试、逐接口验收、严格门禁、文档索引与构建 | 推送或 PR；每周一 | 推送或 PR 时；每周一 12:00 | 上传报告；基线工件与重新生成内容不一致时由机器人提交刷新 |
| 依赖检查（akshare、mcp） | Dependabot 每天 | 每天 12:00 | 更新 `pyproject.toml` 与 `uv.lock` 并开 PR，并发上限 3 |
| 受控自动合并 | 对应 PR 的维护流水线成功后 | 无固定时间 | AKShare 同主版本升级、mcp 同主版本 patch 升级由机器人 squash 合并；其余保留并记录原因 |
| 真实数据源全量验收 | 每月 1 日和 15 日 | 12:00 | 提交状态图、验收汇总与逐接口明细 |
| 依赖变更自动发版 | 推送或每周定时维护成功后 | 无固定时间 | 自动 bump patch 版本，同一作业内打 tag 并创建 Release，随后发布 |

需要知道的四条约束：

- **`GITHUB_TOKEN` 推送不触发新工作流。** 刷新基线与创建 Release 都在发起作业内完成，不依赖
  事件链；自动合并的依赖升级自身也不启动维护流水线，由下一次推送或每周定时任务兜底。
- **自动发版按依赖漂移触发。** 比较 HEAD 与上一发布 tag 的依赖固定版本，仅在变化时 bump；发布
  步骤校验分支头与目标提交的血缘关系，并发组加远端版本检查保证重复触发只产生一个发版提交。
  需要在无依赖变化时发版，手动 bump 版本后推送到默认分支即可。
- **发布失败可重试。** `publish-pypi.yml` 保留 `workflow_dispatch` 入口（输入 `release_tag`），
  因为机器人创建的 Release 不会触发 `release` 事件，`workflow_call` 失败后只能靠它手动重跑。
- **自动合并的判定。** 作者必须是 `dependabot[bot]`，只修改 `pyproject.toml` 与 `uv.lock`，
  恰好一个固定版本依赖变化，且 `pyproject.toml` 除该版本串外无其他改动。mcp 是 MCP 协议库，
  minor 升级可能改变协议行为，因此保留人工确认。

仓库需要在 `Settings → Actions → General → Workflow permissions` 中启用
`Read and write permissions`。建议为默认分支要求
`AKBridge automated validation and maintenance / offline-contract` 状态检查；如分支规则还要求
人工批准，自动合并不会绕过规则，PR 将保持打开并在 Actions 中记录失败原因。

`allow` 列表除 akshare 与 mcp 外还包含 pyjwt 与 urllib3：二者是带未修复告警的传递依赖，不放行则 Dependabot 永远不会为它们开 PR。只修改 `uv.lock` 的 PR（传递依赖或安全更新）会被自动合并流程保留并记录原因，不判失败；判定失败仍限于越界文件、pyproject 杂项改动和降级。
