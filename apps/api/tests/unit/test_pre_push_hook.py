"""The pre-push hook scans exactly what a push sends.

The CI's secret scan runs after a push; the hook runs the same scanner before it
(`task security:secrets`, dependency programme, 2026-10-02). A wrong range is a
scan of nothing — a failure nobody sees — so the hook runs here against stand-ins
for Task and Docker, on each shape a push announces on stdin.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
HOOK = ROOT / ".github" / "hooks" / "pre-push"
ZERO = "0" * 40
LOCAL = "a" * 40
REMOTE = "b" * 40


def _bash() -> str:
    """Git's own bash on Windows (a bare `bash` may be the WSL launcher)."""
    git = shutil.which("git")
    if os.name == "nt" and git:
        for parent in Path(git).resolve().parents:
            candidate = parent / "usr" / "bin" / "bash.exe"
            if candidate.exists():
                return str(candidate)
    found = shutil.which("bash")
    assert found, "bash runs the git hooks; it is not on PATH"
    return found


def _stand_in(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _push(
    tmp_path: Path, lines: list[str], *, docker_up: bool = True, scan_exit: int = 0
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the hook with `lines` on stdin; return its result and every `task` call.

    Bytes, not text: git writes LF to a hook's stdin, and text mode on Windows
    would turn each LF into CRLF.
    """
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    calls = tmp_path / "calls.txt"
    _stand_in(stand_ins, "task", f'printf "%s\\n" "$*" >> "{calls.as_posix()}"\nexit {scan_exit}')
    _stand_in(stand_ins, "docker", f"exit {0 if docker_up else 1}")
    raw = subprocess.run(
        [_bash(), str(HOOK)],
        input="".join(f"{line}\n" for line in lines).encode("utf-8"),
        capture_output=True,
        env={**os.environ, "PATH": f"{stand_ins}{os.pathsep}{os.environ['PATH']}"},
        check=False,
    )
    result = subprocess.CompletedProcess(
        raw.args, raw.returncode, raw.stdout.decode("utf-8"), raw.stderr.decode("utf-8")
    )
    made = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []
    return result, made


def test_an_updated_ref_scans_what_the_remote_lacks(tmp_path: Path) -> None:
    result, calls = _push(tmp_path, [f"refs/heads/main {LOCAL} refs/heads/main {REMOTE}"])

    assert result.returncode == 0, result.stderr
    assert calls == [f"security:secrets RANGE={REMOTE}..{LOCAL}"]


def test_a_new_ref_scans_everything_no_remote_has(tmp_path: Path) -> None:
    result, calls = _push(tmp_path, [f"refs/heads/topic {LOCAL} refs/heads/topic {ZERO}"])

    assert result.returncode == 0, result.stderr
    assert calls == [f"security:secrets RANGE={LOCAL} --not --remotes"]


def test_a_deletion_sends_nothing_and_scans_nothing(tmp_path: Path) -> None:
    result, calls = _push(tmp_path, [f"(delete) {ZERO} refs/heads/old {REMOTE}"])

    assert result.returncode == 0, result.stderr
    assert calls == []


def test_every_ref_is_scanned_and_one_leak_stops_the_push(tmp_path: Path) -> None:
    lines = [
        f"refs/heads/main {LOCAL} refs/heads/main {REMOTE}",
        f"refs/tags/v9.9.9 {REMOTE} refs/tags/v9.9.9 {ZERO}",
    ]
    result, calls = _push(tmp_path, lines, scan_exit=2)

    assert result.returncode == 1
    assert len(calls) == 2, "a failed ref must not hide the scan of the next one"
    assert "nothing was pushed" in result.stderr


def test_no_docker_refuses_the_push_rather_than_skipping_the_scan(tmp_path: Path) -> None:
    result, calls = _push(
        tmp_path, [f"refs/heads/main {LOCAL} refs/heads/main {REMOTE}"], docker_up=False
    )

    assert result.returncode == 1
    assert calls == []
    assert "Docker is not running" in result.stderr
