"""Skill script executor — sandboxed script execution.

Executes Python scripts from skill scripts/ directories.
Standard: agentskills.io (scripts/ convention).
Code never enters LLM context — only stdout output is returned.

Two modes, selected by ``SKILLS_SCRIPT_SANDBOX``:

**container** (default, SEC-001) — one throwaway sibling container per run:
no Docker socket, ``--network none``, read-only rootfs + a small tmpfs,
uid 65534, all capabilities dropped, memory/pids/CPU/fsize bounded. The
script SOURCE is passed inline (``python -c``) so nothing from the API
filesystem is mounted and stdin stays free for the JSON payload. An
unreachable daemon fails the execution — never a silent downgrade.

**subprocess** (legacy) — in-process execution, kept for environments with
no Docker daemon. It only isolates when the API itself runs as root:

1. Process isolation: subprocess.run() — no shell=True
2. Env filtering: Only PATH, HOME, LANG, LC_ALL, TZ
3. Network isolation (Linux): unshare -rn (when CAP_SYS_ADMIN is available)
4. Resource limits (POSIX): RLIMIT_AS/NPROC/FSIZE/CPU via preexec_fn — bounds
   the blast radius (fork bombs, memory/disk exhaustion, CPU spin) even when
   namespace isolation is unavailable (audit A2)
5. Temp working dir — no write access to skill/app dirs

Common to both: path-traversal protection (resolve + relative_to), extension
allow-list, stdin/stdout size caps and a wall-clock timeout.
"""

import asyncio
import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from src.core.constants import (
    SKILLS_SCRIPT_ALLOWED_EXTENSIONS,
    SKILLS_SCRIPT_SANDBOX_CLEANUP_TIMEOUT_SECONDS,
    SKILLS_SCRIPT_SANDBOX_DAEMON_ERROR_CODE,
    SKILLS_SCRIPT_SANDBOX_MAX_SOURCE_BYTES,
    SKILLS_SCRIPT_SANDBOX_NAME_PREFIX,
    SKILLS_SCRIPT_SANDBOX_STARTUP_GRACE_SECONDS,
    SKILLS_SCRIPT_SANDBOX_UID,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.core.config import Settings

logger = get_logger(__name__)


def _build_rlimit_preexec(
    *,
    max_memory_mb: int,
    max_processes: int,
    max_file_size_mb: int,
    max_cpu_seconds: int,
    drop_to_uid: int | None = None,
    drop_to_gid: int | None = None,
) -> Callable[[], None] | None:
    """Build a preexec_fn that sandboxes a skill subprocess before ``exec``.

    Two POSIX-only defenses, applied in the forked child (inherited across
    ``exec`` and by descendants):

    1. Privilege drop (audit A1): when ``drop_to_uid`` is set and the parent
       is root, clear ALL supplementary groups then setgid/setuid to an
       unprivileged id. This denies the root-owned Docker socket to skill
       scripts (a mount-namespace mask needs CAP_SYS_ADMIN, absent here) and
       makes RLIMIT_NPROC effective (it is bypassed for uid 0). Groups MUST
       be cleared first — otherwise the retained ``docker``/``root`` group
       would still grant socket access after the uid change.
    2. Resource limits (audit A2): RLIMIT_AS/NPROC/FSIZE/CPU. Each soft limit
       is clamped to the inherited hard limit so an already-unprivileged
       process never tries to RAISE a ceiling (which would raise ValueError).

    Returns ``None`` on platforms without the ``resource`` module (e.g.
    Windows), where subprocess ``preexec_fn`` is unsupported anyway.

    Args:
        max_memory_mb: RLIMIT_AS ceiling in MB.
        max_processes: RLIMIT_NPROC ceiling (fork-bomb guard).
        max_file_size_mb: RLIMIT_FSIZE ceiling in MB.
        max_cpu_seconds: RLIMIT_CPU ceiling in seconds.
        drop_to_uid: Unprivileged uid to drop to, or None to keep the uid.
        drop_to_gid: Unprivileged gid to drop to (required with ``drop_to_uid``).

    Returns:
        A zero-argument callable for ``subprocess`` ``preexec_fn``, or None.
    """
    try:
        import resource
    except ImportError:  # pragma: no cover - non-POSIX
        return None

    limits: list[tuple[int, int]] = [
        (resource.RLIMIT_AS, max_memory_mb * 1024 * 1024),
        (resource.RLIMIT_NPROC, max_processes),
        (resource.RLIMIT_FSIZE, max_file_size_mb * 1024 * 1024),
        (resource.RLIMIT_CPU, max_cpu_seconds),
    ]

    def _apply() -> None:
        # 1. Privilege drop FIRST (needs root): groups → gid → uid. Ordering is
        # security-critical — setgroups/setgid must precede setuid.
        if drop_to_uid is not None and drop_to_gid is not None:
            os.setgroups([drop_to_gid])
            os.setgid(drop_to_gid)
            os.setuid(drop_to_uid)
        # 2. Resource limits (work unprivileged when only lowering).
        for res, soft in limits:
            _, hard = resource.getrlimit(res)
            new_soft = soft if hard == resource.RLIM_INFINITY else min(soft, hard)
            resource.setrlimit(res, (new_soft, hard))

    return _apply


class ScriptResult(BaseModel):
    """Result of a skill script execution."""

    success: bool
    output: str
    error: str | None = None
    exit_code: int = 0
    execution_time_ms: int = 0


class SkillScriptExecutor:
    """Execute skill scripts in sandboxed subprocess."""

    _ALLOWED_ENV_KEYS = frozenset({"PATH", "HOME", "LANG", "LC_ALL", "TZ"})
    _unshare_checked: bool = False
    _unshare_works: bool = False

    @classmethod
    def _unshare_available(cls) -> bool:
        """Check once if unshare -rn is available (requires CAP_SYS_ADMIN)."""
        if not cls._unshare_checked:
            try:
                result = subprocess.run(
                    ["unshare", "-rn", "--", "true"],
                    capture_output=True,
                    timeout=2,
                )
                cls._unshare_works = result.returncode == 0
            except Exception:
                cls._unshare_works = False
            if not cls._unshare_works:
                logger.info("unshare_not_available", msg="Falling back to direct execution")
            cls._unshare_checked = True
        return cls._unshare_works

    @staticmethod
    def _build_sandbox_command(
        *,
        source: str,
        skill_name: str,
        container_name: str,
        timeout: int,
        settings: Settings,
    ) -> list[str]:
        """Build the `docker run` argv for one sandboxed script execution.

        The script SOURCE is passed as an argument rather than mounted. The API
        itself runs in a container, so a `-v /app/data/skills/...` bind would
        resolve against the HOST filesystem — where that path does not exist —
        and user skills live in a named volume anyway. Handing over the source
        removes both problems and leaves stdin free for the JSON payload, which
        is the contract every existing skill relies on.

        Args:
            source: Python source of the script.
            skill_name: Skill the script belongs to (exposed as SKILL_NAME).
            container_name: Unique name, so a timed-out run can be force-removed.
            timeout: Wall-clock budget, used for the CPU rlimit inside.
            settings: Application settings.

        Returns:
            The argv list for `docker run`.
        """
        limits = [
            "--rm",
            "--interactive",
            # Killing the `docker run` client does NOT stop the container
            # (measured): without a name to target, a script that ignores its
            # budget — `time.sleep(1e9)` burns no CPU, so the CPU rlimit never
            # fires — would linger forever holding memory and pids.
            f"--name={container_name}",
            # No network at all: no skill shipped today makes a network call
            # (verified across all of them), and an isolated script has no
            # business reaching the LAN or the metadata service.
            "--network",
            "none",
            "--read-only",
            f"--user={SKILLS_SCRIPT_SANDBOX_UID}:{SKILLS_SCRIPT_SANDBOX_UID}",
            f"--tmpfs=/tmp:size={settings.skills_script_sandbox_tmpfs_mb}m,mode=1777",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            f"--memory={settings.skills_script_max_memory_mb}m",
            f"--pids-limit={settings.skills_script_max_processes}",
            # Belt and braces with the outer timeout: a script that ignores
            # SIGTERM still dies when the CPU budget runs out.
            f"--ulimit=cpu={min(settings.skills_script_max_cpu_seconds, timeout)}",
            f"--ulimit=fsize={settings.skills_script_max_file_size_mb * 1024 * 1024}",
            "--env",
            f"SKILL_NAME={skill_name}",
            # HOME must point at the tmpfs: the root filesystem is read-only, so
            # anything writing to a home-relative path would fail otherwise.
            "--env",
            "HOME=/tmp",
        ]
        if settings.skills_script_sandbox_pythonpath:
            limits += ["--env", f"PYTHONPATH={settings.skills_script_sandbox_pythonpath}"]

        return [
            "docker",
            "run",
            *limits,
            "--entrypoint",
            "python",
            settings.skills_script_sandbox_image,
            "-c",
            source,
        ]

    @staticmethod
    def _run_sandbox_sync(
        *,
        cmd: list[str],
        container_name: str,
        stdin_payload: str,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        """Run the sandbox container, force-removing it if it outlives its budget.

        Runs entirely in a worker thread on purpose. ``subprocess.run`` kills
        the `docker run` CLIENT on timeout, which leaves the CONTAINER running
        on the daemon (measured) — so the cleanup has to happen here, where it
        still runs even if the awaiting coroutine was cancelled in the
        meantime.

        Args:
            cmd: The `docker run` argv.
            container_name: Name given to the container, used for the cleanup.
            stdin_payload: JSON payload written to the script's stdin.
            timeout: Wall-clock budget for the whole run, in seconds.

        Returns:
            The completed `docker run` process.

        Raises:
            subprocess.TimeoutExpired: Budget exhausted (container removed).
            FileNotFoundError: No docker CLI on PATH.
        """
        try:
            return subprocess.run(
                cmd,
                input=stdin_payload,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            # Best-effort: a script sleeping forever burns no CPU, so neither
            # the CPU rlimit nor `--rm` would ever reclaim it.
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                subprocess.run(
                    ["docker", "rm", "--force", container_name],
                    capture_output=True,
                    timeout=SKILLS_SCRIPT_SANDBOX_CLEANUP_TIMEOUT_SECONDS,
                )
            raise

    @classmethod
    async def _execute_in_container(
        cls,
        *,
        skill_name: str,
        script_name: str,
        script_path: Path,
        stdin_payload: str,
        timeout: int,
        max_output: int,
        user_id: str | None,
        settings: Settings,
    ) -> ScriptResult:
        """Run a skill script in a throwaway container (SEC-001).

        Args:
            skill_name: Skill owning the script.
            script_name: Script file name, for logs and errors.
            script_path: Resolved path of the script on the API's filesystem.
            stdin_payload: JSON payload handed to the script on stdin.
            timeout: Wall-clock budget in seconds.
            max_output: Maximum stdout kept, in bytes.
            user_id: Caller, for the audit trail.
            settings: Application settings.

        Returns:
            The script result, or a failure describing why it could not run.
        """
        try:
            source = script_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("skill_script_unreadable", skill_name=skill_name, error=str(exc))
            return ScriptResult(success=False, output="", error="Script could not be read")

        if len(source.encode("utf-8")) > SKILLS_SCRIPT_SANDBOX_MAX_SOURCE_BYTES:
            # Fail loudly rather than hand the daemon a truncated program.
            return ScriptResult(
                success=False,
                output="",
                error=f"Script exceeds {SKILLS_SCRIPT_SANDBOX_MAX_SOURCE_BYTES // 1024}KB",
            )

        container_name = f"{SKILLS_SCRIPT_SANDBOX_NAME_PREFIX}{uuid.uuid4().hex[:16]}"
        cmd = cls._build_sandbox_command(
            source=source,
            skill_name=skill_name,
            container_name=container_name,
            timeout=timeout,
            settings=settings,
        )
        start_time = time.monotonic()

        try:
            result = await asyncio.to_thread(
                cls._run_sandbox_sync,
                cmd=cmd,
                container_name=container_name,
                stdin_payload=stdin_payload,
                # The container has to start before the script does; without the
                # grace period a script using its full budget would be killed by
                # this timeout instead of its own.
                timeout=timeout + SKILLS_SCRIPT_SANDBOX_STARTUP_GRACE_SECONDS,
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning(
                "skill_script_timeout",
                skill_name=skill_name,
                script=script_name,
                timeout_seconds=timeout,
                user_id=user_id,
                sandbox="container",
            )
            return ScriptResult(
                success=False,
                output="",
                error=f"Timeout after {timeout}s",
                exit_code=-1,
                execution_time_ms=elapsed_ms,
            )
        except FileNotFoundError:
            # No Docker client reachable. Refuse rather than fall back to the
            # in-process path: a sandbox with an automatic downgrade protects
            # nothing, since the downgrade is exactly what an attacker wants.
            logger.error(
                "skill_script_sandbox_unavailable",
                skill_name=skill_name,
                msg="docker CLI not found — refusing to run the script unsandboxed",
            )
            return ScriptResult(
                success=False,
                output="",
                error="Script sandbox unavailable",
            )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        output = result.stdout[:max_output] if result.stdout else ""

        if result.returncode == SKILLS_SCRIPT_SANDBOX_DAEMON_ERROR_CODE:
            # 125 is the daemon/CLI refusing to start the container (missing
            # image, bad flag, daemon down) — not a script failure. Surfacing
            # its stderr would hand the LLM our image names and daemon state.
            logger.error(
                "skill_script_sandbox_unavailable",
                skill_name=skill_name,
                script=script_name,
                stderr=result.stderr[:500] if result.stderr else "",
                user_id=user_id,
            )
            return ScriptResult(
                success=False,
                output="",
                error="Script sandbox unavailable",
                exit_code=result.returncode,
                execution_time_ms=elapsed_ms,
            )

        if result.returncode != 0:
            logger.warning(
                "skill_script_failed",
                skill_name=skill_name,
                script=script_name,
                exit_code=result.returncode,
                stderr=result.stderr[:500] if result.stderr else "",
                stdout=result.stdout[:500] if result.stdout else "",
                user_id=user_id,
                sandbox="container",
            )
            return ScriptResult(
                success=False,
                output=output,
                error=result.stderr[:1000] if result.stderr else "Script failed",
                exit_code=result.returncode,
                execution_time_ms=elapsed_ms,
            )

        logger.info(
            "skill_script_executed",
            skill_name=skill_name,
            script=script_name,
            user_id=user_id,
            output_length=len(output),
            elapsed_ms=elapsed_ms,
            sandbox="container",
        )
        return ScriptResult(success=True, output=output, execution_time_ms=elapsed_ms)

    @classmethod
    async def execute(
        cls,
        skill_name: str,
        script_name: str,
        parameters: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
        user_id: str | None = None,
    ) -> ScriptResult:
        """Execute a skill script in sandboxed subprocess."""
        from src.core.config import get_settings
        from src.domains.skills.cache import SkillsCache

        settings = get_settings()
        timeout = timeout_seconds or settings.skills_script_timeout_seconds
        max_output = settings.skills_script_max_output_kb * 1024
        max_input = settings.skills_script_max_input_kb * 1024

        # Resolve script path (user-scoped for override semantics)
        skill = (
            SkillsCache.get_by_name_for_user(skill_name, user_id)
            if user_id
            else SkillsCache.get_by_name(skill_name)
        )
        if not skill:
            return ScriptResult(success=False, output="", error=f"Skill '{skill_name}' not found")

        skill_dir = Path(skill["source_path"]).parent.resolve()
        script_path = (skill_dir / "scripts" / script_name).resolve()

        if not script_path.exists():
            return ScriptResult(success=False, output="", error=f"Script '{script_name}' not found")

        if script_path.suffix not in SKILLS_SCRIPT_ALLOWED_EXTENSIONS:
            return ScriptResult(success=False, output="", error="Only .py scripts are supported")

        # Path traversal check
        try:
            script_path.resolve().relative_to(skill_dir.resolve())
        except ValueError:
            logger.warning(
                "skill_script_path_traversal",
                skill_name=skill_name,
                script=script_name,
            )
            return ScriptResult(success=False, output="", error="Path traversal detected")

        # Build stdin payload
        stdin_payload = json.dumps(
            {
                "parameters": parameters or {},
                "context": context or {},
                "skill_name": skill_name,
            },
            ensure_ascii=False,
            default=str,
        )

        if len(stdin_payload.encode()) > max_input:
            return ScriptResult(
                success=False,
                output="",
                error=f"Input exceeds {settings.skills_script_max_input_kb}KB",
            )

        # Safe environment
        safe_env = {k: v for k, v in os.environ.items() if k in cls._ALLOWED_ENV_KEYS}
        safe_env["SKILL_NAME"] = skill_name
        safe_env["SKILL_DIR"] = str(skill_dir)

        # SEC-001 — throwaway container. Everything below this branch is the
        # historical in-process path, which only isolates when the API runs as
        # root; production runs as `appuser`, so a script there inherits the
        # supplementary `docker` group and reaches the mounted socket.
        if settings.skills_script_sandbox == "container":
            return await cls._execute_in_container(
                skill_name=skill_name,
                script_name=script_name,
                script_path=script_path,
                stdin_payload=stdin_payload,
                timeout=timeout,
                max_output=max_output,
                user_id=user_id,
                settings=settings,
            )

        # Privilege drop (audit A1): if we are root, run the script as an
        # unprivileged uid so it cannot open the root-owned Docker socket and
        # so RLIMIT_NPROC applies. Privilege drop and `unshare` are mutually
        # exclusive at the preexec level (unshare needs the root we drop), and
        # unshare is unavailable in these containers anyway — so on the drop
        # path we skip unshare and rely on the uid change + rlimits.
        is_posix = platform.system() != "Windows"
        drop_uid: int | None = None
        drop_gid: int | None = None
        if (
            is_posix
            and settings.skills_script_drop_privileges
            and hasattr(os, "geteuid")
            and os.geteuid() == 0
        ):
            drop_uid = settings.skills_script_unprivileged_uid
            drop_gid = settings.skills_script_unprivileged_gid

        # Use bare Python interpreter — avoid debugpy/pydevd wrappers that crash
        # in sandboxed subprocesses. debugpy hooks subprocess.run at the parent
        # process level, so we must use env(1) to launch a fully clean process.
        python_cmd = shutil.which("python3") or shutil.which("python") or sys.executable
        if platform.system() == "Linux" and drop_uid is None and cls._unshare_available():
            cmd = (
                ["unshare", "-rn", "--", "env", "-i"]
                + [f"{k}={v}" for k, v in safe_env.items()]
                + [python_cmd, str(script_path)]
            )
            # env -i replaces the full environment, so don't pass env= to subprocess
            safe_env = None  # type: ignore[assignment]
        elif platform.system() == "Linux":
            # No unshare (or dropping privileges) — still escape debugpy via env -i
            cmd = (
                ["env", "-i"]
                + [f"{k}={v}" for k, v in safe_env.items()]
                + [python_cmd, str(script_path)]
            )
            safe_env = None  # type: ignore[assignment]
        else:
            cmd = [python_cmd, str(script_path)]

        # Sandbox preexec (POSIX): privilege drop (A1) + resource limits (A2).
        # rlimits bound the blast radius (fork bomb, memory/disk/CPU) and the
        # uid drop denies the Docker socket; both are inherited across exec.
        preexec_fn = _build_rlimit_preexec(
            max_memory_mb=settings.skills_script_max_memory_mb,
            max_processes=settings.skills_script_max_processes,
            max_file_size_mb=settings.skills_script_max_file_size_mb,
            max_cpu_seconds=min(settings.skills_script_max_cpu_seconds, timeout),
            drop_to_uid=drop_uid,
            drop_to_gid=drop_gid,
        )

        start_time = time.monotonic()

        try:
            with tempfile.TemporaryDirectory(prefix="skill_") as tmp_dir:
                # When dropping privileges, the temp cwd (created 0700, root)
                # must be writable by the unprivileged uid so legitimate
                # scripts can still write output files. Transfer ownership to
                # that uid and keep the mode at 0700 (owner-only): no other
                # uid can read or tamper with the sandbox, unlike the previous
                # world-writable 0777. Cleanup by the parent still works (it
                # runs privileged, which is what allows the setuid drop).
                if drop_uid is not None:
                    os.chown(tmp_dir, drop_uid, -1)
                    os.chmod(tmp_dir, 0o700)
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    input=stdin_payload,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmp_dir,
                    env=safe_env,
                    preexec_fn=preexec_fn,  # noqa: PLW1509 — intentional sandbox
                )

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            output = result.stdout[:max_output] if result.stdout else ""

            if result.returncode != 0:
                logger.warning(
                    "skill_script_failed",
                    skill_name=skill_name,
                    script=script_name,
                    exit_code=result.returncode,
                    stderr=result.stderr[:500] if result.stderr else "",
                    stdout=result.stdout[:500] if result.stdout else "",
                    user_id=user_id,
                )
                return ScriptResult(
                    success=False,
                    output=output,
                    error=result.stderr[:1000] if result.stderr else "Script failed",
                    exit_code=result.returncode,
                    execution_time_ms=elapsed_ms,
                )

            logger.info(
                "skill_script_executed",
                skill_name=skill_name,
                script=script_name,
                user_id=user_id,
                output_length=len(output),
                elapsed_ms=elapsed_ms,
            )
            return ScriptResult(success=True, output=output, execution_time_ms=elapsed_ms)

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return ScriptResult(
                success=False,
                output="",
                error=f"Timeout after {timeout}s",
                exit_code=-1,
                execution_time_ms=elapsed_ms,
            )
        except Exception as exc:
            logger.error("skill_script_error", skill_name=skill_name, error=str(exc))
            return ScriptResult(success=False, output="", error=str(exc), exit_code=-1)
