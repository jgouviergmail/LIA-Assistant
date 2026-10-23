"""
LLM configuration module.

Contains settings for:
- Embedding resilience and cross-type guardrails
- LLM providers, the LLM instance cache and provider capabilities
- The response, query agent, semantic validator, query analyzer and interest
  LLM slots
- Ollama discovery

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    EMBEDDING_RATE_LIMIT_MAX_CALLS_DEFAULT,
    EMBEDDING_RATE_LIMIT_WAIT_SECONDS_DEFAULT,
    EMBEDDING_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    EMBEDDING_RETRY_BACKOFF_FACTOR_DEFAULT,
    EMBEDDING_RETRY_MAX_ATTEMPTS_DEFAULT,
    OLLAMA_DISCOVERY_RETRY_SECONDS,
    OLLAMA_DISCOVERY_TIMEOUT_SECONDS,
    PRIOR_TURN_THINKING_REPLAY_ENABLED_DEFAULT,
)

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
    # GPT-6: 1 050 000 window minus the 128 000 output it reserves. Read here
    # while the seeded row stays ``declared`` (see the Qwen series below).
    "gpt-6.1-sol": 922_000,
    "gpt-6-astra": 922_000,
    "gpt-6-sol": 922_000,
    "gpt-6-luna": 922_000,
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
    # Anthropic Claude (Models API max_input_tokens, 2026-09-23 — ADR-306). A
    # newer name before the older one it starts with: ``claude-opus-4`` used to
    # hand 200K to Opus 4.7/4.8, and the 4.6 pair carried 200K for a 1M window.
    # Sonnet 4.5: 200K per the context-windows documentation (the Models API
    # reports 1M).
    "claude-fable-5": 1_000_000,
    "claude-mythos-5": 1_000_000,
    "claude-opus-5": 1_000_000,
    "claude-sonnet-5-5": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-opus-4-8": 1_000_000,
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4-6": 1_000_000,
    "claude-opus-4-5": 200_000,
    "claude-opus-4": 200_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-sonnet-4-5": 200_000,
    "claude-sonnet-4": 200_000,
    # Haiku 5.5: the model overview, 2026-10-08 (no Models API read: no spend).
    "claude-haiku-5-5": 1_000_000,
    "claude-haiku-4-5": 200_000,
    # Anthropic Claude 3.x series
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
    # Google Gemini series
    # A seeded model stays ``declared`` on a fresh install, so its window is
    # read HERE (see the Qwen series below).
    # The models the pricing page lists carry their model page's input limit
    # (ai.google.dev/gemini-api/docs/models/<name>, read 2026-09-26).
    "gemini-3.8-flash": 1_048_576,
    "gemini-3.7-flash": 1_048_576,
    "gemini-3.6-flash": 1_048_576,
    "gemini-3.5-flash-lite": 1_048_576,
    "gemini-3.5-flash": 1_048_576,
    "gemini-3.1-flash-lite": 1_048_576,
    "gemini-3.1-pro-preview": 1_048_576,
    "gemini-3-pro-preview": 1_000_000,
    "gemini-3-flash-preview": 1_048_576,
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.5-flash-lite": 1_048_576,
    "gemini-2.0-flash": 1_000_000,
    "gemini-2.0-flash-lite": 1_000_000,
    "gemini-1.5-pro": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    # DeepSeek series — v4 (2026) brought the family up to 1M; v3 stays at 128K.
    # deepseek-flash is the current name (DeepSeek-V4.1-Flash); the v4 names
    # are retired aliases the API still accepts.
    "deepseek-flash": 1_000_000,
    "deepseek-v4-flash": 1_000_000,
    "deepseek-v4-pro": 1_000_000,
    "deepseek-v4-reasoner": 1_000_000,
    "deepseek-v4": 1_000_000,  # matches any "deepseek-v4-…" suffix via startswith fallback
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    "deepseek-coder": 128_000,
    # Perplexity series
    "llama-3.1-sonar-small-128k-online": 128_000,
    "llama-3.1-sonar-large-128k-online": 128_000,
    "llama-3.1-sonar-huge-128k-online": 128_000,
    # Qwen series (more specific prefixes before shorter ones). A model the
    # reference seed inserts stays ``declared``, so on a fresh install its
    # window is read HERE — a Qwen name missing from this table runs at the
    # 128K default against a 1M window.
    "qwen3.8-flash": 1_000_000,
    "qwen3.7-max": 1_000_000,
    "qwen3.7-flash": 1_000_000,
    "qwen3.6-flash": 1_000_000,
    "qwen3.6-plus": 1_000_000,
    "qwen3.5-plus": 1_000_000,
    "qwen3.5-flash": 1_000_000,
    "qwen3-max": 262_144,
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
    # EMBEDDING RESILIENCE (ADR-254)
    # ========================================================================

    embedding_rate_limit_max_calls: int = Field(
        default=EMBEDDING_RATE_LIMIT_MAX_CALLS_DEFAULT,
        ge=0,
        description=(
            "Embedding calls allowed per window, across the whole deployment. "
            "Zero disables the shaper entirely (and costs no Redis round-trip). "
            "The provider quota is per BASE MODEL, so this budget is global, "
            "never per user — raise it together with the provider quota as the "
            "number of users grows."
        ),
    )

    embedding_rate_limit_window_seconds: int = Field(
        default=EMBEDDING_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        gt=0,
        description=(
            "Width of the embedding shaper window. Deliberately SHORT: what "
            "breaks is instantaneous concurrency, and a one-minute window "
            "cannot see six calls fired inside one second."
        ),
    )

    embedding_rate_limit_wait_seconds: float = Field(
        default=EMBEDDING_RATE_LIMIT_WAIT_SECONDS_DEFAULT,
        ge=0,
        description=(
            "How long an embedding may wait for a shaper slot before going "
            "ahead anyway. Bounded on purpose: an interactive turn embeds its "
            "own question, and our own throttle must never be the reason an "
            "answer loses its memory."
        ),
    )

    embedding_retry_max_attempts: int = Field(
        default=EMBEDDING_RETRY_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        description=(
            "Total attempts for one embedding operation, first included. "
            "1 disables retry. Only transient provider failures are retried "
            "(429/500/503/timeouts); a 400 or a bad key fails on the first."
        ),
    )

    embedding_retry_backoff_factor: float = Field(
        default=EMBEDDING_RETRY_BACKOFF_FACTOR_DEFAULT,
        gt=0,
        description="Wait between embedding attempts is backoff_factor ** attempt seconds.",
    )

    # ========================================================================
    # CROSS-TYPE GUARDRAILS
    # ========================================================================

    llm_thinking_max_tokens_floor: int = Field(
        default=4000,
        gt=0,
        description=(
            "Minimum effective max_tokens required to save an LLM-type config "
            "whose reasoning effort consumes the completion budget (DeepSeek V4 "
            "high/max, Qwen thinking toggle, OpenAI medium+, Gemini budgets). "
            "Reasoning tokens are billed inside the completion window: below "
            "this floor the final answer is truncated or empty (measured "
            "2026-07-29: telephony_synthesis on deepseek-v4-flash effort=high "
            "burned its entire 600-token cap on reasoning and every post-call "
            "return degraded to the raw English vendor summary). Enforced at "
            "the admin save path and at boot on LLM_DEFAULTS."
        ),
    )
    prior_turn_thinking_replay_enabled: bool = Field(
        default=PRIOR_TURN_THINKING_REPLAY_ENABLED_DEFAULT,
        description=(
            "Send an earlier turn's thinking back to the Claude model that wrote it, "
            "when that generation keeps prior thinking without binding it to its "
            "conversation (ADR-362): the vendor's default context, billed as input. "
            "Every other earlier thinking block is removed (a binding generation would "
            "refuse it, another model drops it unread). False = all of them removed."
        ),
    )

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
    # LLM INSTANCE CACHE (TTFT optimization)
    # ========================================================================
    llm_instance_cache_enabled: bool = Field(
        default=True,
        description=(
            "Reuse LLM client instances across calls (keyed by fully resolved config). "
            "Keeps httpx connection pools alive between calls (TCP/TLS keep-alive), "
            "saving a handshake per LLM call. Disable to fall back to "
            "one-instance-per-call behavior."
        ),
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
            "ollama": True,  # Native ``format`` (JSON schema, grammar-constrained) via langchain-ollama (ADR-267)
            "perplexity": False,  # OpenAI-compatible but no /parse
            "gemini": True,  # Native structured output via langchain-google-genai
            "qwen": False,  # OpenAI-compatible; JSON mode fallback (no /parse endpoint)
        }

    # LLM CONFIGURATION - ROUTER and CONTEXT RESOLVER were removed by ADR-244:
    # both slots had no get_llm() caller (every occurrence was a docstring),
    # and these settings had no consumer outside their own declaration.

    # NOTE: Legacy thresholds removed (2025-12-30) - Architecture v3
    # router_confidence_threshold, domain_filtering_*, semantic_router_bypass_*
    # All threshold logic now handled by QueryAnalyzerService in agents.py
    # See: V3_ROUTING_MIN_CONFIDENCE, V3_ROUTING_CHAT_SEMANTIC_THRESHOLD, etc.

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

    query_analyzer_llm_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Timeout in seconds for query analyzer LLM call. Default: 30s.",
    )

    # ========================================================================
    # Ollama Provider — Discovery
    # ========================================================================
    # The Ollama provider exposes `/api/tags` (model list) and `/api/show`
    # (per-model details). These are NOT chat completions — they are short
    # GET calls used at startup and on provider/model UI refresh. We keep
    # their HTTP timeout outside of the per-LLM-type table (which governs
    # actual chat completions) because there is nothing to tune per node.

    ollama_discovery_timeout_seconds: float = Field(
        default=float(OLLAMA_DISCOVERY_TIMEOUT_SECONDS),
        ge=1.0,
        le=60.0,
        description=(
            "HTTP timeout for Ollama discovery endpoints `/api/tags` and "
            "`/api/show` (seconds, default 5s). Bumped if the Ollama host "
            "runs many large models and the cold-cache `/api/show` is slow."
        ),
    )
    ollama_discovery_retry_seconds: float = Field(
        default=float(OLLAMA_DISCOVERY_RETRY_SECONDS),
        ge=0.0,
        le=86400.0,
        description=(
            "Least gap (seconds) before a config reload retries the discovery of "
            "an Ollama address that answered nothing; 0 retries on every reload. "
            "A changed address is always discovered at once, and the admin's "
            "model listing always asks the server."
        ),
    )

    # ``OLLAMA_NUM_CTX`` lived here until ADR-278. It was ONE instance-wide
    # number handed to every Ollama tag whatever its size — a deployment set
    # 128 000 and a 4 B model was asked to allocate the same window as a 27 B
    # one. The window is now a property of the configured SLOT
    # (``llm_config_overrides.context_window``, pre-filled from what the server
    # says about that tag), so the operator sets it where they can SEE which
    # model it applies to. Two authorities on one question is one too many.
