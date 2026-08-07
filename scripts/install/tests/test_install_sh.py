"""install.sh contract (B01): static guarantees + POSIX execution proofs."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.install.tests.conftest import REPO_ROOT

INSTALL_SH = REPO_ROOT / "install.sh"


def _sh() -> str | None:
    return shutil.which("sh")


def test_install_sh_exists_and_delegates_with_bytecode_guards() -> None:
    body = INSTALL_SH.read_text(encoding="utf-8")
    assert body.startswith("#!/bin/sh")
    assert "PYTHONDONTWRITEBYTECODE=1" in body
    assert "python3 -B -m scripts.install" in body
    assert "__pycache__" in body and "*.pyc" in body and "*.pyo" in body
    # The scan must precede the EXECUTABLE delegation line (the header
    # comment also mentions the delegation — anchor on `exec`).
    delegation = body.index("exec python3 -B -m scripts.install")
    assert body.index("find scripts/install -name '__pycache__'") < delegation
    assert "set -eu" in body


def test_install_sh_checks_every_host_prerequisite() -> None:
    body = INSTALL_SH.read_text(encoding="utf-8")
    for needle in (
        "uname -s",
        "3, 10",
        "docker compose version",
        "2, 24, 4",
        "x86_64|aarch64",
        "10485760",
    ):
        assert needle in body, needle


@pytest.mark.skipif(
    _sh() is None or sys.platform == "win32",
    reason="Linux sh required (the OS gate precedes the bytecode scan)",
)
def test_bytecode_scan_refuses_stale_pyc(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    (root / "scripts" / "install" / "__pycache__").mkdir(parents=True)
    (root / "scripts" / "install" / "__pycache__" / "x.pyc").write_bytes(b"")
    script = root / "install.sh"
    script.write_text(INSTALL_SH.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        [_sh(), "install.sh", "--check-only"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3
    assert "bytecode" in result.stderr.lower()
