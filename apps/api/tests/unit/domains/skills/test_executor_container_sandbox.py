"""SEC-001 — the throwaway-container sandbox for skill scripts.

The historical in-process path only isolates a script when the API runs as
root: it drops the uid before ``exec``. Production runs as ``appuser``, which
belongs to the ``docker`` group, so a script there inherited a writable Docker
socket — i.e. root on the host. The container path removes that inheritance by
construction: a fresh container, no socket, no network, read-only root, uid
65534, all capabilities dropped.

These tests never contact a Docker daemon. They pin two things:

1. the exact hardening carried by the ``docker run`` argv (a future edit that
   drops ``--network none`` or adds a bind mount must turn one of them red);
2. the fail-closed contract — when the daemon is unreachable the execution is
   refused, never silently downgraded to the in-process path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import Settings, get_settings
from src.core.constants import (
    SKILLS_SCRIPT_SANDBOX_DAEMON_ERROR_CODE,
    SKILLS_SCRIPT_SANDBOX_DEFAULT,
    SKILLS_SCRIPT_SANDBOX_MAX_SOURCE_BYTES,
    SKILLS_SCRIPT_SANDBOX_NAME_PREFIX,
    SKILLS_SCRIPT_SANDBOX_STARTUP_GRACE_SECONDS,
    SKILLS_SCRIPT_SANDBOX_UID,
)
from src.domains.skills.executor import ScriptResult, SkillScriptExecutor


def _sandbox_settings(**overrides: object) -> Settings:
    """A REAL ``Settings`` with the sandbox knobs pinned.

    A ``SimpleNamespace`` stand-in would happily answer a misspelled attribute
    the production code never actually reads, so the builder is exercised
    against the real type.
    """
    base: dict[str, object] = {
        "skills_script_sandbox": "container",
        "skills_script_sandbox_image": "lia-api:local",
        "skills_script_sandbox_pythonpath": "/home/appuser/.local/lib/python3.12/site-packages",
        "skills_script_sandbox_tmpfs_mb": 32,
        "skills_script_max_memory_mb": 512,
        "skills_script_max_processes": 64,
        "skills_script_max_file_size_mb": 10,
        "skills_script_max_cpu_seconds": 30,
    }
    base.update(overrides)
    return get_settings().model_copy(update=base)


@pytest.fixture
def skill_root() -> Iterator[Path]:
    """A real, world-readable skill tree (mirrors production perms)."""
    root = Path(tempfile.mkdtemp(prefix="sandboxskill_"))
    os.chmod(root, 0o755)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _make_skill(skill_root: Path, script_body: str) -> dict[str, str]:
    """Create an on-disk skill and return the matching SkillsCache row."""
    skill_dir = skill_root / "probe-skill"
    (skill_dir / "scripts").mkdir(parents=True)
    source = skill_dir / "SKILL.md"
    source.write_text("# probe\n", encoding="utf-8")
    (skill_dir / "scripts" / "run.py").write_text(script_body, encoding="utf-8")
    return {"name": "probe-skill", "source_path": str(source)}


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


class TestSandboxCommand:
    """The argv handed to `docker run` carries every isolation flag."""

    def test_every_required_hardening_flag_is_present(self) -> None:
        """Drop any of these and the sandbox stops being a sandbox."""
        cmd = SkillScriptExecutor._build_sandbox_command(
            source="print(1)",
            skill_name="s",
            container_name="lia-skill-test",
            timeout=30,
            settings=_sandbox_settings(),
        )

        required = {
            "--rm",  # no forensic leftovers, no disk growth
            "--read-only",  # rootfs immutable
            "--cap-drop=ALL",  # no CAP_DAC_OVERRIDE, no CAP_NET_RAW…
            "--security-opt=no-new-privileges:true",  # setuid binaries neutered
            f"--user={SKILLS_SCRIPT_SANDBOX_UID}:{SKILLS_SCRIPT_SANDBOX_UID}",
        }
        missing = required - set(cmd)
        assert not missing, f"hardening flags lost: {sorted(missing)}"
        # --network takes its value as the next argv element.
        assert cmd[cmd.index("--network") + 1] == "none"

    def test_no_bind_mount_and_no_socket_are_ever_requested(self) -> None:
        """The whole point: the sandbox inherits nothing from the API host."""
        cmd = SkillScriptExecutor._build_sandbox_command(
            source="print(1)",
            skill_name="s",
            container_name="lia-skill-test",
            timeout=30,
            settings=_sandbox_settings(),
        )

        assert "-v" not in cmd
        assert "--volume" not in cmd
        assert "--privileged" not in cmd
        assert not any("docker.sock" in arg for arg in cmd)
        assert not any(arg.startswith("--mount") for arg in cmd)

    def test_source_is_passed_inline_not_mounted(self) -> None:
        """`python -c <source>` — stdin stays free for the JSON payload."""
        source = "import sys, json\nprint(json.load(sys.stdin))\n"
        cmd = SkillScriptExecutor._build_sandbox_command(
            source=source,
            container_name="lia-skill-test",
            skill_name="s",
            timeout=30,
            settings=_sandbox_settings(),
        )

        assert cmd[:2] == ["docker", "run"]
        assert cmd[-3:] == ["lia-api:local", "-c", source]
        assert cmd[cmd.index("--entrypoint") + 1] == "python"
        # --interactive is what keeps stdin attached; without it the payload
        # never reaches the script and every skill silently sees EOF.
        assert "--interactive" in cmd

    def test_resource_ceilings_follow_the_settings(self) -> None:
        """Memory, pids, fsize and CPU are all bounded from configuration."""
        settings = _sandbox_settings(
            skills_script_max_memory_mb=256,
            skills_script_max_processes=16,
            skills_script_max_file_size_mb=4,
            skills_script_max_cpu_seconds=25,
            skills_script_sandbox_tmpfs_mb=8,
        )
        cmd = SkillScriptExecutor._build_sandbox_command(
            source="print(1)",
            container_name="lia-skill-test",
            skill_name="s",
            timeout=60,
            settings=settings,
        )

        assert "--memory=256m" in cmd
        assert "--pids-limit=16" in cmd
        assert f"--ulimit=fsize={4 * 1024 * 1024}" in cmd
        assert "--tmpfs=/tmp:size=8m,mode=1777" in cmd
        # CPU ceiling is the tighter of the two budgets.
        assert "--ulimit=cpu=25" in cmd

    def test_cpu_ceiling_never_exceeds_the_wall_clock_budget(self) -> None:
        """A short per-call timeout must tighten the CPU rlimit, not relax it."""
        cmd = SkillScriptExecutor._build_sandbox_command(
            source="print(1)",
            container_name="lia-skill-test",
            skill_name="s",
            timeout=5,
            settings=_sandbox_settings(skills_script_max_cpu_seconds=30),
        )

        assert "--ulimit=cpu=5" in cmd

    def test_home_and_skill_name_are_exported(self) -> None:
        """HOME must land on the tmpfs — the rootfs is read-only."""
        cmd = SkillScriptExecutor._build_sandbox_command(
            source="print(1)",
            container_name="lia-skill-test",
            skill_name="qr-code",
            timeout=30,
            settings=_sandbox_settings(),
        )

        assert "SKILL_NAME=qr-code" in cmd
        assert "HOME=/tmp" in cmd

    def test_pythonpath_is_exported_when_configured(self) -> None:
        """The production image installs deps under appuser's home."""
        cmd = SkillScriptExecutor._build_sandbox_command(
            source="print(1)",
            skill_name="s",
            container_name="lia-skill-test",
            timeout=30,
            settings=_sandbox_settings(),
        )

        assert "PYTHONPATH=/home/appuser/.local/lib/python3.12/site-packages" in cmd

    def test_pythonpath_is_omitted_when_empty(self) -> None:
        """An empty setting must not export a bogus empty PYTHONPATH."""
        cmd = SkillScriptExecutor._build_sandbox_command(
            source="print(1)",
            container_name="lia-skill-test",
            skill_name="s",
            timeout=30,
            settings=_sandbox_settings(skills_script_sandbox_pythonpath=""),
        )

        assert not any(arg.startswith("PYTHONPATH") for arg in cmd)


# ---------------------------------------------------------------------------
# Execution contract
# ---------------------------------------------------------------------------


class TestContainerExecution:
    """`execute()` routes to the sandbox and honours its failure modes."""

    @pytest.fixture(autouse=True)
    def _force_container_sandbox(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Pin container mode on the cached settings instance.

        ``get_settings()`` is ``@lru_cache``d: an environment variable set
        after import time never reaches ``execute()``.
        """
        from src.core.config import get_settings

        monkeypatch.setattr(get_settings(), "skills_script_sandbox", "container")

    async def _run(self, skill: dict[str, str], **kwargs: object) -> ScriptResult:
        call: dict[str, object] = {
            "skill_name": "probe-skill",
            "script_name": "run.py",
            "user_id": "u1",
        }
        call.update(kwargs)
        with patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user", return_value=skill):
            return await SkillScriptExecutor.execute(**call)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_execute_uses_docker_and_forwards_the_payload(self, skill_root: Path) -> None:
        """The JSON payload reaches the container on stdin, unmodified."""
        skill = _make_skill(skill_root, "print('ok')\n")
        fake = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="ok\n", stderr=""))

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill, parameters={"x": 42})

        assert result.success, result.error
        assert result.output.strip() == "ok"
        cmd = fake.call_args.args[0]
        assert cmd[:2] == ["docker", "run"]
        # The script SOURCE, not its path, is what gets executed.
        assert cmd[-1] == "print('ok')\n"
        payload = fake.call_args.kwargs["input"]
        assert '"x": 42' in payload
        # shell=True would reintroduce injection through the source itself.
        assert fake.call_args.kwargs.get("shell") is not True

    @pytest.mark.asyncio
    async def test_timeout_leaves_room_for_container_startup(self, skill_root: Path) -> None:
        """The outer timeout must not fire before the script's own budget."""
        skill = _make_skill(skill_root, "print('ok')\n")
        fake = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))

        with patch("src.domains.skills.executor.subprocess.run", fake):
            await self._run(skill, timeout_seconds=20)

        assert fake.call_args.kwargs["timeout"] == 20 + SKILLS_SCRIPT_SANDBOX_STARTUP_GRACE_SECONDS

    @pytest.mark.asyncio
    async def test_missing_docker_client_fails_closed(self, skill_root: Path) -> None:
        """No daemon → refusal. A sandbox that downgrades protects nothing."""
        skill = _make_skill(skill_root, "print('ok')\n")
        fake = MagicMock(side_effect=FileNotFoundError("docker"))

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill)

        assert result.success is False
        assert result.error == "Script sandbox unavailable"
        # Exactly one attempt: no retry with a plain interpreter.
        assert fake.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_is_reported_with_the_declared_budget(self, skill_root: Path) -> None:
        """The user-facing message quotes the script budget, not the grace."""
        skill = _make_skill(skill_root, "print('ok')\n")
        fake = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=45))

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill, timeout_seconds=30)

        assert result.success is False
        assert result.error == "Timeout after 30s"
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_timeout_force_removes_the_container(self, skill_root: Path) -> None:
        """Killing the client leaves the container running — measured.

        A script that sleeps burns no CPU, so the CPU rlimit never fires and
        ``--rm`` never triggers: without an explicit removal the container
        would outlive its own timeout indefinitely.
        """
        skill = _make_skill(skill_root, "import time; time.sleep(999)\n")
        fake = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=45))

        with patch("src.domains.skills.executor.subprocess.run", fake):
            await self._run(skill, timeout_seconds=30)

        run_argv = fake.call_args_list[0].args[0]
        cleanup_argv = fake.call_args_list[1].args[0]
        container_name = next(arg.split("=", 1)[1] for arg in run_argv if arg.startswith("--name="))
        assert cleanup_argv == ["docker", "rm", "--force", container_name]

    @pytest.mark.asyncio
    async def test_a_failing_cleanup_never_masks_the_timeout(self, skill_root: Path) -> None:
        """Best-effort removal: its own failure must not swallow the verdict."""
        skill = _make_skill(skill_root, "import time; time.sleep(999)\n")
        fake = MagicMock(
            side_effect=[
                subprocess.TimeoutExpired(cmd="docker", timeout=45),
                OSError("daemon gone"),
            ]
        )

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill, timeout_seconds=30)

        assert result.error == "Timeout after 30s"

    @pytest.mark.asyncio
    async def test_container_names_are_unique_per_run(self, skill_root: Path) -> None:
        """Two concurrent runs must not collide on the container name."""
        skill = _make_skill(skill_root, "print('ok')\n")
        fake = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))

        with patch("src.domains.skills.executor.subprocess.run", fake):
            await self._run(skill)
            await self._run(skill)

        names = [
            arg for call in fake.call_args_list for arg in call.args[0] if arg.startswith("--name=")
        ]
        assert len(names) == 2
        assert names[0] != names[1]
        assert all(name.startswith(f"--name={SKILLS_SCRIPT_SANDBOX_NAME_PREFIX}") for name in names)

    @pytest.mark.asyncio
    async def test_daemon_refusal_is_not_reported_as_a_script_failure(
        self, skill_root: Path
    ) -> None:
        """Exit 125 = the daemon refused to start it; stderr stays internal."""
        skill = _make_skill(skill_root, "print('ok')\n")
        fake = MagicMock(
            return_value=SimpleNamespace(
                returncode=SKILLS_SCRIPT_SANDBOX_DAEMON_ERROR_CODE,
                stdout="",
                stderr="Unable to find image 'lia-api:local' locally",
            )
        )

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill)

        assert result.success is False
        assert result.error == "Script sandbox unavailable"
        # The image name and daemon state must not reach the LLM context.
        assert "lia-api" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_non_zero_exit_surfaces_stderr_bounded(self, skill_root: Path) -> None:
        """A failing script reports its stderr, capped so it cannot flood."""
        skill = _make_skill(skill_root, "raise SystemExit(3)\n")
        fake = MagicMock(
            return_value=SimpleNamespace(returncode=3, stdout="", stderr="boom" * 1000)
        )

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill)

        assert result.success is False
        assert result.exit_code == 3
        assert result.error is not None
        assert len(result.error) == 1000

    @pytest.mark.asyncio
    async def test_stdout_is_truncated_to_the_configured_ceiling(
        self, skill_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A chatty script cannot blow up the LLM context."""
        from src.core.config import get_settings

        monkeypatch.setattr(get_settings(), "skills_script_max_output_kb", 1)
        skill = _make_skill(skill_root, "print('x' * 999999)\n")
        fake = MagicMock(
            return_value=SimpleNamespace(returncode=0, stdout="x" * 999_999, stderr="")
        )

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill)

        assert result.success is True
        assert len(result.output) == 1024

    @pytest.mark.asyncio
    async def test_oversized_source_is_refused_before_docker(self, skill_root: Path) -> None:
        """Never hand the daemon a program bigger than the argv budget."""
        skill = _make_skill(skill_root, "#" * (SKILLS_SCRIPT_SANDBOX_MAX_SOURCE_BYTES + 1))
        fake = MagicMock()

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill)

        assert result.success is False
        assert result.error is not None and "KB" in result.error
        fake.assert_not_called()

    @pytest.mark.asyncio
    async def test_unreadable_script_is_refused_without_leaking_the_path(
        self, skill_root: Path
    ) -> None:
        """An I/O failure must not echo a filesystem path back to the LLM."""
        skill = _make_skill(skill_root, "print('ok')\n")
        fake = MagicMock()

        with (
            patch("src.domains.skills.executor.subprocess.run", fake),
            patch.object(Path, "read_text", side_effect=OSError("EIO")),
        ):
            result = await self._run(skill)

        assert result.success is False
        assert result.error == "Script could not be read"
        fake.assert_not_called()

    @pytest.mark.asyncio
    async def test_path_traversal_is_still_rejected_in_container_mode(
        self, skill_root: Path
    ) -> None:
        """The pre-sandbox guards run before the branch, not after."""
        skill = _make_skill(skill_root, "print('ok')\n")
        # A real, readable .py OUTSIDE the skill dir — otherwise the request
        # would be stopped by the existence/extension checks and this test
        # would pass without ever reaching the traversal guard.
        (skill_root / "evil.py").write_text("print('pwned')\n", encoding="utf-8")
        fake = MagicMock()

        with patch("src.domains.skills.executor.subprocess.run", fake):
            result = await self._run(skill, script_name="../../evil.py")

        assert result.success is False
        assert result.error == "Path traversal detected"
        fake.assert_not_called()


class TestSandboxDefault:
    """The secure mode is the default — a silent flip back must be loud."""

    def test_default_is_the_container_sandbox(self) -> None:
        assert SKILLS_SCRIPT_SANDBOX_DEFAULT == "container"

    def test_settings_expose_the_container_default(self) -> None:
        from src.core.config.skills import SkillsSettings

        assert SkillsSettings().skills_script_sandbox == "container"

    def test_sandbox_uid_is_unprivileged(self) -> None:
        """uid 0 here would hand the script root inside the container."""
        assert SKILLS_SCRIPT_SANDBOX_UID > 0
