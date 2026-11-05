from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RESOLVER = REPO_ROOT / "scripts" / "resolve-akshare-ref.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the resolver script runs under bash"
)


def _fake_gh(directory: Path, log: Path, existing_tags: set[str]) -> None:
    """Write a fake ``gh`` that resolves only ``existing_tags`` to fixed SHAs."""
    cases = "".join(
        f'  "repos/akfamily/akshare/commits/{tag}") echo "{tag}-sha"; exit 0;;\n'
        for tag in sorted(existing_tags)
    )
    script = directory / "gh"
    script.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$2" >> "$FAKE_GH_LOG"\n'
        'case "$2" in\n'
        f"{cases}"
        '  *) echo "gh: No commit found for SHA: $2 (HTTP 422)" >&2; exit 1;;\n'
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _resolve(
    version: str | None, tmp_path: Path, existing_tags: set[str]
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required to run the resolver script")
    log = tmp_path / "gh-calls.log"
    _fake_gh(tmp_path, log, existing_tags)
    arguments = [bash, str(RESOLVER)] + ([version] if version else [])
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "FAKE_GH_LOG": str(log),
    }
    result = subprocess.run(
        arguments, capture_output=True, text=True, encoding="utf-8", env=environment
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, calls


def test_resolver_prefers_the_current_v_tag_convention(tmp_path: Path) -> None:
    result, calls = _resolve("1.20.25", tmp_path, {"v1.20.25", "release-v1.20.25"})

    assert result.returncode == 0
    assert result.stdout.strip() == "v1.20.25-sha"
    assert calls == ["repos/akfamily/akshare/commits/v1.20.25"]


def test_resolver_falls_back_to_the_legacy_release_v_tag(tmp_path: Path) -> None:
    result, calls = _resolve("1.19.3", tmp_path, {"release-v1.19.3"})

    assert result.returncode == 0
    assert result.stdout.strip() == "release-v1.19.3-sha"
    assert calls == [
        "repos/akfamily/akshare/commits/v1.19.3",
        "repos/akfamily/akshare/commits/release-v1.19.3",
    ]


def test_resolver_fails_clearly_when_no_tag_matches(tmp_path: Path) -> None:
    result, calls = _resolve("0.0.0", tmp_path, set())

    assert result.returncode == 1
    assert result.stdout == ""
    assert "v0.0.0" in result.stderr and "release-v0.0.0" in result.stderr
    assert calls == [
        "repos/akfamily/akshare/commits/v0.0.0",
        "repos/akfamily/akshare/commits/release-v0.0.0",
    ]


def test_resolver_requires_a_version_argument(tmp_path: Path) -> None:
    result, _ = _resolve(None, tmp_path, set())

    assert result.returncode == 2
    assert "usage" in result.stderr
