"""
Skills configuration module.

Contains settings for:
- Skills feature toggle (enabled/disabled)
- Skills filesystem paths (system + user)
- Skills per-user limits
- Script execution settings (timeout, output limits)

Phase: evolution — Agent Skills (agentskills.io open standard)
Reference: docs/technical/SKILLS_INTEGRATION.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    SKILLS_MAX_PER_USER_DEFAULT,
    SKILLS_SCRIPT_DROP_PRIVILEGES,
    SKILLS_SCRIPT_MAX_CPU_SECONDS,
    SKILLS_SCRIPT_MAX_FILE_SIZE_MB,
    SKILLS_SCRIPT_MAX_INPUT_KB,
    SKILLS_SCRIPT_MAX_MEMORY_MB,
    SKILLS_SCRIPT_MAX_OUTPUT_KB,
    SKILLS_SCRIPT_MAX_PROCESSES,
    SKILLS_SCRIPT_TIMEOUT_SECONDS,
    SKILLS_SCRIPT_UNPRIVILEGED_GID,
    SKILLS_SCRIPT_UNPRIVILEGED_UID,
    SKILLS_SYSTEM_PATH_DEFAULT,
    SKILLS_USERS_PATH_DEFAULT,
)


class SkillsSettings(BaseSettings):
    """Skills settings for agentskills.io standard integration."""

    # ========================================================================
    # Feature Toggle
    # ========================================================================

    skills_enabled: bool = Field(
        default=True,
        description=(
            "Enable Agent Skills system. When true, SKILL.md files are loaded "
            "from disk and injected into the LLM pipeline (catalogue + activation)."
        ),
    )

    # ========================================================================
    # Filesystem Paths
    # ========================================================================

    skills_system_path: str = Field(
        default=SKILLS_SYSTEM_PATH_DEFAULT,
        description="Path to system (admin) skills directory. Git-tracked, read-only at runtime.",
    )

    skills_users_path: str = Field(
        default=SKILLS_USERS_PATH_DEFAULT,
        description="Path to user-imported skills directory. Writable, per-user subdirectories.",
    )

    # ========================================================================
    # Per-User Limits
    # ========================================================================

    skills_max_per_user: int = Field(
        default=SKILLS_MAX_PER_USER_DEFAULT,
        ge=1,
        le=100,
        description="Maximum number of imported skills per user.",
    )

    # ========================================================================
    # Script Execution
    # ========================================================================

    skills_scripts_enabled: bool = Field(
        default=True,
        description=(
            "Enable skill script execution via run_skill_script tool. "
            "Scripts run in sandboxed subprocess with filtered environment."
        ),
    )

    skills_script_timeout_seconds: int = Field(
        default=SKILLS_SCRIPT_TIMEOUT_SECONDS,
        ge=5,
        le=120,
        description="Maximum execution time for skill scripts (seconds).",
    )

    skills_script_max_output_kb: int = Field(
        default=SKILLS_SCRIPT_MAX_OUTPUT_KB,
        ge=1,
        le=500,
        description="Maximum stdout output from skill scripts (KB).",
    )

    skills_script_max_input_kb: int = Field(
        default=SKILLS_SCRIPT_MAX_INPUT_KB,
        ge=1,
        le=500,
        description="Maximum stdin input to skill scripts (KB).",
    )

    # ========================================================================
    # Subprocess resource limits (rlimit via preexec_fn — audit A2)
    # ========================================================================
    # Bound the blast radius of a malicious/buggy skill script. Applied on
    # POSIX only; a no-op on platforms without the `resource` module.

    skills_script_max_memory_mb: int = Field(
        default=SKILLS_SCRIPT_MAX_MEMORY_MB,
        ge=64,
        le=4096,
        description="Address-space ceiling per skill subprocess (RLIMIT_AS, MB).",
    )

    skills_script_max_processes: int = Field(
        default=SKILLS_SCRIPT_MAX_PROCESSES,
        ge=1,
        le=1024,
        description="Max processes/threads per skill subprocess (RLIMIT_NPROC — kills fork bombs).",
    )

    skills_script_max_file_size_mb: int = Field(
        default=SKILLS_SCRIPT_MAX_FILE_SIZE_MB,
        ge=1,
        le=1024,
        description="Max size of any file a skill script may write (RLIMIT_FSIZE, MB).",
    )

    skills_script_max_cpu_seconds: int = Field(
        default=SKILLS_SCRIPT_MAX_CPU_SECONDS,
        ge=1,
        le=300,
        description="CPU-time ceiling per skill subprocess (RLIMIT_CPU — complements wall timeout).",
    )

    skills_script_drop_privileges: bool = Field(
        default=SKILLS_SCRIPT_DROP_PRIVILEGES,
        description=(
            "When the API runs as root, drop skill subprocesses to an "
            "unprivileged uid/gid (supplementary groups cleared) before exec. "
            "Denies the root-owned Docker socket to skill scripts (audit A1)."
        ),
    )

    skills_script_unprivileged_uid: int = Field(
        default=SKILLS_SCRIPT_UNPRIVILEGED_UID,
        ge=1,
        description="Target uid for dropped skill subprocesses (default: nobody).",
    )

    skills_script_unprivileged_gid: int = Field(
        default=SKILLS_SCRIPT_UNPRIVILEGED_GID,
        ge=1,
        description="Target gid for dropped skill subprocesses (default: nogroup).",
    )
