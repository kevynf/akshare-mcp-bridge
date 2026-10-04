# Contributing Guide

[简体中文](CONTRIBUTING.md)

Thank you for contributing to AKBridge. Code, documentation, and test changes must remain reproducible and must not require human or LLM intervention for validation.

## Development Environment

```powershell
uv sync --group dev
```

## Pre-commit Checks

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

Offline acceptance does not contact third-party providers or call an LLM. A separate scheduled workflow performs real provider probes.

## Change Requirements

- Preserve `--mode all` compatibility and update router mode and the semantic catalog together.
- Regenerate `artifacts/acceptance/manifest.json` and `artifacts/catalog.json` when changing an interface contract.
- Do not commit credentials, cookies, API keys, real data snapshots, or local environment directories.
- Keep Chinese and English documentation in sync. Use English topic names and language suffixes for filenames, for example `automated-validation-and-maintenance.zh-CN.md`.

## Publishing to PyPI

The release workflow uses PyPI Trusted Publishing and stores no API token in the repository. Before the first release, configure the GitHub Publisher for project `akbridge` on PyPI with repository `kevynf/akbridge`, workflow `publish-pypi.yml`, and environment `pypi`.

Releases are version-driven and also dependency-driven. For a manual release, update `pyproject.toml`,
`src/akbridge/__init__.py`, and both version fields in `server.json`, then merge into the default
branch; the release follows a successful CI run. For a dependency-driven release, `auto-release.yml`
bumps the patch version automatically when the pinned dependencies differ from the last release tag,
then creates the matching GitHub Release (for example, `v0.1.3`) **in the same job**, targeting that
commit, and reuses `publish-pypi.yml` to publish to PyPI and the MCP Registry; it is a no-op when
nothing changed, and a concurrency group plus a remote-version check keeps repeated triggers to a
single release commit. Existing releases are idempotent; a tag without a release, or a tag pointing
elsewhere, fails for maintainer review. After a failed `workflow_call` publish, retry through the
`workflow_dispatch` entry point of `publish-pypi.yml` (input `release_tag`). Manually published
GitHub Releases still trigger the same publishing workflow.
