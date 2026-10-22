"""install.sh contract (B01): static guarantees + executable prerequisite checks."""

from __future__ import annotations

import os
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


@pytest.mark.parametrize(
    ("version", "ok"),
    [
        ("2.24.3", False),
        ("2.24.3-1", False),
        ("2.24.4", True),
        ("2.26.1-4", True),
        ("v2.26.1", True),
        ("2.40.3+ds1-0ubuntu1", True),
        ("2.30.1", True),
        ("2.9.9", False),
        ("", False),
        ("invalid", False),
        ("2.24.4-rc.1", False),
        ("2.40.3-rc.1", False),
        ("2.26.1~rc1", False),
        ("2.26.1junk", False),
        ("2.26.1.4", False),
        ("vv2.26.1", False),
    ],
)
def test_install_sh_compose_version_gate(version: str, ok: bool) -> None:
    # Run the actual bootstrap check even where the shell's Linux gate cannot run.
    body = INSTALL_SH.read_text(encoding="utf-8")
    check = body.split("<<'PYEOF'", 1)[1].split("\n", 1)[1].split("\nPYEOF", 1)[0]
    result = subprocess.run(
        [sys.executable, "-B", "-", version],
        input=check,
        capture_output=True,
        text=True,
    )
    assert result.returncode == (0 if ok else 1), result.stderr


def _stand_in(bin_dir: Path, name: str, body: str) -> None:
    command = bin_dir / name
    command.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    command.chmod(0o755)


@pytest.mark.skipif(
    _sh() is None or sys.platform != "linux",
    reason="Linux sh required (the OS gate precedes the bytecode scan)",
)
def test_bytecode_scan_refuses_stale_pyc(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    (root / "scripts" / "install" / "__pycache__").mkdir(parents=True)
    (root / "scripts" / "install" / "__pycache__" / "x.pyc").write_bytes(b"")
    script = root / "install.sh"
    script.write_text(INSTALL_SH.read_text(encoding="utf-8"), encoding="utf-8")
    # The Docker and free-space gates precede the scan: stand-ins answer them, so
    # the proof holds on a host without Docker or with a nearly full disk.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stand_in(bin_dir, "docker", '[ "$1 $2" = "compose version" ] || exit 1\necho 2.30.1')
    _stand_in(
        bin_dir,
        "df",
        "printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'\n"
        "printf 'stand-in 41943040 0 41943040 0%% /\\n'",
    )
    result = subprocess.run(
        [_sh(), "install.sh", "--check-only"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )
    assert result.returncode == 3
    assert "bytecode" in result.stderr.lower()
