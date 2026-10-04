# 贡献指南

[English](CONTRIBUTING.en.md)

感谢参与 AKBridge。代码、文档和测试修改都应保持可复现，并且不能依赖人工或 LLM 才能验收。

## 开发环境

```powershell
uv sync --group dev
```

## 提交前检查

```powershell
uv run --no-sync python -m pytest -q
uv run --no-sync ruff check src tests
uv run --no-sync ruff format --check src tests
uv run --no-sync akbridge-accept run --offline --workers 4
uv run --no-sync akbridge-maintain ci --strict --check-latest
uv build
uv sync --extra release
uv run --no-sync twine check dist/*
```

离线验收不会请求第三方数据源，也不会调用 LLM。真实数据源探测由独立的定时工作流负责。

## 变更要求

- 保持 `--mode all` 的兼容性，并同步更新路由模式和语义目录。
- 新增或修改接口契约时，重新生成 `artifacts/acceptance/manifest.json` 和 `artifacts/catalog.json`。
- 不要提交凭据、Cookie、API Key、真实数据快照或本地环境目录。
- 文档正文可使用中文，但文件名使用英文主题名和语言后缀，例如 `automated-validation-and-maintenance.zh-CN.md`。

## 发布到 PyPI

发布工作流使用 PyPI Trusted Publishing，不在仓库中保存 API Token。首次发布前，在 PyPI
为项目 `akbridge` 配置 GitHub Publisher：仓库 **`kevynf/akshare-mcp-bridge`**（注意不是
PyPI 项目名 `akbridge`，也不是改名前的旧仓库名）、工作流 `publish-pypi.yml`、环境 `pypi`。
仓库改名后必须同步更新这里的值，否则 OIDC 声明与配置不匹配，发布会以
`invalid-publisher` 失败。

发布由版本号驱动，也支持依赖驱动。人工发布：同步更新 `pyproject.toml`、
`src/akbridge/__init__.py`，以及 `server.json` 中的顶层版本和包版本，合并到默认分支，
CI 成功后即可发版。依赖驱动：`auto-release.yml` 发现依赖固定版本相对上一发布 tag 发生变化时，
自动 bump patch 版本并推送，随后在**同一作业内**以该提交为 target 创建 GitHub Release（例如
`v0.1.3`），再复用 `publish-pypi.yml` 发布 PyPI 和 MCP Registry；无变化时空转，重复触发由并发组
与远端版本检查保证只产生一个发版提交。已有同版本 Release 时流程保持幂等；标签存在但 Release
缺失或指向其他提交时会失败，需要维护者检查。`workflow_call` 发布失败后，可用
`publish-pypi.yml` 的 `workflow_dispatch`（输入 `release_tag`）手动重试。人工发布 GitHub
Release 仍会直接触发同一发布流程。
