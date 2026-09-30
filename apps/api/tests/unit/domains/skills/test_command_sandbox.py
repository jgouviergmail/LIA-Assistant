"""One skill command in the throwaway container (ADR-327 lot 2).

Three things are pinned here:

- the ``docker run`` line carries the SEC-001 isolation whole, mounts nothing,
  and never writes the command into the bootstrap — it travels as an argument;
- the reader is BOUNDED: a run that writes past its ceiling is stopped and its
  container removed, as is a run past its budget;
- the bootstrap itself, run under a real bash, unpacks the bundle, runs the
  command in the copy and hands back a tar the reader understands.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.constants import SKILL_COMMAND_WORK_ROOT
from src.domains.skills.command_bundle import InputFile, OutputLimits, pack_bundle, read_output
from src.domains.skills.command_sandbox import (
    BOOTSTRAP,
    SandboxTimeout,
    SandboxUnavailable,
    build_command_argv,
    run_bounded,
)
from src.domains.skills.executor import EgressSpec

pytestmark = pytest.mark.unit


def _settings(**overrides: Any) -> Any:
    values = {
        "skills_script_sandbox_image": "lia-skill-sandbox:local",
        "skill_command_max_memory_mb": 1024,
        "skill_command_tmpfs_mb": 256,
        "skill_command_max_file_mb": 25,
        "skills_script_max_processes": 64,
        "skill_command_cpus": 2.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _argv(command: str = "python scripts/fill.py", **overrides: Any) -> list[str]:
    return build_command_argv(
        skill_name="pdf",
        command=command,
        container_name="lia-skill-abc",
        budget_seconds=60,
        text_limit=32 * 1024,
        settings=_settings(**overrides),
    )


class TestArgv:
    def test_the_sec001_isolation_is_whole(self) -> None:
        argv = _argv()
        joined = " ".join(argv)
        for flag in (
            "--network none",
            "--read-only",
            "--user=65534:65534",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory=1024m",
            "--pids-limit=64",
            # Two cores for the budget and its kill grace: a threaded program
            # (numpy, Node) is not killed long before its wall-clock budget.
            "--cpus=2.0",
            "--ulimit=cpu=130",
            f"--ulimit=fsize={25 * 1024 * 1024}",
            "--name=lia-skill-abc",
            "--rm",
        ):
            assert flag in joined, flag

    def test_nothing_is_mounted_and_the_socket_never_travels(self) -> None:
        argv = _argv()
        assert "-v" not in argv and "--volume" not in argv
        assert not any("docker.sock" in arg for arg in argv)

    def test_the_tmpfs_holds_the_run_and_lets_a_shebang_script_execute(self) -> None:
        assert "--tmpfs=/tmp:size=256m,mode=1777,exec" in _argv()

    def test_the_command_is_an_argument_never_part_of_the_script(self) -> None:
        hostile = '"; rm -rf / #'
        argv = _argv(hostile)
        entry = argv.index("--entrypoint")
        assert argv[entry + 1 : entry + 5] == ["bash", "lia-skill-sandbox:local", "-c", BOOTSTRAP]
        assert argv[entry + 5 :] == [
            "lia-skill-command",
            hostile,
            "60",
            str(32 * 1024 + 1),
            SKILL_COMMAND_WORK_ROOT,
        ]
        assert hostile not in BOOTSTRAP

    def test_home_and_the_skill_are_named(self) -> None:
        argv = _argv()
        assert "HOME=/tmp" in argv and "SKILL_NAME=pdf" in argv


class TestANetworkCommand:
    """ADR-327 lot 3: a command with hosts joins the proxy's network, and only that changes."""

    EGRESS = EgressSpec(
        network="lia-sandbox",
        proxy_url="http://egress:3128",
        ca_volume="lia-egress-ca",
        ca_dir="/etc/lia-egress/ca",
        ca_file="/etc/lia-egress/ca/ca.crt",
        tokens={"LIA_KEY_BRAVE_SEARCH": "sbx_run_abc"},
    )

    def _argv(self) -> list[str]:
        return build_command_argv(
            skill_name="pdf",
            command="npm view left-pad version",
            container_name="lia-skill-abc",
            budget_seconds=60,
            text_limit=32 * 1024,
            settings=_settings(),
            egress=self.EGRESS,
        )

    def test_joins_the_proxy_network_and_mounts_only_the_ca(self) -> None:
        argv = self._argv()
        assert argv[argv.index("--network") + 1] == "lia-sandbox"
        volumes = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-v"]
        assert volumes == ["lia-egress-ca:/etc/lia-egress/ca:ro"]

    def test_every_client_trusts_the_proxy_and_the_token_travels(self) -> None:
        env = dict(
            argv_pair.split("=", 1)
            for argv_pair in (
                self._argv()[i + 1] for i, a in enumerate(self._argv()) if a == "--env"
            )
        )
        assert env["HTTPS_PROXY"] == "http://egress:3128"
        for name in ("NODE_EXTRA_CA_CERTS", "GIT_SSL_CAINFO", "PIP_CERT", "SSL_CERT_FILE"):
            assert env[name] == "/etc/lia-egress/ca/ca.crt", name
        assert env["LIA_KEY_BRAVE_SEARCH"] == "sbx_run_abc"

    def test_the_isolation_is_otherwise_untouched(self) -> None:
        joined = " ".join(self._argv())
        for flag in ("--read-only", "--user=65534:65534", "--cap-drop=ALL", "--cpus=2.0"):
            assert flag in joined, flag
        assert "--network none" not in joined

    def test_an_offline_command_stays_offline(self) -> None:
        argv = _argv()
        assert argv[argv.index("--network") + 1] == "none"
        assert not any(arg.startswith("HTTPS_PROXY=") for arg in argv)

    def test_npm_fails_at_once_offline_and_reaches_the_registry_online(self) -> None:
        """Measured 2026-09-30: offline, npm retried until the 60 s budget ran
        out; told it is offline, it fails in 0.25 s naming the cache mode."""
        assert "npm_config_offline=true" in _argv()
        assert not any(arg.startswith("npm_config_offline=") for arg in self._argv())


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


class TestRunBounded:
    def test_stdin_is_fed_and_stdout_returned(self) -> None:
        removed: list[str] = []
        run = run_bounded(
            _python("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()[::-1])"),
            container_name="c1",
            stdin=b"abc",
            timeout=30,
            max_stdout=1_000,
            remove=removed.append,
        )
        assert (run.returncode, run.stdout, run.overflow) == (0, b"cba", False)
        assert removed == []

    def test_a_run_writing_past_its_ceiling_is_stopped_and_removed(self) -> None:
        removed: list[str] = []
        run = run_bounded(
            _python("import sys\nwhile True: sys.stdout.buffer.write(b'x' * 65536)"),
            container_name="c2",
            stdin=b"",
            timeout=30,
            max_stdout=100_000,
            remove=removed.append,
        )
        assert run.overflow
        assert len(run.stdout) == 100_000
        assert removed == ["c2"]

    def test_a_run_past_its_budget_is_removed_and_said(self) -> None:
        removed: list[str] = []
        with pytest.raises(SandboxTimeout):
            run_bounded(
                _python("import time; time.sleep(30)"),
                container_name="c3",
                stdin=b"",
                timeout=1,
                max_stdout=1_000,
                remove=removed.append,
            )
        assert removed == ["c3"]

    def test_no_docker_client_is_a_sandbox_that_is_not_there(self) -> None:
        with pytest.raises(SandboxUnavailable):
            run_bounded(
                ["lia-no-such-program-anywhere"],
                container_name="c4",
                stdin=b"",
                timeout=5,
                max_stdout=10,
                remove=lambda _: None,
            )


_LIMITS = OutputLimits(
    max_text_bytes=1_000, max_files=5, max_file_bytes=10_000, max_total_bytes=20_000
)


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the bootstrap is a POSIX bash script with GNU tar and coreutils",
)
class TestBootstrap:
    """The bootstrap under a real bash — the container's own, minus the container."""

    def _run(self, tmp_path: Path, command: str, *, budget: int = 20) -> Any:
        skill = tmp_path / "skill-src"
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: t\n---\n", encoding="utf-8")
        (skill / "scripts" / "hello.sh").write_text(
            '#!/bin/bash\necho "hello $1"\n', encoding="utf-8"
        )
        upload = tmp_path / "stored.txt"
        upload.write_text("from the person", encoding="utf-8")
        bundle = pack_bundle(
            skill,
            [InputFile(name="note.txt", path=upload, size=upload.stat().st_size)],
            max_bytes=1_000_000,
        )
        root = tmp_path / "work"
        done = subprocess.run(
            ["bash", "-c", BOOTSTRAP, "lia-skill-command", command, str(budget), "1001", str(root)],
            input=bundle,
            capture_output=True,
            timeout=budget + 30,
            check=False,
        )
        return read_output(done.stdout, _LIMITS)

    def test_the_command_runs_in_the_copy_and_its_files_come_back(self, tmp_path: Path) -> None:
        output = self._run(
            tmp_path,
            "./scripts/hello.sh world && cp ../input/note.txt out/copy.txt && echo oops >&2",
        )
        assert output.exit_code == 0
        assert output.stdout == "hello world\n"
        assert output.stderr == "oops\n"
        assert [(f.name, f.data) for f in output.files] == [("copy.txt", b"from the person")]

    def test_a_failing_command_keeps_its_exit_status(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, "exit 3").exit_code == 3

    def test_a_command_past_its_budget_is_stopped_and_still_answers(self, tmp_path: Path) -> None:
        output = self._run(tmp_path, "echo started; sleep 30", budget=1)
        assert output.exit_code == 124
        assert output.stdout == "started\n"

    def test_long_text_is_cut_inside_the_sandbox(self, tmp_path: Path) -> None:
        output = self._run(tmp_path, "head -c 5000 /dev/zero | tr '\\0' 'x'")
        assert output.stdout_truncated
        assert len(output.stdout) == _LIMITS.max_text_bytes
