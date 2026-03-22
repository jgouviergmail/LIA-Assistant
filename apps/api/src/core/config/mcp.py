"""
MCP (Model Context Protocol) configuration module.

Contains settings for:
- MCP feature toggle (enabled/disabled)
- Server configuration (inline JSON or file path)
- Tool execution limits (timeout, max servers, max tools per server)
- Security settings (HITL requirement, rate limiting)
- Connection resilience (retry, health check interval)

Phase: evolution F2 — MCP Support
Created: 2026-02-28
Reference: docs/technical/MCP_INTEGRATION.md
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    MCP_APP_MAX_HTML_SIZE_DEFAULT,
    MCP_CONNECTION_RETRY_MAX_DEFAULT,
    MCP_DEFAULT_RATE_LIMIT_CALLS,
    MCP_DEFAULT_RATE_LIMIT_WINDOW,
    MCP_DEFAULT_TIMEOUT_SECONDS,
    MCP_DESCRIPTION_LLM_FREQUENCY_PENALTY_DEFAULT,
    MCP_DESCRIPTION_LLM_MAX_TOKENS_DEFAULT,
    MCP_DESCRIPTION_LLM_MODEL_DEFAULT,
    MCP_DESCRIPTION_LLM_PRESENCE_PENALTY_DEFAULT,
    MCP_DESCRIPTION_LLM_PROVIDER_CONFIG_DEFAULT,
    MCP_DESCRIPTION_LLM_TEMPERATURE_DEFAULT,
    MCP_DESCRIPTION_LLM_TOP_P_DEFAULT,
    MCP_EXCALIDRAW_LLM_FREQUENCY_PENALTY_DEFAULT,
    MCP_EXCALIDRAW_LLM_MAX_TOKENS_DEFAULT,
    MCP_EXCALIDRAW_LLM_MODEL_DEFAULT,
    MCP_EXCALIDRAW_LLM_PRESENCE_PENALTY_DEFAULT,
    MCP_EXCALIDRAW_LLM_PROVIDER_CONFIG_DEFAULT,
    MCP_EXCALIDRAW_LLM_TEMPERATURE_DEFAULT,
    MCP_EXCALIDRAW_LLM_TOP_P_DEFAULT,
    MCP_EXCALIDRAW_STEP_TIMEOUT_SECONDS_DEFAULT,
    MCP_HEALTH_CHECK_INTERVAL_DEFAULT,
    MCP_MAX_SERVERS_DEFAULT,
    MCP_MAX_STRUCTURED_ITEMS_PER_CALL,
    MCP_MAX_TOOLS_PER_SERVER_DEFAULT,
    MCP_REFERENCE_CONTENT_MAX_CHARS_DEFAULT,
    MCP_USER_MAX_SERVERS_PER_USER_DEFAULT,
    MCP_USER_POOL_EVICTION_INTERVAL_DEFAULT,
    MCP_USER_POOL_MAX_TOTAL_DEFAULT,
    MCP_USER_POOL_TTL_SECONDS_DEFAULT,
)


class MCPSettings(BaseSettings):
    """MCP (Model Context Protocol) settings for external tool servers."""

    # ========================================================================
    # Feature Toggle
    # ========================================================================

    mcp_enabled: bool = Field(
        default=False,
        description=(
            "Enable MCP support. When true, connects to configured MCP servers "
            "at startup and registers discovered tools in the catalogue."
        ),
    )

    # ========================================================================
    # Server Configuration
    # ========================================================================

    mcp_servers_config: str = Field(
        default=MCP_EXCALIDRAW_LLM_PROVIDER_CONFIG_DEFAULT,
        description=(
            "JSON string defining MCP servers. "
            'Format: {"name": {"transport": "stdio"|"streamable_http", '
            '"command": "...", "args": [...], "url": "...", '
            '"env": {...}, "timeout_seconds": 30, "enabled": true, '
            '"hitl_required": null}}'
        ),
    )

    mcp_servers_config_path: str | None = Field(
        default=None,
        description=(
            "Path to JSON file containing MCP server configuration. "
            "Overrides MCP_SERVERS_CONFIG if set."
        ),
    )

    # ========================================================================
    # Validator — JSON syntax fail-fast
    # ========================================================================

    @field_validator("mcp_servers_config", mode="before")
    @classmethod
    def validate_json_syntax(cls, v: Any) -> str:
        """
        Validate JSON syntax at settings load time (fail-fast).

        Prevents late failures during MCP initialization by catching
        malformed JSON in the configuration as early as possible.

        Args:
            v: Raw value from environment or settings

        Returns:
            Validated JSON string

        Raises:
            ValueError: If JSON syntax is invalid
        """
        if not isinstance(v, str):
            return str(v)
        if v and v != "{}":
            try:
                json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"MCP_SERVERS_CONFIG contains invalid JSON: {e}. "
                    f"Check syntax in .env or environment variable."
                ) from e
        return v

    # ========================================================================
    # Tool Execution Limits
    # ========================================================================

    mcp_tool_timeout_seconds: int = Field(
        default=MCP_DEFAULT_TIMEOUT_SECONDS,
        ge=5,
        le=120,
        description="Timeout for individual MCP tool calls (seconds).",
    )

    mcp_max_servers: int = Field(
        default=MCP_MAX_SERVERS_DEFAULT,
        ge=1,
        le=50,
        description="Maximum number of MCP servers that can be configured.",
    )

    mcp_max_tools_per_server: int = Field(
        default=MCP_MAX_TOOLS_PER_SERVER_DEFAULT,
        ge=1,
        le=100,
        description=(
            "Maximum tools to register per MCP server. " "Excess tools are silently ignored."
        ),
    )

    # ========================================================================
    # Security
    # ========================================================================

    mcp_hitl_required: bool = Field(
        default=True,
        description=(
            "Global HITL requirement for MCP tools. "
            "Per-server hitl_required overrides this. "
            "true = all MCP tool calls require user approval."
        ),
    )

    mcp_rate_limit_calls: int = Field(
        default=MCP_DEFAULT_RATE_LIMIT_CALLS,
        ge=1,
        description="Max MCP tool calls per server per rate limit window.",
    )

    mcp_rate_limit_window: int = Field(
        default=MCP_DEFAULT_RATE_LIMIT_WINDOW,
        ge=10,
        description="Rate limit window in seconds for MCP tool calls.",
    )

    mcp_max_structured_items_per_call: int = Field(
        default=MCP_MAX_STRUCTURED_ITEMS_PER_CALL,
        ge=1,
        le=200,
        description=(
            "Maximum structured items to parse from a single MCP tool call. "
            "Prevents registry explosion when MCP tools return large arrays "
            "(e.g., list_commits with 100+ items per page)."
        ),
    )

    # ========================================================================
    # MCP Apps (evolution F2.5)
    # ========================================================================

    mcp_app_max_html_size: int = Field(
        default=MCP_APP_MAX_HTML_SIZE_DEFAULT,
        ge=1024,
        le=10 * 1024 * 1024,
        description=(
            "Maximum HTML size (bytes) from read_resource() for MCP Apps widgets. "
            "Prevents DoS from oversized HTML payloads. Default 2MB."
        ),
    )

    mcp_reference_content_max_chars: int = Field(
        default=MCP_REFERENCE_CONTENT_MAX_CHARS_DEFAULT,
        ge=0,
        le=50000,
        description=(
            "Maximum characters of MCP reference content (read_me) to inject "
            "in the planner prompt. Larger values give better tool parameter "
            "quality but consume more tokens. 0 disables injection."
        ),
    )

    # ========================================================================
    # Connection Resilience
    # ========================================================================

    mcp_health_check_interval_seconds: int = Field(
        default=MCP_HEALTH_CHECK_INTERVAL_DEFAULT,
        ge=60,
        description="Interval between MCP server health checks (seconds).",
    )

    mcp_connection_retry_max: int = Field(
        default=MCP_CONNECTION_RETRY_MAX_DEFAULT,
        ge=0,
        le=10,
        description="Max connection retry attempts per MCP server at startup.",
    )

    # ========================================================================
    # Per-User MCP (evolution F2.1)
    # ========================================================================
    # Each user can declare and manage their own MCP servers via the web UI.
    # Only streamable_http transport is allowed (no stdio for security).
    # Reference: domains/user_mcp/, infrastructure/mcp/user_pool.py

    mcp_user_enabled: bool = Field(
        default=False,
        description=(
            "Enable per-user MCP support. When true, users can declare "
            "their own MCP servers and use discovered tools in chat."
        ),
    )

    mcp_user_max_servers_per_user: int = Field(
        default=MCP_USER_MAX_SERVERS_PER_USER_DEFAULT,
        ge=1,
        le=20,
        description="Maximum MCP servers a single user can configure.",
    )

    mcp_user_pool_ttl_seconds: int = Field(
        default=MCP_USER_POOL_TTL_SECONDS_DEFAULT,
        ge=60,
        description=(
            "Idle TTL for user MCP connections in the pool (seconds). "
            "Connections unused for this duration are evicted."
        ),
    )

    mcp_user_pool_max_total: int = Field(
        default=MCP_USER_POOL_MAX_TOTAL_DEFAULT,
        ge=5,
        description=(
            "Maximum total connections in the user MCP pool across all users. "
            "Oldest idle connections are evicted when limit is reached."
        ),
    )

    mcp_user_pool_eviction_interval: int = Field(
        default=MCP_USER_POOL_EVICTION_INTERVAL_DEFAULT,
        ge=30,
        description="Interval between pool eviction sweeps (seconds).",
    )

    mcp_user_oauth_callback_base_url: str | None = Field(
        default=None,
        description=(
            "Base URL for OAuth 2.1 callbacks (e.g., 'https://app.example.com'). "
            "Required for OAuth-authenticated MCP servers."
        ),
    )

    # ========================================================================
    # Excalidraw Diagram LLM Generation (evolution F2 — Iterative Builder)
    # ========================================================================
    # The builder makes a single LLM call to generate the complete Excalidraw
    # diagram (camera + background + shapes + labels + arrows).
    # The LLM is the creative engine — it decides ALL positions and layout.
    # Uses a dedicated LLM config (can differ from planner for quality/speed).

    mcp_excalidraw_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini", "qwen"
    ] = Field(
        default="anthropic",
        description="LLM provider for Excalidraw diagram generation.",
    )

    mcp_excalidraw_llm_provider_config: str = Field(
        default=MCP_DESCRIPTION_LLM_PROVIDER_CONFIG_DEFAULT,
        description="Advanced provider-specific config for Excalidraw LLM (JSON string).",
    )

    mcp_excalidraw_llm_model: str = Field(
        default=MCP_EXCALIDRAW_LLM_MODEL_DEFAULT,
        description="LLM model for Excalidraw diagram generation.",
    )

    mcp_excalidraw_llm_temperature: float = Field(
        default=MCP_EXCALIDRAW_LLM_TEMPERATURE_DEFAULT,
        ge=0.0,
        le=2.0,
        description="Temperature for Excalidraw LLM (0.3 for balanced creativity/consistency).",
    )

    mcp_excalidraw_llm_top_p: float = Field(
        default=MCP_EXCALIDRAW_LLM_TOP_P_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling for Excalidraw LLM (1.0 = disabled).",
    )

    mcp_excalidraw_llm_frequency_penalty: float = Field(
        default=MCP_EXCALIDRAW_LLM_FREQUENCY_PENALTY_DEFAULT,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Excalidraw LLM (0.0 = no penalty).",
    )

    mcp_excalidraw_llm_presence_penalty: float = Field(
        default=MCP_EXCALIDRAW_LLM_PRESENCE_PENALTY_DEFAULT,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Excalidraw LLM (0.0 = no penalty).",
    )

    mcp_excalidraw_llm_max_tokens: int = Field(
        default=MCP_EXCALIDRAW_LLM_MAX_TOKENS_DEFAULT,
        gt=0,
        description=(
            "Max tokens for Excalidraw LLM output. "
            "Must be large enough for 15+ shapes + arrows with full coordinates."
        ),
    )

    mcp_excalidraw_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default="low",
        description=(
            "Reasoning effort for Excalidraw LLM. " "'low' for balanced diagram generation quality."
        ),
    )

    mcp_excalidraw_step_timeout_seconds: int = Field(
        default=MCP_EXCALIDRAW_STEP_TIMEOUT_SECONDS_DEFAULT,
        ge=30,
        le=300,
        description=(
            "Timeout for the Excalidraw LLM call (seconds). "
            "Single call generates all elements (shapes + arrows)."
        ),
    )

    # ========================================================================
    # Domain Description LLM Generation
    # ========================================================================
    # Uses a cheap/fast model to analyze discovered MCP tools and generate
    # a domain description optimized for LLM-based query routing.
    # Prompt: domains/agents/prompts/v1/mcp_description_prompt.txt

    mcp_description_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini", "qwen"
    ] = Field(
        default="openai",
        description="LLM provider for MCP domain description generation.",
    )

    mcp_description_llm_provider_config: str = Field(
        default=MCP_DESCRIPTION_LLM_PROVIDER_CONFIG_DEFAULT,
        description="Advanced provider-specific config for MCP description LLM (JSON string).",
    )

    mcp_description_llm_model: str = Field(
        default=MCP_DESCRIPTION_LLM_MODEL_DEFAULT,
        description="LLM model for MCP domain description generation (cheap/fast).",
    )

    mcp_description_llm_temperature: float = Field(
        default=MCP_DESCRIPTION_LLM_TEMPERATURE_DEFAULT,
        ge=0.0,
        le=2.0,
        description="Temperature for MCP description LLM (low for consistent results).",
    )

    mcp_description_llm_top_p: float = Field(
        default=MCP_DESCRIPTION_LLM_TOP_P_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling for MCP description LLM (1.0 = disabled).",
    )

    mcp_description_llm_frequency_penalty: float = Field(
        default=MCP_DESCRIPTION_LLM_FREQUENCY_PENALTY_DEFAULT,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for MCP description LLM (0.0 = no penalty).",
    )

    mcp_description_llm_presence_penalty: float = Field(
        default=MCP_DESCRIPTION_LLM_PRESENCE_PENALTY_DEFAULT,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for MCP description LLM (0.0 = no penalty).",
    )

    mcp_description_llm_max_tokens: int = Field(
        default=MCP_DESCRIPTION_LLM_MAX_TOKENS_DEFAULT,
        gt=0,
        description="Max tokens for MCP description LLM output.",
    )

    mcp_description_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for MCP description LLM (OpenAI o-series/GPT-5 only). "
            "None = not applicable for non-reasoning models."
        ),
    )
