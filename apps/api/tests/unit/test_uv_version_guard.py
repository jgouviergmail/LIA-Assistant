"""The pinned uv writer is checked portably, with exact argv and version matching."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_lia_check_uv_version", ROOT / "scripts/check_uv_version.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("stdout", "code", "expected"),
    [
        ("uv 0.13.4 (build metadata)\n", 0, True),
        ("uv 0.13.4\r\n", 0, True),
        ("uv 0.12.18\n", 0, False),
        ("uv 0.13.40\n", 0, False),
        ("uv 0.13.4rc1\n", 0, False),
        ("other 0.13.4\n", 0, False),
        ("uv 0.13.4\nextra output\n", 0, False),
        ("", 0, False),
        ("uv 0.13.4\n", 1, False),
    ],
)
def test_only_a_successful_exact_uv_version_is_accepted(
    monkeypatch: pytest.MonkeyPatch, stdout: str, code: int, expected: bool
) -> None:
    guard = _load()
    executable = str(Path("tools with spaces") / "uv.exe")

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert argv == [executable, "--version"]
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 10
        return subprocess.CompletedProcess(argv, code, stdout, "private stderr canary")

    monkeypatch.setattr(guard.subprocess, "run", run)
    assert guard.matches_uv_version(executable, "0.13.4") is expected


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError("missing"), PermissionError("denied"), subprocess.TimeoutExpired("uv", 10)],
)
def test_an_unavailable_uv_fails_closed(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    guard = _load()

    def run(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(guard.subprocess, "run", run)
    assert not guard.matches_uv_version("uv", "0.13.4")


def test_cli_refuses_a_wrong_version_without_relaying_child_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    guard = _load()
    monkeypatch.setattr(
        guard.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            ["uv", "--version"], 0, "uv 0.12.18\n", "private stderr canary"
        ),
    )
    assert guard.main(["--uv", "uv", "--expected", "0.13.4"]) == 1
    output = capsys.readouterr()
    assert "0.13.4" in output.err
    assert "private stderr canary" not in output.err + output.out


def test_the_bootstrap_guard_keeps_python_310_syntax() -> None:
    source = (ROOT / "scripts/check_uv_version.py").read_text(encoding="utf-8")
    ast.parse(source, feature_version=(3, 10))
