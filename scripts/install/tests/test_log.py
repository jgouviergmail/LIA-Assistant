"""Installer log contract (B13): private, redacted, non-secret codes."""

from __future__ import annotations

import os
from pathlib import Path

from scripts.install.log import InstallLog

SECRET = "pw-CANARY-77!aa"


def test_log_file_is_private_and_redacts_registered_secrets(
    tmp_path: Path,
) -> None:
    path = tmp_path / "install.log"
    log = InstallLog(path, secrets=(SECRET,))
    log.write("step_started", step="bootstrap")
    log.write("step_failed", step="bootstrap", detail=f"stdin was {SECRET}")
    body = path.read_text(encoding="utf-8")
    assert "step_started" in body
    assert "step_failed" in body
    assert SECRET not in body
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600


def test_secrets_registered_later_are_covered(tmp_path: Path) -> None:
    log = InstallLog(tmp_path / "install.log", secrets=())
    log.add_secret(SECRET)
    log.write("echo", detail=SECRET)
    assert SECRET not in (tmp_path / "install.log").read_text(encoding="utf-8")


def test_recorded_argv_is_redacted_without_mutating_the_original(
    tmp_path: Path,
) -> None:
    log = InstallLog(tmp_path / "install.log", secrets=(SECRET,))
    argv = ["docker", "compose", "run", f"--env=TOKEN={SECRET}"]
    recorded = log.redact_argv(argv)
    assert SECRET not in " ".join(recorded)
    assert argv[3] == f"--env=TOKEN={SECRET}", "original argv untouched"


def test_lines_are_timestamped_and_append_only(tmp_path: Path) -> None:
    path = tmp_path / "install.log"
    log = InstallLog(path, secrets=())
    log.write("first")
    log.write("second")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        assert line[:4].isdigit(), f"missing ISO timestamp: {line}"
        assert "+00:00" in line or "Z" in line, "timestamps must be UTC-aware"
