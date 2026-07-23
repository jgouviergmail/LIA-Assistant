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
    SKILLS_URL_IMPORT_MAX_BYTES_DEFAULT,
    SKILLS_URL_IMPORT_RATE_MAX_CALLS_DEFAULT,
    SKILLS_URL_IMPORT_RATE_WINDOW_SECONDS_DEFAULT,
    SKILLS_URL_IMPORT_TIMEOUT_SECONDS_DEFAULT,
    SKILLS_USERS_PATH_DEFAULT,
    SKILLS_ZIP_MAX_DECOMPRESSED_KB,
    SKILLS_ZIP_MAX_FILES,
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
    # Import Hardening (upload endpoints + chat import tool)
    # ========================================================================

    skills_zip_max_decompressed_kb: int = Field(
        default=SKILLS_ZIP_MAX_DECOMPRESSED_KB,
        ge=100,
        le=51200,
        description=(
            "Maximum total decompressed size of an imported skill package (KB). "
            "Guards against zip bombs — checked before extraction."
        ),
    )

    skills_zip_max_files: int = Field(
        default=SKILLS_ZIP_MAX_FILES,
        ge=1,
        le=512,
        description="Maximum number of files in an imported skill package.",
    )

    skills_chat_import_enabled: bool = Field(
        default=True,
        description=(
            "Enable direct skill import from chat via the import_user_skill tool "
            "(skill-generator flow). When false, generated skills must be "
            "imported manually through Settings."
        ),
    )

    # ========================================================================
    # URL Import (UXR Lot 10, B12)
    # ========================================================================

    skills_url_import_enabled: bool = Field(
        default=True,
        description=(
            "Enable POST /skills/import-from-url (https-only, SSRF-validated, "
            "streamed size cap; feeds the same hardened import pipeline as "
            "file upload)."
        ),
    )

    skills_url_import_max_bytes: int = Field(
        default=SKILLS_URL_IMPORT_MAX_BYTES_DEFAULT,
        ge=1024,
        le=52_428_800,
        description="Streamed download cap for URL-sourced skill imports (bytes).",
    )

    skills_url_import_timeout_seconds: int = Field(
        default=SKILLS_URL_IMPORT_TIMEOUT_SECONDS_DEFAULT,
        ge=1,
        le=120,
        description="Total HTTP timeout for URL-sourced skill imports (seconds).",
    )

    skills_url_import_rate_max_calls: int = Field(
        default=SKILLS_URL_IMPORT_RATE_MAX_CALLS_DEFAULT,
        ge=1,
        le=1000,
        description=(
            "Per-user outbound-fetch attempts allowed per window on "
            "POST /skills/import-from-url (failed imports consume no quota)."
        ),
    )

    skills_url_import_rate_window_seconds: int = Field(
        default=SKILLS_URL_IMPORT_RATE_WINDOW_SECONDS_DEFAULT,
        ge=60,
        le=86_400,
        description="Sliding-window size for the URL-import rate limit (seconds).",
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
