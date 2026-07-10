"""
DevOps settings for Claude CLI remote server management.

Allows administrators to interact with Claude Code CLI installed on dev/prod servers
via SSH, enabling autonomous server inspection, log analysis, and container management.

Servers are configured as a JSON array in the DEVOPS_SERVERS environment variable.
Each server entry supports:
  - name: str — identifier (e.g. "dev", "prod")
  - host: str — IP or hostname
  - port: int — SSH port (default 22)
  - username: str — SSH user
  - ssh_key_path: str | None — path to SSH private key
  - working_directory: str — where Claude CLI runs (default "~/lia-workspace")
  - allowed_claude_tools: list[str] — Claude CLI --allowedTools
  - disallowed_claude_tools: list[str] — Claude CLI --disallowedTools (priority over allowed)
  - max_turns: int — Claude CLI --max-turns (default 30)
  - description: str — server description for the LLM planner
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    DEVOPS_CLAUDE_TOOL_TIMEOUT_SECONDS_DEFAULT,
    DEVOPS_DEFAULT_COMMAND_TIMEOUT,
    DEVOPS_DEFAULT_MAX_OUTPUT_CHARS,
    DEVOPS_DEFAULT_SSH_TIMEOUT,
    DEVOPS_RATE_LIMIT_CALLS_DEFAULT,
    DEVOPS_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
)


class DevOpsSettings(BaseSettings):
    """Settings for DevOps Claude CLI remote server management."""

    devops_enabled: bool = Field(
        default=True,
        description="Enable DevOps Claude CLI remote management feature.",
    )
    devops_servers: str = Field(
        default="[]",
        description="JSON array of server configurations.",
    )
    devops_ssh_timeout: int = Field(
        default=DEVOPS_DEFAULT_SSH_TIMEOUT,
        description="SSH connection timeout in seconds.",
    )
    devops_command_timeout: int = Field(
        default=DEVOPS_DEFAULT_COMMAND_TIMEOUT,
        description="Claude CLI command execution timeout in seconds.",
    )
    devops_max_output_chars: int = Field(
        default=DEVOPS_DEFAULT_MAX_OUTPUT_CHARS,
        description="Maximum output characters before truncation.",
    )
    devops_rate_limit_calls: int = Field(
        default=DEVOPS_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=50,
        description=(
            "Max claude_server_task_tool calls per user per window. "
            "Anti-runaway ceiling: each call is a paid Claude CLI run plus "
            "real actions on a remote server over SSH. Each task lasts up to "
            "~120s wall-clock, so the default (5/10min) cannot hinder normal "
            "sequential admin use."
        ),
    )
    devops_rate_limit_window: int = Field(
        default=DEVOPS_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Rate limit window (seconds) for claude_server_task_tool.",
    )
    devops_claude_tool_timeout_seconds: float = Field(
        default=DEVOPS_CLAUDE_TOOL_TIMEOUT_SECONDS_DEFAULT,
        ge=30.0,
        le=900.0,
        description=(
            "Wall-clock timeout (seconds) applied by the parallel executor "
            "to a single `claude_server_task_tool` step. Default 120s. "
            "Distinct from `devops_command_timeout` (which bounds the remote "
            "Claude CLI itself) — this one bounds the round trip including "
            "SSH connect + CLI startup. Should normally be smaller than "
            "`devops_command_timeout` so we surface a parallel-executor "
            "timeout rather than a hung step."
        ),
    )
