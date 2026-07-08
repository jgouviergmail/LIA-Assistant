"""Skill script executor — sandboxed subprocess execution.

Executes Python scripts from skill scripts/ directories.
Standard: agentskills.io (scripts/ convention).
Code never enters LLM context — only stdout output is returned.

Security:
1. Process isolation: subprocess.run() — no shell=True
2. Env filtering: Only PATH, HOME, LANG, LC_ALL, TZ
3. Network isolation (Linux): unshare -rn (when CAP_SYS_ADMIN is available)
4. Resource limits (POSIX): RLIMIT_AS/NPROC/FSIZE/CPU via preexec_fn — bounds
   the blast radius (fork bombs, memory/disk exhaustion, CPU spin) even when
   namespace isolation is unavailable (audit A2)
5. Temp working dir — no write access to skill/app dirs
6. Path traversal protection: resolve + relative_to check
7. Timeout + output limits
"""

import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.core.constants import SKILLS_SCRIPT_ALLOWED_EXTENSIONS
from src.infrastructure.observability.logging import get_logger

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
