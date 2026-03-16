"""
Advanced configuration module.

Contains settings for:
- LLM Pricing & Cost Tracking
- Currency Exchange Rates API
- Internationalization (i18n)
- Tool Context Management
- Formatting Display Limits
- Redis Advanced Configuration
- Cache TTL Configuration
- Agent Streaming Configuration
- Token Encoding Configuration
- Feature Flags
- Dynamic Prompt Configuration
- Agent Limits & Constraints

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    DEFAULT_USD_EUR_RATE,
    EXTERNAL_CONTENT_WRAPPING_ENABLED_DEFAULT,
    LLM_PRICING_CACHE_TTL_DEFAULT,
    SUPPORTED_LANGUAGES,
    TOOL_CONTEXT_CONFIDENCE_THRESHOLD,
    TOOL_CONTEXT_DETAILS_MAX_ITEMS,
    TOOL_CONTEXT_MAX_ITEMS,
    WEB_FETCH_CACHE_PREFIX,
    WEB_FETCH_CACHE_TTL_DEFAULT,
    WEB_SEARCH_CACHE_ENABLED_DEFAULT,
    WEB_SEARCH_CACHE_PREFIX,
    WEB_SEARCH_CACHE_TTL_DEFAULT,
)


class SupportedCurrency:
    """Enum placeholder for supported currencies (will be in __init__.py)."""

    USD = "USD"
    EUR = "EUR"


class AdvancedSettings(BaseSettings):
    """Advanced configuration settings for specialized features."""

    # ========================================================================
    # LLM Pricing & Cost Tracking
    # ========================================================================
    llm_pricing_cache_ttl_seconds: int = Field(
        default=LLM_PRICING_CACHE_TTL_DEFAULT,
        gt=0,
        description="LLM pricing cache TTL in seconds (default: 1 hour)",
    )

    default_usd_eur_rate: float = Field(
        default=DEFAULT_USD_EUR_RATE,
        gt=0.0,
        description="Fallback USD/EUR exchange rate when DB/API unavailable",
    )

    # Note: default_currency moved to __init__.py as it depends on SupportedCurrency enum

    # ========================================================================
    # Currency Exchange Rates API
    # ========================================================================
    currency_api_url: str = Field(
        default="https://api.frankfurter.app",
        description="Currency exchange rates API base URL (default: frankfurter.app - free, ECB source)",
    )
    currency_api_timeout_seconds: float = Field(
        default=5.0,
        gt=0.0,
        description="Timeout for currency exchange rate API requests (seconds)",
    )

    # ========================================================================
    # Internationalization (i18n) - UI messages only (not LLM prompts)
    # ========================================================================
    default_language: str = Field(
        default="fr",
        description="Default language for error messages and API responses (fr/en/es/de/it)",
    )
    supported_languages: str | list[str] = Field(
        default=SUPPORTED_LANGUAGES,
        description="List of supported languages for UI (comma-separated or list)",
    )

    # ========================================================================
    # Tool Context Management
    # ========================================================================
    # NOTE: Tool context is always enabled for contextual references (e.g., "the 2nd contact")

    tool_context_confidence_threshold: float = Field(
        default=TOOL_CONTEXT_CONFIDENCE_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for fuzzy reference resolution (0.0-1.0)",
    )
    tool_context_max_items: int = Field(
        default=TOOL_CONTEXT_MAX_ITEMS,
        gt=0,
        description="Maximum number of items to store per context list",
    )
    tool_context_details_max_items: int = Field(
        default=TOOL_CONTEXT_DETAILS_MAX_ITEMS,
        gt=0,
        description="Maximum number of detailed items to cache per domain (LRU eviction)",
    )

    # ========================================================================
    # Web Search / Fetch Cache
    # ========================================================================
    web_search_cache_enabled: bool = Field(
        default=WEB_SEARCH_CACHE_ENABLED_DEFAULT,
        description=(
            "Enable Redis TTL caching for web search and web fetch tool results. "
            "Reduces external API calls (Brave, Perplexity, Wikipedia) for repeated queries."
        ),
    )
    web_search_cache_ttl_seconds: int = Field(
        default=WEB_SEARCH_CACHE_TTL_DEFAULT,
        ge=0,
        le=3600,
        description="TTL for cached unified web search results (0 = disabled)",
    )
    web_fetch_cache_ttl_seconds: int = Field(
        default=WEB_FETCH_CACHE_TTL_DEFAULT,
        ge=0,
        le=7200,
        description="TTL for cached web fetch (page content) results (0 = disabled)",
    )
    web_search_cache_prefix: str = Field(
        default=WEB_SEARCH_CACHE_PREFIX,
        description="Redis key prefix for web search cache entries",
    )
    web_fetch_cache_prefix: str = Field(
        default=WEB_FETCH_CACHE_PREFIX,
        description="Redis key prefix for web fetch cache entries",
    )

    # ========================================================================
    # External Content Wrapping (prompt injection prevention)
    # ========================================================================
    external_content_wrapping_enabled: bool = Field(
        default=EXTERNAL_CONTENT_WRAPPING_ENABLED_DEFAULT,
        description=(
            "Wrap untrusted external content (web fetch, search results) in safety markers "
            "to prevent prompt injection. Recommended: always enabled in production."
        ),
    )

    # ========================================================================
    # Entity Resolution (Auto-disambiguation)
    # ========================================================================
    entity_resolution_auto_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for automatic entity resolution (0.0-1.0)",
    )
    entity_resolution_max_candidates: int = Field(
        default=5,
        gt=0,
        le=10,
        description="Maximum number of candidates to show in disambiguation questions",
    )
    entity_resolution_enabled: bool = Field(
        default=True,
        description="Enable automatic entity resolution for name mentions",
    )

    # ========================================================================
    # Formatting Display Limits
    # ========================================================================
    format_truncate_subject_length: int = Field(
        default=55,
        ge=0,
        description="Max characters for email subjects in display (0 = no truncation)",
    )

    # ========================================================================
    # Redis Advanced Configuration
    # ========================================================================
    redis_scan_count: int = Field(
        default=100,
        gt=0,
        description="Number of keys to scan per Redis SCAN iteration",
    )

    # ========================================================================
    # Cache TTL Configuration
    # ========================================================================
    currency_cache_ttl_hours: int = Field(
        default=24,
        gt=0,
        description="Cache TTL for currency exchange rates (hours)",
    )
    hitl_pending_data_ttl_seconds: int = Field(
        default=3600,
        gt=0,
        description="Redis TTL for pending HITL tool approval data (seconds, default: 1 hour for response time metrics)",
    )

    # ========================================================================
    # Agent Streaming Configuration
    # ========================================================================
    agent_stream_sleep_interval: float = Field(
        default=0.0,
        ge=0.0,
        le=0.1,
        description=(
            "Sleep interval between streaming chunks (seconds). "
            "0 = no throttling (recommended for production - StreamingResponse handles backpressure). "
            "0.01-0.1 = throttling for debugging/testing only."
        ),
    )

    # ========================================================================
    # Token Encoding Configuration
    # ========================================================================
    token_encoding_name: str = Field(
        default="o200k_base",
        description="Token encoding name for tiktoken (o200k_base for GPT-4 models)",
    )
    token_count_default_model: str = Field(
        default="gpt-4.1-mini",
        description="Default model name for token counting operations",
    )

    # NOTE: use_conversation_repository removed - always use optimized v2 implementation

    # ========================================================================
    # Dynamic Prompt Configuration
    # ========================================================================
    prompt_datetime_format: str = Field(
        default="%Y-%m-%d %H:%M:%S UTC",
        description="Format for datetime in agent prompts (strftime format)",
    )
    prompt_timezone: str = Field(
        default="UTC",
        description="Timezone for datetime in agent prompts (IANA timezone name)",
    )

    # ========================================================================
    # Agent Limits & Constraints
    # ========================================================================
    max_agent_results: int = Field(
        default=10,
        gt=0,
        description="Maximum number of agent results to keep in history",
    )

    # ========================================================================
    # JINJA2 TEMPLATE EVALUATION (Issue #41)
    # ========================================================================
    jinja_max_recursion_depth: int = Field(
        default=10,
        ge=5,
        le=50,
        description=(
            "Maximum recursion depth for Jinja2 template parameter evaluation. "
            "Protects against DoS attacks via deeply nested JSON structures. "
            "Typical plans have 2-3 nesting levels (step → params → values). "
            "Default: 10 (large margin of safety, Python recursion limit is 1000)."
        ),
    )
