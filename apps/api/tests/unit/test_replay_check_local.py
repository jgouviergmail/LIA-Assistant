"""Hermetic tests for the portable local migration-replay launcher (F048).

The launcher (``scripts/db/replay_check_local.py``) drives the host ``docker`` CLI
through an injectable runner, so every branch — Docker missing (the Windows/WSL
failure the audit flagged), daemon unreachable, happy path, and guaranteed DROP
in ``finally`` on create/replay failure — is exercised WITHOUT a real Docker
daemon by substituting a recording/faulting runner.
"""

from __future__ import annotations

import importlib.util
import subprocess
from collections.abc import Sequence
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
LAUNCHER_PATH = REPO_ROOT / "scripts" / "db" / "replay_check_local.py"


def _load_launcher() -> ModuleType:
    if not LAUNCHER_PATH.is_file():
        pytest.skip("guard needs the full repository checkout (scripts/db/replay_check_local.py).")
    spec = importlib.util.spec_from_file_location("replay_check_local", LAUNCHER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = _load_launcher()


class RecordingRunner:
    """Records every argv and optionally faults when an argv matches a needle."""

    def __init__(
        self,
        *,
        fail_on: str | None = None,
        exc: BaseException | None = None,
        printenv_stdout: str = "postgresql+asyncpg://u:p@lia-postgres-dev:5432/lia",
    ) -> None:
        self.calls: list[list[str]] = []
        self._fail_on = fail_on
        self._exc = exc
        self._printenv_stdout = printenv_stdout

    def __call__(
        self, argv: Sequence[str], capture_output: bool = False
    ) -> subprocess.CompletedProcess[str]:
        argv = list(argv)
        self.calls.append(argv)
        joined = " ".join(argv)
        if self._exc is not None and "docker version" in joined:
            raise self._exc
        if self._fail_on is not None and self._fail_on in joined:
            raise subprocess.CalledProcessError(1, argv, stderr="boom")
        stdout = self._printenv_stdout if "printenv" in argv else ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def flat(self) -> str:
        return "\n".join(" ".join(c) for c in self.calls)


# --------------------------------------------------------------------------- #
# require_docker: the Windows/WSL failure the audit flagged
# --------------------------------------------------------------------------- #


def test_require_docker_missing_cli_raises_actionable() -> None:
    runner = RecordingRunner(exc=FileNotFoundError("docker"))
    with pytest.raises(launcher.ReplayCheckError, match="PowerShell"):
        launcher.require_docker(runner)


def test_require_docker_daemon_unreachable_raises_actionable() -> None:
    runner = RecordingRunner(
        exc=subprocess.CalledProcessError(1, ["docker", "version"], stderr="cannot connect")
    )
    with pytest.raises(launcher.ReplayCheckError, match="daemon is unreachable"):
        launcher.require_docker(runner)


def test_require_docker_ok_does_not_raise() -> None:
    runner = RecordingRunner()
    launcher.require_docker(runner)
    assert runner.calls[0][:2] == ["docker", "version"]


# --------------------------------------------------------------------------- #
# run_replay_check: ordering, uniqueness, guaranteed DROP
# --------------------------------------------------------------------------- #


def test_happy_path_probes_docker_first_creates_replays_then_drops() -> None:
    runner = RecordingRunner()
    launcher.run_replay_check(runner)
    flat = runner.flat()

    # Docker is validated before any mutation.
    assert runner.calls[0][:2] == ["docker", "version"]
    # A unique throwaway DB is created, extensions added, chain replayed, DB dropped.
    assert "CREATE DATABASE lia_alembic_replay_check_" in flat
    assert "CREATE EXTENSION IF NOT EXISTS vector" in flat
    assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' in flat
    assert "docker cp" in flat
    assert "bash /tmp/check_migrations_replay.sh" in flat
    assert "DROP DATABASE IF EXISTS lia_alembic_replay_check_" in flat
    # No shell string is ever passed: every call is an argv list (shell-agnostic).
    assert all(isinstance(c, list) for c in runner.calls)


def test_database_name_is_unique_per_run() -> None:
    names = set()
    for _ in range(5):
        runner = RecordingRunner()
        launcher.run_replay_check(runner)
        created = [c for c in runner.calls if any("CREATE DATABASE" in a for a in c)][0]
        names.add(next(a for a in created if "CREATE DATABASE" in a))
    assert len(names) == 5, "throwaway DB name must be unique per run to avoid collisions"


def test_drop_runs_even_when_replay_fails() -> None:
    runner = RecordingRunner(fail_on="check_migrations_replay.sh")
    with pytest.raises(launcher.ReplayCheckError, match="replay check failed"):
        launcher.run_replay_check(runner)
    assert "DROP DATABASE IF EXISTS lia_alembic_replay_check_" in runner.flat()


def test_drop_runs_even_when_create_fails() -> None:
    runner = RecordingRunner(fail_on="CREATE DATABASE")
    with pytest.raises(launcher.ReplayCheckError):
        launcher.run_replay_check(runner)
    assert "DROP DATABASE IF EXISTS lia_alembic_replay_check_" in runner.flat()


def test_no_mutation_when_docker_unavailable() -> None:
    runner = RecordingRunner(exc=FileNotFoundError("docker"))
    with pytest.raises(launcher.ReplayCheckError):
        launcher.run_replay_check(runner)
    # Only the probe ran; no CREATE/DROP was attempted.
    assert runner.flat().count("docker version") == 1
    assert "CREATE DATABASE" not in runner.flat()
    assert "DROP DATABASE" not in runner.flat()


def test_drop_failure_is_non_fatal_and_warns(capsys: pytest.CaptureFixture[str]) -> None:
    # DROP itself fails, but the (successful) replay result must not be masked.
    runner = RecordingRunner(fail_on="DROP DATABASE")
    launcher.run_replay_check(runner)  # must NOT raise
    assert "could not drop throwaway database" in capsys.readouterr().err


def test_main_returns_1_with_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> None:
        raise launcher.ReplayCheckError("docker missing")

    monkeypatch.setattr(launcher, "run_replay_check", _boom)
    assert launcher.main() == 1
