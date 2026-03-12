"""
LLM configuration module.

Contains settings for:
- LLM Provider API Keys (OpenAI, Anthropic, DeepSeek, Perplexity, Ollama)
- Provider Capabilities (structured output, JSON mode)
- Router LLM Configuration
- Response LLM Configuration
- Contacts Agent LLM Configuration
- Gmail Agent LLM Configuration
- Domain Filtering Configuration

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# =============================================================================
# MODEL CONTEXT WINDOWS (tokens)
# =============================================================================
# Centralized mapping of model names to their maximum context window sizes.
# Used by middleware to calculate dynamic summarization triggers.
#
# Sources:
# - OpenAI: https://platform.openai.com/docs/models
# - Anthropic: https://docs.anthropic.com/en/docs/about-claude/models
# - Google: https://ai.google.dev/gemini-api/docs/models/gemini
# - DeepSeek: https://platform.deepseek.com/api-docs
#
# Note: Values are conservative estimates. Some models may support more via
# extended context options (e.g., Claude 200k → 1M with prompt caching).
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # IMPORTANT: More specific prefixes MUST come before shorter ones
    # because get_model_context_window() uses startswith() fallback.
    # e.g., "o1-mini" before "o1", "gpt-4-turbo" before "gpt-4".
    #
    # OpenAI GPT-5.x series (2025-2026) — all 1M, order doesn't matter
    "gpt-5-mini": 1_047_576,
    "gpt-5-nano": 1_047_576,
    "gpt-5.1": 1_047_576,
    "gpt-5.2": 1_047_576,
    "gpt-5": 1_047_576,
    # OpenAI GPT-4.1 series (2025) — all 1M, order doesn't matter
    "gpt-4.1-mini": 1_047_576,
    "gpt-4.1-nano": 1_047_576,
    "gpt-4.1": 1_047_576,
    # OpenAI GPT-4o series — same value, but more specific first for safety
    "gpt-4o-mini": 128_000,
    "gpt-4o": 128_000,
    # OpenAI GPT-4 series — DIFFERENT values, order matters!
    "gpt-4-turbo-preview": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    # OpenAI GPT-3.5 series
    "gpt-3.5-turbo-16k": 16_385,
    "gpt-3.5-turbo": 16_385,
    # OpenAI o-series reasoning models — o1-mini (128K) before o1 (200K)!
    "o1-mini": 128_000,
    "o1": 200_000,
    "o3-mini": 200_000,
    "o3": 200_000,
    "o4-mini": 200_000,
    # Anthropic Claude 4.x series
    "claude-opus-4-6": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-opus-4": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-haiku-4-5": 200_000,
    # Anthropic Claude 3.x series
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
    # Google Gemini series
    "gemini-3.1-pro-preview": 1_000_000,
    "gemini-3-pro-preview": 1_000_000,
    "gemini-3-flash-preview": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-flash-lite": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.0-flash-lite": 1_000_000,
    "gemini-1.5-pro": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    # DeepSeek series
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    "deepseek-coder": 128_000,
    # Perplexity series
    "llama-3.1-sonar-small-128k-online": 128_000,
    "llama-3.1-sonar-large-128k-online": 128_000,
    "llama-3.1-sonar-huge-128k-online": 128_000,
}

# Default context window for unknown models
DEFAULT_CONTEXT_WINDOW: int = 128_000


def get_model_context_window(model_name: str) -> int:
    """
    Get the context window size for a model.

    Args:
        model_name: Model identifier (e.g., "gpt-4.1-mini", "claude-3-5-sonnet-20241022")

    Returns:
        Context window size in tokens. Falls back to DEFAULT_CONTEXT_WINDOW for unknown models.

    Example:
        >>> get_model_context_window("gpt-4.1-mini")
        1047576
        >>> get_model_context_window("claude-3-5-sonnet-20241022")
        200000
        >>> get_model_context_window("unknown-model")
        128000  # default fallback
    """
    # Direct match
    if model_name in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model_name]

    # Try prefix matching for versioned models (e.g., "gpt-4.1-mini-2025-01" → "gpt-4.1-mini")
    for known_model, context_window in MODEL_CONTEXT_WINDOWS.items():
        if model_name.startswith(known_model):
            return context_window

    return DEFAULT_CONTEXT_WINDOW


class LLMSettings(BaseSettings):
    """LLM provider and configuration settings."""

    # ========================================================================
    # LLM PROVIDERS CONFIGURATION
    # ========================================================================

    # OpenAI Organization ID (not a secret — stays in .env)
    openai_organization_id: str = Field(
        default="",
        description="OpenAI Organization ID (optional, required for GPT-5 streaming with verified org)",
    )

    # NOTE: LLM provider API keys (OpenAI, Anthropic, DeepSeek, Perplexity, Gemini, Ollama)
    # are stored encrypted in the database and managed via Admin UI.
    # See: Settings > Administration > LLM Configuration

    # OpenWeatherMap (Weather API)
    openweathermap_api_key: str = Field(
        default="",
        description="OpenWeatherMap API key for weather data (get from https://home.openweathermap.org/api_keys)",
    )

    # Google API Key (Generic - used for Places photos, Drive thumbnails, etc.)
    google_api_key: str = Field(
        default="",
        description="Generic Google API key for Places photos and Drive thumbnails (get from https://console.cloud.google.com/apis/credentials)",
    )

    # Google Places (Places API New) - deprecated, use google_api_key instead
    google_places_api_key: str = Field(
        default="",
        description="Google Places API key for location search (deprecated, use GOOGLE_API_KEY instead)",
    )

    # ========================================================================
    # LLM PROVIDER CAPABILITIES (LangChain v1.0 Best Practice 2025)
    # ========================================================================
    # Explicitly declare provider capabilities to avoid runtime detection complexity.
    # This ensures predictable behavior and easier maintenance.
    #
    # Structured Output Support:
    # - OpenAI: Native /v1/chat/completions/parse endpoint (Pydantic schemas)
    # - Anthropic: Native structured output via SDK
    # - DeepSeek: Supports Pydantic-based structured output
    # - Ollama: OpenAI-compatible API but NO /parse endpoint (use JSON mode fallback)
    # - Perplexity: OpenAI-compatible API but NO /parse endpoint (use JSON mode fallback)
    #
    # JSON Mode Support:
    # - All providers support response_format={"type": "json_object"}
    # - This is the fallback for providers without native structured output
    #
    # Best Practice: When adding new providers, explicitly declare capabilities here.

    @property
    def provider_supports_structured_output(self) -> dict[str, bool]:
        """
        Provider capabilities for native structured output (Pydantic parsing).

        Returns:
            Dict mapping provider name to structured output support status.
            True = Native /parse endpoint (optimal)
            False = Use JSON mode fallback (compatible)
        """
        return {
            "openai": True,  # Native /parse with Pydantic schemas
            "anthropic": True,  # Native structured output
            "deepseek": True,  # Supports Pydantic schemas
            "ollama": False,  # OpenAI-compatible but no /parse
            "perplexity": False,  # OpenAI-compatible but no /parse
            "gemini": True,  # Native structured output via langchain-google-genai
        }

    # ========================================================================
    # LLM CONFIGURATION - ROUTER
    # ========================================================================

    router_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for router")
    router_llm_provider_config: str = Field(
        default="{}", description="Advanced provider-specific config for router (JSON string)"
    )
    router_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for router node",
    )
    router_llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for router LLM (0.0 for deterministic routing)",
    )
    router_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling for router LLM (1.0 = disabled, use temperature)",
    )
    router_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for router LLM (0.0 = no penalty)",
    )
    router_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for router LLM (0.0 = no penalty)",
    )
    router_llm_max_tokens: int = Field(
        default=300,
        gt=0,
        description="Max tokens for router LLM output",
    )
    router_llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = Field(
        default=None,
        description=(
            "Reasoning effort for router LLM (OpenAI o-series/GPT-5 only). "
            "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
            "Recommended: 'minimal' for router (fast routing decisions, deterministic)."
        ),
    )

    # NOTE: Legacy thresholds removed (2025-12-30) - Architecture v3
    # router_confidence_threshold, domain_filtering_*, semantic_router_bypass_*
    # All threshold logic now handled by QueryAnalyzerService in agents.py
    # See: V3_ROUTING_MIN_CONFIDENCE, V3_ROUTING_CHAT_SEMANTIC_THRESHOLD, etc.

    # ========================================================================
    # LLM CONFIGURATION - RESPONSE
    # ========================================================================

    response_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for response")
    response_llm_provider_config: str = Field(
        default="{}", description="Advanced provider-specific config for response (JSON string)"
    )
    response_llm_model: str = Field(
        default="gpt-4.1-mini",
        description="LLM model for response node",
    )
    response_llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for response LLM (0.0 for deterministic responses)",
    )
    response_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling for response LLM (1.0 = disabled, use temperature)",
    )
    response_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for response LLM (0.0 = no penalty)",
    )
    response_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for response LLM (0.0 = no penalty)",
    )
    response_llm_max_tokens: int = Field(
        default=8000,
        gt=0,
        description="Max tokens for response LLM output",
    )
    response_llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = (
        Field(
            default=None,
            description=(
                "Reasoning effort for response LLM (OpenAI o-series/GPT-5 only). "
                "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
                "Recommended: 'low' for response (creative synthesis with minimal reasoning)."
            ),
        )
    )

    # ========================================================================
    # LLM CONFIGURATION - CONTACTS AGENT
    # ========================================================================

    contacts_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for contacts agent")
    contacts_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for contacts agent (JSON string)",
    )
    contacts_agent_llm_model: str = Field(
        default="",
        description="Deprecated: use LLM_DEFAULTS. LLM model for contacts agent.",
    )
    contacts_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for contacts agent (0.3 for precise tool usage)",
    )
    contacts_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for contacts agent (nucleus sampling)",
    )
    contacts_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for contacts agent (reduce repetition)",
    )
    contacts_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for contacts agent (encourage new topics)",
    )
    contacts_agent_llm_max_tokens: int = Field(
        default=2000,
        gt=0,
        description="Max tokens for contacts agent (sufficient for tool calls + reasoning)",
    )
    contacts_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for contacts agent LLM (OpenAI o-series/GPT-5 only). "
            "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
            "Recommended: 'low' for contacts agent (ReAct tool usage with light reasoning)."
        ),
    )

    # ========================================================================
    # LLM CONFIGURATION - GMAIL AGENT
    # ========================================================================

    emails_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Emails agent")
    emails_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Emails agent (JSON string)",
    )
    emails_agent_llm_model: str = Field(
        default="",
        description="Deprecated: use LLM_DEFAULTS. LLM model for Emails agent.",
    )
    emails_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Emails agent (0.3 for precise tool usage)",
    )
    emails_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Emails agent (nucleus sampling)",
    )
    emails_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Emails agent (reduce repetition)",
    )
    emails_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Emails agent (encourage new topics)",
    )
    emails_agent_llm_max_tokens: int = Field(
        default=2000,
        gt=0,
        description="Max tokens for Emails agent (sufficient for tool calls + reasoning)",
    )
    emails_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for Emails agent LLM (OpenAI o-series/GPT-5 only). "
            "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
            "Recommended: 'low' for Emails agent (ReAct tool usage with light reasoning)."
        ),
    )

    # ========================================================================
    # LLM CONFIGURATION - CALENDAR AGENT
    # ========================================================================

    calendar_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Calendar agent")
    calendar_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Calendar agent (JSON string)",
    )
    calendar_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Calendar agent node (ReAct pattern)",
    )
    calendar_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Calendar agent (0.3 for precise scheduling)",
    )
    calendar_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Calendar agent (nucleus sampling)",
    )
    calendar_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Calendar agent",
    )
    calendar_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Calendar agent",
    )
    calendar_agent_llm_max_tokens: int = Field(
        default=2000,
        gt=0,
        description="Max tokens for Calendar agent (sufficient for tool calls + reasoning)",
    )
    calendar_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for Calendar agent LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - DRIVE AGENT
    # ========================================================================

    drive_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Drive agent")
    drive_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Drive agent (JSON string)",
    )
    drive_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Drive agent node (ReAct pattern)",
    )
    drive_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Drive agent (0.3 for precise file search)",
    )
    drive_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Drive agent (nucleus sampling)",
    )
    drive_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Drive agent",
    )
    drive_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Drive agent",
    )
    drive_agent_llm_max_tokens: int = Field(
        default=2000,
        gt=0,
        description="Max tokens for Drive agent (sufficient for tool calls + reasoning)",
    )
    drive_agent_llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = (
        Field(
            default=None,
            description="Reasoning effort for Drive agent LLM (OpenAI o-series/GPT-5 only).",
        )
    )

    # ========================================================================
    # LLM CONFIGURATION - TASKS AGENT
    # ========================================================================

    tasks_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Tasks agent")
    tasks_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Tasks agent (JSON string)",
    )
    tasks_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Tasks agent node (ReAct pattern)",
    )
    tasks_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Tasks agent (0.3 for precise task management)",
    )
    tasks_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Tasks agent (nucleus sampling)",
    )
    tasks_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Tasks agent",
    )
    tasks_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Tasks agent",
    )
    tasks_agent_llm_max_tokens: int = Field(
        default=2000,
        gt=0,
        description="Max tokens for Tasks agent (sufficient for tool calls + reasoning)",
    )
    tasks_agent_llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = (
        Field(
            default=None,
            description="Reasoning effort for Tasks agent LLM (OpenAI o-series/GPT-5 only).",
        )
    )

    # ========================================================================
    # LLM CONFIGURATION - WEATHER AGENT
    # ========================================================================

    weather_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Weather agent")
    weather_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Weather agent (JSON string)",
    )
    weather_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Weather agent node (ReAct pattern)",
    )
    weather_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Weather agent (0.3 for precise weather info)",
    )
    weather_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Weather agent (nucleus sampling)",
    )
    weather_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Weather agent",
    )
    weather_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Weather agent",
    )
    weather_agent_llm_max_tokens: int = Field(
        default=1000,
        gt=0,
        description="Max tokens for Weather agent (sufficient for tool calls + reasoning)",
    )
    weather_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for Weather agent LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - WIKIPEDIA AGENT
    # ========================================================================

    wikipedia_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Wikipedia agent")
    wikipedia_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Wikipedia agent (JSON string)",
    )
    wikipedia_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Wikipedia agent node (ReAct pattern)",
    )
    wikipedia_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Wikipedia agent (0.3 for accurate knowledge)",
    )
    wikipedia_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Wikipedia agent (nucleus sampling)",
    )
    wikipedia_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Wikipedia agent",
    )
    wikipedia_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Wikipedia agent",
    )
    wikipedia_agent_llm_max_tokens: int = Field(
        default=2000,
        gt=0,
        description="Max tokens for Wikipedia agent (sufficient for tool calls + reasoning)",
    )
    wikipedia_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for Wikipedia agent LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - PERPLEXITY AGENT (Internet Search)
    # ========================================================================

    perplexity_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Perplexity agent")
    perplexity_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Perplexity agent (JSON string)",
    )
    perplexity_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Perplexity agent node (ReAct pattern)",
    )
    perplexity_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Perplexity agent (0.3 for accurate search)",
    )
    perplexity_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Perplexity agent (nucleus sampling)",
    )
    perplexity_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Perplexity agent",
    )
    perplexity_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Perplexity agent",
    )
    perplexity_agent_llm_max_tokens: int = Field(
        default=3000,
        gt=0,
        description="Max tokens for Perplexity agent (sufficient for tool calls + reasoning)",
    )
    perplexity_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for Perplexity agent LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - BRAVE AGENT (Brave Search)
    # ========================================================================

    brave_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Brave Search agent")
    brave_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Brave agent (JSON string)",
    )
    brave_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Brave agent node (ReAct pattern)",
    )
    brave_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Brave agent (0.3 for accurate search)",
    )
    brave_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Brave agent (nucleus sampling)",
    )
    brave_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Brave agent",
    )
    brave_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Brave agent",
    )
    brave_agent_llm_max_tokens: int = Field(
        default=3000,
        gt=0,
        description="Max tokens for Brave agent (sufficient for tool calls + reasoning)",
    )
    brave_agent_llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = (
        Field(
            default=None,
            description="Reasoning effort for Brave agent LLM (OpenAI o-series/GPT-5 only).",
        )
    )

    # ========================================================================
    # LLM CONFIGURATION - WEB SEARCH AGENT (Unified Triple Source Search)
    # ========================================================================

    web_search_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Web Search agent")
    web_search_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Web Search agent (JSON string)",
    )
    web_search_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Web Search agent node (orchestrates triple source)",
    )
    web_search_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Web Search agent (0.3 for accurate synthesis)",
    )
    web_search_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Web Search agent (nucleus sampling)",
    )
    web_search_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Web Search agent",
    )
    web_search_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Web Search agent",
    )
    web_search_agent_llm_max_tokens: int = Field(
        default=4000,
        gt=0,
        description="Max tokens for Web Search agent (sufficient for triple source results)",
    )
    web_search_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for Web Search agent LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - WEB FETCH AGENT (Web Page Content Extraction)
    # ========================================================================

    web_fetch_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Web Fetch agent")
    web_fetch_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Web Fetch agent (JSON string)",
    )
    web_fetch_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Web Fetch agent node (URL content extraction)",
    )
    web_fetch_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Web Fetch agent (0.3 for accurate extraction)",
    )
    web_fetch_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Web Fetch agent (nucleus sampling)",
    )
    web_fetch_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Web Fetch agent",
    )
    web_fetch_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Web Fetch agent",
    )
    web_fetch_agent_llm_max_tokens: int = Field(
        default=3000,
        gt=0,
        description="Max tokens for Web Fetch agent (sufficient for tool calls + summary)",
    )
    web_fetch_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for Web Fetch agent LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - PLACES AGENT (Google Places)
    # ========================================================================

    places_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Places agent")
    places_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Places agent (JSON string)",
    )
    places_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Places agent node (ReAct pattern)",
    )
    places_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Places agent (0.3 for precise location search)",
    )
    places_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Places agent (nucleus sampling)",
    )
    places_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Places agent",
    )
    places_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Places agent",
    )
    places_agent_llm_max_tokens: int = Field(
        default=2000,
        gt=0,
        description="Max tokens for Places agent (sufficient for tool calls + reasoning)",
    )
    places_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for Places agent LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - ROUTES AGENT (Google Routes Directions)
    # ========================================================================

    routes_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Routes agent")
    routes_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Routes agent (JSON string)",
    )
    routes_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Routes agent node (ReAct pattern)",
    )
    routes_agent_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for Routes agent (0.3 for precise route calculation)",
    )
    routes_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Routes agent (nucleus sampling)",
    )
    routes_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Routes agent",
    )
    routes_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Routes agent",
    )
    routes_agent_llm_max_tokens: int = Field(
        default=2000,
        gt=0,
        description="Max tokens for Routes agent (sufficient for tool calls + reasoning)",
    )
    routes_agent_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for Routes agent LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - QUERY AGENT (LocalQueryEngine / INTELLIA)
    # ========================================================================

    query_agent_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(default="openai", description="LLM provider for Query agent")
    query_agent_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for Query agent (JSON string)",
    )
    query_agent_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for Query agent node (data analysis on Registry)",
    )
    query_agent_llm_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Temperature for Query agent (low for precise data analysis)",
    )
    query_agent_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for Query agent (nucleus sampling)",
    )
    query_agent_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for Query agent",
    )
    query_agent_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for Query agent",
    )
    query_agent_llm_max_tokens: int = Field(
        default=5000,
        gt=0,
        description="Max tokens for Query agent (sufficient for analysis + results)",
    )
    query_agent_llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = (
        Field(
            default=None,
            description="Reasoning effort for Query agent LLM (OpenAI o-series/GPT-5 only).",
        )
    )

    # ========================================================================
    # LLM CONFIGURATION - SEMANTIC VALIDATOR (Phase 2 OPTIMPLAN)
    # ========================================================================
    # Semantic validation uses a DISTINCT LLM from planner to avoid self-validation bias
    # Best Practice: Use fast, inexpensive model (GPT-4.1-mini) for validation
    # Performance Target: P95 < 2s, with 1s timeout for optimistic validation

    semantic_validator_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for semantic validator (distinct from planner)",
    )
    semantic_validator_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for semantic validator (JSON string)",
    )
    semantic_validator_llm_model: str = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model for semantic validation (fast model recommended). "
            "Default: gpt-4.1-mini for speed + quality balance. "
            "Alternatives: gpt-4.1-nano (ultra-fast), gpt-4.1-mini-mini (higher quality)."
        ),
    )
    semantic_validator_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for semantic validator (0.3 for validation)",
    )
    semantic_validator_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for semantic validator (nucleus sampling)",
    )
    semantic_validator_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for semantic validator",
    )
    semantic_validator_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for semantic validator",
    )
    semantic_validator_llm_max_tokens: int = Field(
        default=1000,
        gt=0,
        description=(
            "Max tokens for semantic validator output. "
            "Should be sufficient for validation result (issues + clarification questions). "
            "Default: 1000 (structured output is compact)."
        ),
    )
    semantic_validator_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for semantic validator LLM (OpenAI o-series/GPT-5 only). "
            "Controls reasoning depth: minimal=sub-second (GPT-5), low=1-3s, medium=5-15s, high=30+s. "
            "Recommended: 'minimal' or None for semantic validator (fast validation)."
        ),
    )

    # ========================================================================
    # LLM CONFIGURATION - CONTEXT RESOLVER (LLM-Native Semantic Architecture - Phase 0)
    # ========================================================================
    # Fast LLM for resolving context: temporal references, coreferences, memory injection
    # Uses a fast model (gpt-4.1-mini) for low latency (<500ms target)

    context_resolver_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for context resolver (fast model required)",
    )
    context_resolver_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for context resolver (JSON string)",
    )
    context_resolver_llm_model: str = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model for context resolution (fast model required). "
            "Default: gpt-4.1-mini for speed. Target latency: <500ms."
        ),
    )
    context_resolver_llm_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Temperature for context resolver (low for deterministic resolution)",
    )
    context_resolver_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for context resolver (nucleus sampling)",
    )
    context_resolver_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for context resolver",
    )
    context_resolver_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for context resolver",
    )
    context_resolver_llm_max_tokens: int = Field(
        default=1000,
        gt=0,
        description=(
            "Max tokens for context resolver output. "
            "Sufficient for resolved query + resolutions list. "
            "Default: 1000 (structured output is compact)."
        ),
    )
    context_resolver_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for context resolver LLM (OpenAI o-series/GPT-5 only). "
            "Recommended: None or 'minimal' for speed."
        ),
    )

    # ========================================================================
    # LLM CONFIGURATION - QUERY ANALYZER (Intent + Domain Detection)
    # ========================================================================
    # LLM-based query analysis replacing embeddings-based SemanticDomainSelector.
    # Responsibilities:
    # - Detect user intent (action vs conversation)
    # - Select primary and secondary domains
    # - Resolve context references (memory, conversation history)
    # - Semantic type expansion
    # Performance Target: P95 < 800ms (fast model recommended)

    query_analyzer_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for query analyzer (fast model required)",
    )
    query_analyzer_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for query analyzer (JSON string)",
    )
    query_analyzer_llm_model: str = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model for query analysis (fast model required). "
            "Replaces embeddings-based domain selection with LLM intelligence. "
            "Default: gpt-4.1-mini for speed + quality balance. "
            "Target latency: <800ms."
        ),
    )
    query_analyzer_llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Temperature for query analyzer (0.0 for deterministic analysis)",
    )
    query_analyzer_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for query analyzer (nucleus sampling)",
    )
    query_analyzer_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for query analyzer",
    )
    query_analyzer_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for query analyzer",
    )
    query_analyzer_llm_max_tokens: int = Field(
        default=500,
        gt=0,
        description=(
            "Max tokens for query analyzer output. "
            "Structured output is compact (intent + domains + reasoning). "
            "Default: 500 tokens."
        ),
    )
    query_analyzer_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description=(
            "Reasoning effort for query analyzer LLM (OpenAI o-series/GPT-5 only). "
            "Recommended: None or 'minimal' for speed."
        ),
    )

    # ========================================================================
    # LLM CONFIGURATION - INTEREST EXTRACTION (Proactive Learning)
    # ========================================================================
    # Fire-and-forget interest extraction from conversations.
    # Pattern: Same as memory_extractor.py (background LLM analysis).
    # Performance Target: P95 < 2s (non-blocking, async)

    interest_extraction_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for interest extraction (fast model recommended)",
    )
    interest_extraction_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for interest extraction (JSON string)",
    )
    interest_extraction_llm_model: str = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model for interest extraction. "
            "Extracts 0-2 interests per conversation turn. "
            "Default: gpt-4.1-mini for quality + speed balance."
        ),
    )
    interest_extraction_llm_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Temperature for interest extraction (low for consistency)",
    )
    interest_extraction_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for interest extraction (nucleus sampling)",
    )
    interest_extraction_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for interest extraction",
    )
    interest_extraction_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for interest extraction",
    )
    interest_extraction_llm_max_tokens: int = Field(
        default=500,
        gt=0,
        description="Max tokens for interest extraction output (JSON array of 0-2 interests)",
    )
    interest_extraction_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for interest extraction LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # LLM CONFIGURATION - INTEREST CONTENT PRESENTATION (Proactive Notifications)
    # ========================================================================
    # Generates engaging content for proactive interest notifications.
    # Pattern: Conversational presentation of Wikipedia/Perplexity/LLM content.
    # Performance Target: P95 < 3s (user-facing quality)

    interest_content_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for interest content presentation",
    )
    interest_content_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for interest content (JSON string)",
    )
    interest_content_llm_model: str = Field(
        default="gpt-4.1-mini",
        description=(
            "LLM model for interest content presentation. "
            "Generates conversational notification content. "
            "Default: gpt-4.1-mini for natural language quality."
        ),
    )
    interest_content_llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperature for content presentation (higher for creativity)",
    )
    interest_content_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Top-p for content presentation (nucleus sampling)",
    )
    interest_content_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for content presentation",
    )
    interest_content_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for content presentation",
    )
    interest_content_llm_max_tokens: int = Field(
        default=1000,
        gt=0,
        description="Max tokens for content presentation (conversational notification)",
    )
    interest_content_llm_reasoning_effort: (
        Literal["none", "minimal", "low", "medium", "high"] | None
    ) = Field(
        default=None,
        description="Reasoning effort for content presentation LLM (OpenAI o-series/GPT-5 only).",
    )

    # ========================================================================
    # VALIDATORS - Empty String to None Conversion
    # ========================================================================
    # Pydantic-settings reads env vars as strings. Empty strings ("") are NOT
    # automatically converted to None for Optional fields with Literal types.
    # This validator ensures empty strings in .env are treated as None.

    @field_validator(
        "router_llm_reasoning_effort",
        "response_llm_reasoning_effort",
        "contacts_agent_llm_reasoning_effort",
        "emails_agent_llm_reasoning_effort",
        "calendar_agent_llm_reasoning_effort",
        "drive_agent_llm_reasoning_effort",
        "tasks_agent_llm_reasoning_effort",
        "weather_agent_llm_reasoning_effort",
        "wikipedia_agent_llm_reasoning_effort",
        "perplexity_agent_llm_reasoning_effort",
        "places_agent_llm_reasoning_effort",
        "routes_agent_llm_reasoning_effort",
        "query_agent_llm_reasoning_effort",
        "semantic_validator_llm_reasoning_effort",
        "context_resolver_llm_reasoning_effort",
        "query_analyzer_llm_reasoning_effort",
        "interest_extraction_llm_reasoning_effort",
        "interest_content_llm_reasoning_effort",
        "brave_agent_llm_reasoning_effort",
        "web_search_agent_llm_reasoning_effort",
        "web_fetch_agent_llm_reasoning_effort",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Any:
        """
        Convert empty strings to None for reasoning_effort fields.

        Environment variables with empty values (VAR=) are read as "" (empty string).
        Since reasoning_effort accepts Literal[...] | None, we convert "" to None.

        This is a common pattern for optional enum/literal fields in pydantic-settings.

        Args:
            v: Raw value from environment or settings

        Returns:
            None if empty string, otherwise original value
        """
        if v == "" or v is None:
            return None
        return v
