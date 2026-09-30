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

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    SKILL_COMMAND_COLLECT_GRACE_SECONDS,
    SKILL_COMMAND_CPUS_DEFAULT,
    SKILL_COMMAND_KILL_AFTER_SECONDS,
    SKILL_COMMAND_MAX_FILE_MB_DEFAULT,
    SKILL_COMMAND_MAX_INPUT_MB_DEFAULT,
    SKILL_COMMAND_MAX_MEMORY_MB_DEFAULT,
    SKILL_COMMAND_MAX_OUTPUT_FILES_DEFAULT,
    SKILL_COMMAND_MAX_OUTPUT_MB_DEFAULT,
    SKILL_COMMAND_MAX_TEXT_KB_DEFAULT,
    SKILL_COMMAND_NETWORK_ENABLED_DEFAULT,
    SKILL_COMMAND_RATE_LIMIT_CALLS_DEFAULT,
    SKILL_COMMAND_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    SKILL_COMMAND_TIMEOUT_SECONDS_DEFAULT,
    SKILL_COMMAND_TMPFS_MB_DEFAULT,
    SKILL_PROPOSAL_RATE_LIMIT_CALLS_DEFAULT,
    SKILL_PROPOSAL_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    SKILL_PROPOSAL_TTL_SECONDS_DEFAULT,
    SKILL_PROPOSALS_MAX_PER_USER_DEFAULT,
    SKILL_SCRIPT_ONLY_CUMULATES_NATIVE_PLAN_DEFAULT,
    SKILLS_MAX_PER_USER_DEFAULT,
    SKILLS_SCRIPT_DROP_PRIVILEGES,
    SKILLS_SCRIPT_MAX_CPU_SECONDS,
    SKILLS_SCRIPT_MAX_FILE_SIZE_MB,
    SKILLS_SCRIPT_MAX_INPUT_KB,
    SKILLS_SCRIPT_MAX_MEMORY_MB,
    SKILLS_SCRIPT_MAX_OUTPUT_KB,
    SKILLS_SCRIPT_MAX_PROCESSES,
    SKILLS_SCRIPT_SANDBOX_DEFAULT,
    SKILLS_SCRIPT_SANDBOX_IMAGE_DEFAULT,
    SKILLS_SCRIPT_SANDBOX_PYTHONPATH_DEFAULT,
    SKILLS_SCRIPT_SANDBOX_STARTUP_GRACE_SECONDS,
    SKILLS_SCRIPT_SANDBOX_TMPFS_MB,
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

    skill_script_only_cumulates_native_plan: bool = Field(
        default=SKILL_SCRIPT_ONLY_CUMULATES_NATIVE_PLAN_DEFAULT,
        description=(
            "When True, a script-only skill (scripts, no deterministic "
            "plan_template) no longer bypasses the LLM planner with an empty "
            "plan: the planner emits the detected domain's native steps AND "
            "response_node still activates the skill, so both run. Set to "
            "False to restore the historical empty-plan bypass if the native "
            "steps are noise for your deployment."
        ),
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
            "Let the chat propose a skill it wrote (import_user_skill, the "
            "skill-generator flow): the person installs it from the card under "
            "the answer. When false, generated skills are imported through Settings."
        ),
    )
    skill_proposal_ttl_seconds: int = Field(
        default=SKILL_PROPOSAL_TTL_SECONDS_DEFAULT,
        ge=600,
        le=604800,
        description="How long a skill proposed in the chat may be installed from its card (s).",
    )
    skill_proposals_max_per_user: int = Field(
        default=SKILL_PROPOSALS_MAX_PER_USER_DEFAULT,
        ge=1,
        le=50,
        description="Live skill proposals one account keeps; the oldest makes room.",
    )
    skill_proposal_rate_limit_calls: int = Field(
        default=SKILL_PROPOSAL_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1000,
        description="Reads and installs of skill proposals per account and window.",
    )
    skill_proposal_rate_limit_window_seconds: int = Field(
        default=SKILL_PROPOSAL_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=3600,
        description="The window of the skill proposal rate limit (s).",
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

    skills_script_sandbox: Literal["container", "subprocess"] = Field(
        default=SKILLS_SCRIPT_SANDBOX_DEFAULT,  # type: ignore[arg-type]
        description=(
            "SEC-001. 'container': run each script in a throwaway container with "
            "no Docker socket, no network, read-only root and an unprivileged uid "
            "— the only option that stops a script inheriting the API's docker "
            "group. 'subprocess': historical in-process path, protective ONLY when "
            "the API itself runs as root, and without the sandbox image's libraries. "
            "Selecting 'container' without a reachable Docker daemon fails the "
            "execution; it never downgrades silently."
        ),
    )

    skills_script_sandbox_image: str = Field(
        default=SKILLS_SCRIPT_SANDBOX_IMAGE_DEFAULT,
        min_length=1,
        description=(
            "Image for the sandbox container: the dedicated sandbox image "
            "(apps/api/Dockerfile.sandbox, ADR-327) — Python, Node, the promised "
            "libraries and commands, and neither the Docker client nor the "
            "application's code. `task sandbox:libraries:check` proves an image."
        ),
    )

    skills_script_sandbox_pythonpath: str = Field(
        default=SKILLS_SCRIPT_SANDBOX_PYTHONPATH_DEFAULT,
        description=(
            "PYTHONPATH exported into the sandbox. The production image installs "
            "packages under appuser's home (`pip install --user`); a container "
            "running as another uid resolves a different home and would find none "
            "of them. Empty disables the override."
        ),
    )

    skills_script_sandbox_tmpfs_mb: int = Field(
        default=SKILLS_SCRIPT_SANDBOX_TMPFS_MB,
        ge=1,
        le=512,
        description="Size of the writable /tmp tmpfs inside the sandbox (MB).",
    )

    # ========================================================================
    # Skill commands (ADR-327 lot 2) — gated by skills_scripts_enabled, since
    # they run in the same container sandbox, and refused outside it.
    # ========================================================================

    skill_command_timeout_seconds: int = Field(
        default=SKILL_COMMAND_TIMEOUT_SECONDS_DEFAULT,
        ge=1,
        le=600,
        description="Wall-clock budget of one skill command (seconds).",
    )
    skill_command_max_memory_mb: int = Field(
        default=SKILL_COMMAND_MAX_MEMORY_MB_DEFAULT,
        ge=128,
        le=16384,
        description=(
            "Memory ceiling of a command's container (MB). Its tmpfs pages count "
            "against it: keep it well above skill_command_tmpfs_mb."
        ),
    )
    skill_command_cpus: float = Field(
        default=SKILL_COMMAND_CPUS_DEFAULT,
        ge=0.1,
        le=64,
        description=(
            "Cores one command may use (docker --cpus); its CPU-time ulimit is these "
            "cores over the budget, so a threaded program is not killed early."
        ),
    )
    skill_command_tmpfs_mb: int = Field(
        default=SKILL_COMMAND_TMPFS_MB_DEFAULT,
        ge=16,
        le=8192,
        description="Writable tmpfs of a command's container: the copy, inputs and outputs (MB).",
    )
    skill_command_max_input_mb: int = Field(
        default=SKILL_COMMAND_MAX_INPUT_MB_DEFAULT,
        ge=1,
        le=4096,
        description="What one command carries in — the skill folder and the turn's files (MB).",
    )
    skill_command_max_file_mb: int = Field(
        default=SKILL_COMMAND_MAX_FILE_MB_DEFAULT,
        ge=1,
        le=4096,
        description="Largest single file in or out of a command (MB) — also its fsize ulimit.",
    )
    skill_command_max_output_files: int = Field(
        default=SKILL_COMMAND_MAX_OUTPUT_FILES_DEFAULT,
        ge=1,
        le=100,
        description="Files a command may hand back from out/.",
    )
    skill_command_max_output_mb: int = Field(
        default=SKILL_COMMAND_MAX_OUTPUT_MB_DEFAULT,
        ge=1,
        le=4096,
        description="All the files a command hands back, together (MB).",
    )

    @property
    def skills_script_wall_seconds(self) -> int:
        """How long one script may hold its caller: its budget and the container's start."""
        return self.skills_script_timeout_seconds + SKILLS_SCRIPT_SANDBOX_STARTUP_GRACE_SECONDS

    @property
    def skill_command_wall_seconds(self) -> int:
        """How long one command may hold its caller (ADR-327 lot 2).

        Its budget, the ``timeout -k`` grace, the container's start and the
        packing of what it wrote — the ONE figure the runner waits for and a
        plan step is given, so no layer above cuts a run the sandbox still allows.
        """
        return (
            self.skill_command_timeout_seconds
            + SKILL_COMMAND_KILL_AFTER_SECONDS
            + SKILLS_SCRIPT_SANDBOX_STARTUP_GRACE_SECONDS
            + SKILL_COMMAND_COLLECT_GRACE_SECONDS
        )

    skill_command_rate_limit_calls: int = Field(
        default=SKILL_COMMAND_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=600,
        description="Skill commands one account may run per window (ADR-327).",
    )
    skill_command_rate_limit_window_seconds: int = Field(
        default=SKILL_COMMAND_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=3600,
        description="Window of the skill command rate limit (seconds).",
    )
    skill_command_network_enabled: bool = Field(
        default=SKILL_COMMAND_NETWORK_ENABLED_DEFAULT,
        description=(
            "Let a skill's command reach the hosts it declares through the egress proxy "
            "(ADR-327 lot 3). Effective only where the sandbox's egress capability is on; "
            "off, every command runs offline."
        ),
    )
    skill_command_max_text_kb: int = Field(
        default=SKILL_COMMAND_MAX_TEXT_KB_DEFAULT,
        ge=1,
        le=1024,
        description="Standard output and standard error kept from a command, each (KB).",
    )
