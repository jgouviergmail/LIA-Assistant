"""Skill script executor — sandboxed subprocess execution.

Executes Python scripts from skill scripts/ directories.
Standard: agentskills.io (scripts/ convention).
Code never enters LLM context — only stdout output is returned.

Security:
1. Process isolation: subprocess.run() — no shell=True
2. Env filtering: Only PATH, HOME, LANG, LC_ALL, TZ
3. Network isolation (Linux): unshare -rn
4. Temp working dir — no write access to skill/app dirs
5. Path traversal protection: resolve + relative_to check
6. Timeout + output limits
"""

import asyncio
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.core.constants import (
    SKILLS_SCRIPT_ALLOWED_EXTENSIONS,
    SKILLS_SCRIPT_MAX_INPUT_KB,
    SKILLS_SCRIPT_MAX_OUTPUT_KB,
    SKILLS_SCRIPT_TIMEOUT_SECONDS,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


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
        timeout = timeout_seconds or getattr(
            settings, "skills_script_timeout_seconds", SKILLS_SCRIPT_TIMEOUT_SECONDS
        )
        max_output = (
            getattr(settings, "skills_script_max_output_kb", SKILLS_SCRIPT_MAX_OUTPUT_KB) * 1024
        )
        max_input = (
            getattr(settings, "skills_script_max_input_kb", SKILLS_SCRIPT_MAX_INPUT_KB) * 1024
        )

        # Resolve script path (user-scoped for override semantics)
        skill = (
            SkillsCache.get_by_name_for_user(skill_name, user_id)
            if user_id
            else SkillsCache.get_by_name(skill_name)
        )
        if not skill:
            return ScriptResult(success=False, output="", error=f"Skill '{skill_name}' not found")

        skill_dir = Path(skill["source_path"]).parent
        script_path = skill_dir / "scripts" / script_name

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
                error=f"Input exceeds {SKILLS_SCRIPT_MAX_INPUT_KB}KB",
            )

        # Safe environment
        safe_env = {k: v for k, v in os.environ.items() if k in cls._ALLOWED_ENV_KEYS}
        safe_env["SKILL_NAME"] = skill_name
        safe_env["SKILL_DIR"] = str(skill_dir)

        # Network isolation on Linux; sys.executable for cross-platform portability
        python_cmd = sys.executable or "python3"
        if platform.system() == "Linux":
            cmd = ["unshare", "-rn", "--", python_cmd, str(script_path)]
        else:
            cmd = [python_cmd, str(script_path)]

        start_time = time.monotonic()

        try:
            with tempfile.TemporaryDirectory(prefix="skill_") as tmp_dir:
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    input=stdin_payload,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmp_dir,
                    env=safe_env,
                )

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            output = result.stdout[:max_output] if result.stdout else ""

            if result.returncode != 0:
                logger.warning(
                    "skill_script_failed",
                    skill_name=skill_name,
                    script=script_name,
                    exit_code=result.returncode,
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
