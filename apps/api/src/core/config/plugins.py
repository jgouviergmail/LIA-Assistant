"""
Agent Plugins configuration module (ADR-225).

Contains settings for:
- Plugins feature toggle (enabled/disabled)
- Plugins filesystem path (per-user plugin roots)
- Per-user quota and package size budgets

Phase: evolution — Agent Plugins (agent-plugins.org open standard)
Reference: docs/architecture/ADR-225-Standard-Agent-Plugins-v1.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    PLUGINS_MAX_FILE_SIZE_KB_DEFAULT,
    PLUGINS_MAX_PER_USER_DEFAULT,
    PLUGINS_USERS_PATH_DEFAULT,
    PLUGINS_ZIP_MAX_DECOMPRESSED_KB_DEFAULT,
    PLUGINS_ZIP_MAX_FILES_DEFAULT,
)


class PluginsSettings(BaseSettings):
    """Agent Plugins settings for agent-plugins.org standard integration."""

    plugins_enabled: bool = Field(
        default=True,
        description=(
            "Enable the Agent Plugins system (agent-plugins.org). When true, "
            "users can install portable plugins bringing skills and "
            "streamable-http MCP servers; the plugins router is mounted."
        ),
    )

    plugins_users_path: str = Field(
        default=PLUGINS_USERS_PATH_DEFAULT,
        description=(
            "Base directory for per-user installed plugin roots "
            "({path}/{user_id}/{plugin_name}/). Kept on disk for inspection "
            "and updates (ADR-225 arbitrage D)."
        ),
    )

    plugins_max_per_user: int = Field(
        default=PLUGINS_MAX_PER_USER_DEFAULT,
        ge=1,
        le=100,
        description="Maximum installed plugins per user.",
    )

    plugins_max_file_size_kb: int = Field(
        default=PLUGINS_MAX_FILE_SIZE_KB_DEFAULT,
        ge=1,
        description="Maximum uploaded plugin package size (KB).",
    )

    plugins_zip_max_decompressed_kb: int = Field(
        default=PLUGINS_ZIP_MAX_DECOMPRESSED_KB_DEFAULT,
        ge=1,
        description=(
            "Zip-bomb guard: maximum total decompressed size (KB) of a " "plugin package."
        ),
    )

    plugins_zip_max_files: int = Field(
        default=PLUGINS_ZIP_MAX_FILES_DEFAULT,
        ge=1,
        description="Zip-bomb guard: maximum member count of a plugin package.",
    )
