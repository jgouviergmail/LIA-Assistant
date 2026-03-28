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
    DEVOPS_DEFAULT_COMMAND_TIMEOUT,
    DEVOPS_DEFAULT_MAX_OUTPUT_CHARS,
    DEVOPS_DEFAULT_SSH_TIMEOUT,
)


class DevOpsSettings(BaseSettings):
    """Settings for DevOps Claude CLI remote server management."""

    devops_enabled: bool = Field(
        default=False,
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
