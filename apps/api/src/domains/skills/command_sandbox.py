"""Run one skill command in the SEC-001 throwaway container (ADR-327 lot 2).

The container receives the bundle (``command_bundle.pack_bundle``) on stdin,
runs the command with bash in a copy of the skill folder, and writes one tar
on stdout. Three rules shape this module:

- **the isolation is the scripts' own** (``executor.isolation_flags``): no
  network, read-only root, uid 65534, every capability dropped, bounded
  memory, processes, CPU and file size — and NOTHING mounted;
- **the command is an argument, never part of the script**: the bootstrap is a
  constant, the command reaches it as ``$1``, so no quoting can escape it;
- **what comes back is read under a ceiling**: a run writing past it is
  stopped and its container removed, as is a run past its budget. Killing the
  ``docker run`` client does not stop a container (measured for SEC-001), so
  every path that gives up removes it by name.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import subprocess
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import IO, TYPE_CHECKING

from src.core.constants import (
    SKILL_COMMAND_BOOTSTRAP_ERROR_CODE,
    SKILL_COMMAND_KILL_AFTER_SECONDS,
    SKILL_COMMAND_WORK_ROOT,
    SKILLS_SCRIPT_SANDBOX_DAEMON_ERROR_CODE,
    SKILLS_SCRIPT_SANDBOX_NAME_PREFIX,
)
from src.domains.skills.command_bundle import CommandOutput, OutputLimits, read_output
from src.domains.skills.executor import EgressSpec, egress_args, force_remove, isolation_flags
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.core.config import Settings

__all__ = [
    "BOOTSTRAP",
    "BoundedRun",
    "SandboxTimeout",
    "SandboxUnavailable",
    "build_command_argv",
    "output_limits",
    "run_bounded",
    "run_command",
]

logger = get_logger(__name__)

#: What the container runs: ``$1`` the command, ``$2`` its budget in seconds,
#: ``$3`` the bytes of text kept plus one (so a cut can be seen), ``$4`` the
#: work root. The skill is copied to ``$4/skill``, the turn's files to
#: ``$4/input``; the command runs in the copy, and ``out/`` is what comes back.
#: A constant: nothing a model or a skill wrote is ever interpolated into it.
BOOTSTRAP = f"""set -u
root="$4"
result="$root/.result"
mkdir -p "$root" "$result" || exit {SKILL_COMMAND_BOOTSTRAP_ERROR_CODE}
tar -x -f - -C "$root" || exit {SKILL_COMMAND_BOOTSTRAP_ERROR_CODE}
mkdir -p "$root/skill/out" "$root/input" || exit {SKILL_COMMAND_BOOTSTRAP_ERROR_CODE}
cd "$root/skill" || exit {SKILL_COMMAND_BOOTSTRAP_ERROR_CODE}
timeout -k {SKILL_COMMAND_KILL_AFTER_SECONDS} "$2" bash -c "$1" </dev/null >"$result/stdout" 2>"$result/stderr"
echo "$?" >"$result/exit_code"
truncate -s "<$3" "$result/stdout" "$result/stderr"
exec tar -c -f - -C "$result" stdout stderr exit_code -C "$root/skill" out
"""

#: ``$0`` of the bootstrap — what ``ps`` shows inside the container.
_BOOTSTRAP_NAME = "lia-skill-command"
_CHUNK = 64 * 1024
#: The docker client's own error text is diagnostic, never read in full.
_STDERR_CEILING = 64 * 1024
#: Tar framing around the files: headers, PAX records, padding, end blocks.
_TAR_OVERHEAD = 256 * 1024
#: ``docker run`` could not start the container: daemon, image, or the
#: entrypoint missing from the image (126, 127).
_START_FAILURES = frozenset({SKILLS_SCRIPT_SANDBOX_DAEMON_ERROR_CODE, 126, 127})


class SandboxUnavailable(Exception):
    """The sandbox could not run the command at all — never the command's fault."""


class SandboxTimeout(Exception):
    """The run outlived every grace period; its container was removed."""


@dataclass(frozen=True, slots=True)
class BoundedRun:
    """What the ``docker run`` client returned, bounded.

    Attributes:
        returncode: The client's exit status.
        stdout: What it wrote on stdout, at most the ceiling.
        stderr: What it wrote on stderr, at most its own ceiling.
        overflow: stdout went past the ceiling and the run was stopped.
    """

    returncode: int
    stdout: bytes
    stderr: bytes
    overflow: bool


def output_limits(settings: Settings) -> OutputLimits:
    """What one command may bring back, from the settings."""
    return OutputLimits(
        max_text_bytes=settings.skill_command_max_text_kb * 1024,
        max_files=settings.skill_command_max_output_files,
        max_file_bytes=settings.skill_command_max_file_mb * 1024 * 1024,
        max_total_bytes=settings.skill_command_max_output_mb * 1024 * 1024,
    )


def _stdout_ceiling(limits: OutputLimits) -> int:
    """How much of the container's stdout is read: the files, the text, the framing."""
    return limits.max_total_bytes + 2 * (limits.max_text_bytes + 1) + _TAR_OVERHEAD


def build_command_argv(
    *,
    skill_name: str,
    command: str,
    container_name: str,
    budget_seconds: int,
    text_limit: int,
    settings: Settings,
    egress: EgressSpec | None = None,
) -> list[str]:
    """The ``docker run`` line of one command.

    Args:
        skill_name: The skill, exported as ``SKILL_NAME``.
        command: What bash runs in the copy — passed as ``$1``, never inlined.
        container_name: Unique name, so a run past its budget can be removed.
        budget_seconds: The command's own budget (the in-container ``timeout``).
        text_limit: Bytes of stdout and of stderr kept.
        settings: Application settings.
        egress: The published run's proxy, CA and tokens (ADR-327 lot 3), or
            None for an offline command.

    Returns:
        The argv.
    """
    return [
        "docker",
        "run",
        *isolation_flags(
            container_name=container_name,
            # No network, unless the run was published to the egress proxy:
            # then the INTERNAL network whose only routed member is the proxy.
            network=egress.network if egress is not None else "none",
            # `exec`: a skill's shebang script runs as `./scripts/x.sh`, which
            # grants nothing Python could not already do in the same box.
            tmpfs=f"/tmp:size={settings.skill_command_tmpfs_mb}m,mode=1777,exec",
            memory_mb=settings.skill_command_max_memory_mb,
            processes=settings.skills_script_max_processes,
            # Per process: every core the run may use, for the budget and the
            # kill grace — so the wall clock, not threads, ends a busy program.
            cpu_seconds=math.ceil(
                settings.skill_command_cpus * (budget_seconds + SKILL_COMMAND_KILL_AFTER_SECONDS)
            ),
            file_size_mb=settings.skill_command_max_file_mb,
            cpus=settings.skill_command_cpus,
        ),
        "--env",
        f"SKILL_NAME={skill_name}",
        "--env",
        "HOME=/tmp",
        # Offline, npm is told so: otherwise it retries an unreachable registry
        # until the budget runs out (measured 2026-09-30: > 60 s, against
        # 0.25 s and a « cache mode » error once told).
        *(egress_args(egress) if egress is not None else ["--env", "npm_config_offline=true"]),
        "--entrypoint",
        "bash",
        settings.skills_script_sandbox_image,
        "-c",
        BOOTSTRAP,
        _BOOTSTRAP_NAME,
        command,
        str(budget_seconds),
        str(text_limit + 1),
        SKILL_COMMAND_WORK_ROOT,
    ]


def _feed(stream: IO[bytes], data: bytes) -> None:
    """Write the bundle, tolerating a client that stopped reading."""
    try:
        for start in range(0, len(data), _CHUNK):
            stream.write(data[start : start + _CHUNK])
    except OSError:
        # The client stopped reading (it died, or the run was stopped): the
        # outcome is decided by what it wrote and how it exited.
        logger.debug("skill_command_stdin_closed_early")
    finally:
        # Closing flushes, possibly into the same broken pipe.
        with contextlib.suppress(OSError):
            stream.close()


def _drain(
    stream: IO[bytes],
    sink: bytearray,
    ceiling: int,
    on_overflow: Callable[[], None] | None = None,
) -> None:
    """Read ``stream`` into ``sink`` up to ``ceiling``.

    Past it, ``on_overflow`` is called and reading stops; without one, the rest
    is read and dropped, so the writer never blocks on a full pipe.
    """
    with stream:
        while chunk := stream.read(_CHUNK):
            room = ceiling - len(sink)
            if len(chunk) <= room:
                sink += chunk
                continue
            sink += chunk[:room]
            if on_overflow is not None:
                on_overflow()
                return


def run_bounded(
    cmd: Sequence[str],
    *,
    container_name: str,
    stdin: bytes,
    timeout: float,
    max_stdout: int,
    remove: Callable[[str], None] = force_remove,
) -> BoundedRun:
    """Run the ``docker run`` client with a bounded reader. Blocking: call it in a thread.

    It runs entirely in a worker thread on purpose, like the scripts' runner:
    the cleanup must happen even when the coroutine awaiting it is cancelled.

    Args:
        cmd: The argv.
        container_name: What to remove when the run is given up on.
        stdin: The bundle.
        timeout: Wall-clock budget of the whole run, graces included.
        max_stdout: Bytes of stdout read; past them the run is stopped.
        remove: How a container is removed (the real ``docker rm`` by default).

    Returns:
        The bounded run.

    Raises:
        SandboxUnavailable: No docker client.
        SandboxTimeout: The run outlived ``timeout`` (its container removed).
    """
    try:
        process = subprocess.Popen(
            list(cmd), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except FileNotFoundError as exc:
        # Refused, never downgraded to an in-process run (SEC-001).
        logger.error("skill_command_sandbox_unavailable", reason="docker_client_missing")
        raise SandboxUnavailable("docker client not found") from exc
    pipes = (process.stdin, process.stdout, process.stderr)
    if pipes[0] is None or pipes[1] is None or pipes[2] is None:
        process.kill()
        raise SandboxUnavailable("docker client pipes missing")
    stdout, stderr = bytearray(), bytearray()
    overflow = threading.Event()

    def stop() -> None:
        overflow.set()
        remove(container_name)
        process.kill()

    threads = [
        threading.Thread(target=_feed, args=(pipes[0], stdin), daemon=True),
        threading.Thread(target=_drain, args=(pipes[1], stdout, max_stdout, stop), daemon=True),
        # The client's own error text: bounded, the rest dropped, never stopped on.
        threading.Thread(target=_drain, args=(pipes[2], stderr, _STDERR_CEILING), daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        remove(container_name)
        process.kill()
        process.wait()
        raise SandboxTimeout(container_name) from exc
    finally:
        for thread in threads:
            thread.join(timeout=SKILL_COMMAND_KILL_AFTER_SECONDS)
    return BoundedRun(
        returncode=process.returncode,
        stdout=bytes(stdout),
        stderr=bytes(stderr),
        overflow=overflow.is_set(),
    )


async def run_command(
    *,
    skill_name: str,
    command: str,
    bundle: bytes,
    settings: Settings,
    user_id: str | None,
    egress: EgressSpec | None = None,
) -> CommandOutput:
    """Run one command on one bundle and read what it handed back.

    Args:
        skill_name: The skill (logs, ``SKILL_NAME``).
        command: What bash runs in the copy.
        bundle: The tar of the skill and the turn's files.
        settings: Application settings.
        user_id: The person (logs).
        egress: The published run's network (ADR-327 lot 3), or None offline.

    Returns:
        The bounded output — ``incomplete`` when the run wrote past the ceiling.

    Raises:
        SandboxUnavailable: The sandbox could not run anything.
        SandboxTimeout: The run outlived every grace period.
        UnreadableOutput: The run handed back something that is not its tar.
    """
    limits = output_limits(settings)
    budget = settings.skill_command_timeout_seconds
    container_name = f"{SKILLS_SCRIPT_SANDBOX_NAME_PREFIX}{uuid.uuid4().hex[:16]}"
    argv = build_command_argv(
        skill_name=skill_name,
        command=command,
        container_name=container_name,
        budget_seconds=budget,
        text_limit=limits.max_text_bytes,
        settings=settings,
        egress=egress,
    )
    run = await asyncio.to_thread(
        run_bounded,
        argv,
        container_name=container_name,
        stdin=bundle,
        timeout=settings.skill_command_wall_seconds,
        max_stdout=_stdout_ceiling(limits),
    )
    if not run.stdout and (
        run.returncode in _START_FAILURES or run.returncode == SKILL_COMMAND_BOOTSTRAP_ERROR_CODE
    ):
        # The client's stderr names our image and daemon: logged by length,
        # never handed to the model.
        logger.error(
            "skill_command_sandbox_unavailable",
            skill_name=skill_name,
            exit_code=run.returncode,
            stderr_length=len(run.stderr),
            user_id=user_id,
        )
        raise SandboxUnavailable(str(run.returncode))
    output = read_output(run.stdout, limits)
    if run.overflow:
        output = replace(output, incomplete=True)
    return output
