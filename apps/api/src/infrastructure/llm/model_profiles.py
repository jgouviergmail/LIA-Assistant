"""
Model Profiles - LLM Capability Detection with Fallback.

Provides a unified way to query LLM capabilities (structured output, tool calling,
max tokens, etc.) across providers. Uses LangChain's native .profile attribute when
available, with comprehensive fallback profiles for all supported providers.

Architecture (LangChain v1.1 Best Practice):
- Priority 1: Native .profile attribute (provider-specific, most accurate)
- Priority 2: FALLBACK_PROFILES by provider/model (maintained locally)
- Priority 3: Conservative defaults (safe for unknown models)

Usage:
    >>> from src.infrastructure.llm.model_profiles import get_model_profile
    >>> profile = get_model_profile(llm, "openai", "gpt-4.1-mini")
    >>> if profile.supports_tool_calling:
    ...     llm = llm.bind_tools(tools)
    >>> if profile.supports_structured_output:
    ...     llm = llm.with_structured_output(schema, strict=profile.supports_strict_mode)

Providers Supported:
- OpenAI: Full capability (structured output, tools, strict mode)
- Anthropic: Full capability (structured output, tools)
- DeepSeek: Partial (deepseek-chat supports tools, deepseek-reasoner doesn't)
- Gemini: Full capability (structured output, tools)
- Ollama: Model-dependent (conservative defaults)
- Perplexity: Limited (no native structured output or tools)
"""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ModelProfile:
    """
    LLM capability profile for a specific model.

    Attributes:
        max_input_tokens: Maximum context window size
        max_output_tokens: Maximum tokens in response
        supports_structured_output: Can use .with_structured_output()
        supports_tool_calling: Can use .bind_tools()
        supports_strict_mode: Can use strict=True in structured output (OpenAI only)
        supports_streaming: Can stream responses
        supports_vision: Can process images
        cost_per_1m_input: Cost per 1M input tokens (USD)
        cost_per_1m_output: Cost per 1M output tokens (USD)
        is_reasoning_model: Special reasoning model (o-series, GPT-5, deepseek-reasoner)
        metadata: Additional provider-specific metadata
    """

    max_input_tokens: int = 8192
    max_output_tokens: int = 4096
    supports_structured_output: bool = True
    supports_tool_calling: bool = True
    supports_strict_mode: bool = False
    supports_streaming: bool = True
    supports_vision: bool = False
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    is_reasoning_model: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# FALLBACK PROFILES BY PROVIDER
# =============================================================================
# These profiles are used when the LLM doesn't have a native .profile attribute
# or when we need to augment the native profile with additional info.
#
# Maintained based on official documentation (December 2025):
# - OpenAI: https://platform.openai.com/docs/models
# - Anthropic: https://docs.anthropic.com/claude/docs/models-overview
# - DeepSeek: https://www.deepseek.com/docs
# - Gemini: https://ai.google.dev/gemini-api/docs/models/gemini
# - Ollama: https://ollama.com/library

FALLBACK_PROFILES: dict[str, dict[str, ModelProfile]] = {
    # =========================================================================
    # OPENAI
    # IMPORTANT: More specific prefixes MUST come before shorter ones due to
    # startswith() fallback matching in get_model_profile(). E.g., "gpt-4.1-mini"
    # before "gpt-4.1", "o1-mini" before "o1".
    # =========================================================================
    "openai": {
        # GPT-4.1 Series (2025) — specific variants before base
        "gpt-4.1-mini": ModelProfile(
            max_input_tokens=1047576,
            max_output_tokens=16384,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.4,
            cost_per_1m_output=1.6,
        ),
        "gpt-4.1-nano": ModelProfile(
            max_input_tokens=1047576,
            max_output_tokens=16384,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.1,
            cost_per_1m_output=0.4,
        ),
        "gpt-4.1": ModelProfile(
            max_input_tokens=1047576,  # 1M context
            max_output_tokens=32768,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=2.0,
            cost_per_1m_output=8.0,
        ),
        # GPT-5.x series (Reasoning Models - 2025-2026) — specific variants before base
        "gpt-5-mini": ModelProfile(
            max_input_tokens=1047576,
            max_output_tokens=16384,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.25,
            cost_per_1m_output=2.0,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        "gpt-5-nano": ModelProfile(
            max_input_tokens=1047576,
            max_output_tokens=16384,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.05,
            cost_per_1m_output=0.4,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        "gpt-5.2": ModelProfile(
            max_input_tokens=1047576,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=1.75,
            cost_per_1m_output=14.0,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        "gpt-5.1": ModelProfile(
            max_input_tokens=1047576,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=1.25,
            cost_per_1m_output=10.0,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        "gpt-5": ModelProfile(
            max_input_tokens=1047576,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=1.25,
            cost_per_1m_output=10.0,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        # GPT-4o series — specific variants before base
        "gpt-4o-mini": ModelProfile(
            max_input_tokens=128000,
            max_output_tokens=16384,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.15,
            cost_per_1m_output=0.6,
        ),
        "gpt-4o": ModelProfile(
            max_input_tokens=128000,
            max_output_tokens=16384,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=2.5,
            cost_per_1m_output=10.0,
        ),
        # o-Series (Reasoning Models) — specific variants before base
        "o4-mini": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=100000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=1.1,
            cost_per_1m_output=4.4,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        "o3-mini": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=100000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=1.1,
            cost_per_1m_output=4.4,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        "o3": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=100000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=2.0,
            cost_per_1m_output=8.0,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        "o1-mini": ModelProfile(
            max_input_tokens=128000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=1.1,
            cost_per_1m_output=4.4,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        "o1": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=100000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=15.0,
            cost_per_1m_output=60.0,
            is_reasoning_model=True,
            metadata={"reasoning_effort_support": True},
        ),
        # Embedding Models (input-only, no output tokens)
        "text-embedding-3-small": ModelProfile(
            max_input_tokens=8192,
            max_output_tokens=0,  # Embeddings produce vectors, not tokens
            supports_structured_output=False,
            supports_tool_calling=False,
            supports_strict_mode=False,
            supports_streaming=False,
            supports_vision=False,
            cost_per_1m_input=0.02,  # $0.02 per 1M tokens
            cost_per_1m_output=0.0,
            metadata={"model_type": "embedding", "dimensions": 1536},
        ),
        "text-embedding-3-large": ModelProfile(
            max_input_tokens=8192,
            max_output_tokens=0,
            supports_structured_output=False,
            supports_tool_calling=False,
            supports_strict_mode=False,
            supports_streaming=False,
            supports_vision=False,
            cost_per_1m_input=0.13,  # $0.13 per 1M tokens
            cost_per_1m_output=0.0,
            metadata={"model_type": "embedding", "dimensions": 3072},
        ),
        "text-embedding-ada-002": ModelProfile(
            max_input_tokens=8192,
            max_output_tokens=0,
            supports_structured_output=False,
            supports_tool_calling=False,
            supports_strict_mode=False,
            supports_streaming=False,
            supports_vision=False,
            cost_per_1m_input=0.10,  # $0.10 per 1M tokens (legacy)
            cost_per_1m_output=0.0,
            metadata={"model_type": "embedding", "dimensions": 1536},
        ),
        # Default OpenAI (conservative for unknown models)
        "default": ModelProfile(
            max_input_tokens=128000,
            max_output_tokens=16384,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=True,
            supports_streaming=True,
            supports_vision=False,
        ),
    },
    # =========================================================================
    # ANTHROPIC
    # =========================================================================
    "anthropic": {
        # Claude Opus 4.x series
        "claude-opus-4-6": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=32000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,  # Anthropic doesn't have strict mode
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=5.0,
            cost_per_1m_output=25.0,
        ),
        "claude-opus-4-5": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=32000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=5.0,
            cost_per_1m_output=25.0,
        ),
        "claude-opus-4": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=32000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=15.0,
            cost_per_1m_output=75.0,
        ),
        # Claude Sonnet 4.x series
        "claude-sonnet-4-6": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=64000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=3.0,
            cost_per_1m_output=15.0,
        ),
        "claude-sonnet-4-5": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=64000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=3.0,
            cost_per_1m_output=15.0,
        ),
        "claude-sonnet-4": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=64000,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=3.0,
            cost_per_1m_output=15.0,
        ),
        # Claude Haiku 4.x series
        "claude-haiku-4-5": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=1.0,
            cost_per_1m_output=5.0,
        ),
        # Claude 3.5 series (legacy)
        "claude-3-5-sonnet-20241022": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=3.0,
            cost_per_1m_output=15.0,
        ),
        "claude-3-5-haiku-20241022": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.80,
            cost_per_1m_output=4.0,
        ),
        # Default Anthropic
        "default": ModelProfile(
            max_input_tokens=200000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
        ),
    },
    # =========================================================================
    # DEEPSEEK
    # =========================================================================
    "deepseek": {
        "deepseek-chat": ModelProfile(
            max_input_tokens=128000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
            cost_per_1m_input=0.28,
            cost_per_1m_output=0.42,
        ),
        "deepseek-reasoner": ModelProfile(
            max_input_tokens=128000,
            max_output_tokens=64000,
            supports_structured_output=False,  # Thinking mode doesn't support structured output
            supports_tool_calling=False,  # Thinking mode doesn't support tools
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
            cost_per_1m_input=0.28,
            cost_per_1m_output=0.42,
            is_reasoning_model=True,
        ),
        # Default DeepSeek
        "default": ModelProfile(
            max_input_tokens=128000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
        ),
    },
    # =========================================================================
    # GEMINI
    # IMPORTANT: More specific prefixes MUST come before shorter ones due to
    # startswith() fallback matching. E.g., "gemini-2.5-flash-lite" before
    # "gemini-2.5-flash".
    # =========================================================================
    "gemini": {
        # Gemini 3.x series (2026)
        "gemini-3.1-pro-preview": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,  # Gemini doesn't have strict mode
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=2.0,
            cost_per_1m_output=12.0,
        ),
        "gemini-3-pro-preview": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=2.0,
            cost_per_1m_output=12.0,
        ),
        "gemini-3-flash-preview": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.50,
            cost_per_1m_output=3.0,
        ),
        # Gemini 2.5 series — specific variants before base
        "gemini-2.5-pro": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=1.25,
            cost_per_1m_output=10.0,
        ),
        "gemini-2.5-flash-lite": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.10,
            cost_per_1m_output=0.40,
        ),
        "gemini-2.5-flash": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.30,
            cost_per_1m_output=2.50,
        ),
        # Gemini 2.0 series — specific variants before base
        "gemini-2.0-flash-lite": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.075,
            cost_per_1m_output=0.30,
        ),
        "gemini-2.0-flash": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            cost_per_1m_input=0.10,
            cost_per_1m_output=0.40,
        ),
        # Default Gemini
        "default": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
        ),
    },
    # =========================================================================
    # OLLAMA (Local deployment - conservative defaults)
    # =========================================================================
    # NOTE: These profiles are used as FALLBACK when Ollama is unreachable
    # and at runtime by get_model_profile() for the LLM factory.
    # When Ollama is reachable, the admin UI queries real capabilities
    # via POST /api/show (see ollama_discovery.py).
    "ollama": {
        # Ollama models vary widely - use conservative defaults
        "default": ModelProfile(
            max_input_tokens=32768,
            max_output_tokens=4096,
            supports_structured_output=False,  # Model-dependent, default to False
            supports_tool_calling=False,  # Model-dependent, default to False
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
            cost_per_1m_input=0.0,  # Local = free
            cost_per_1m_output=0.0,
        ),
        # Common Ollama models with better profiles
        "llama3.1": ModelProfile(
            max_input_tokens=131072,
            max_output_tokens=4096,
            supports_structured_output=True,  # llama3.1 supports JSON mode
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
        ),
        "llama3.2": ModelProfile(
            max_input_tokens=131072,
            max_output_tokens=4096,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,  # llama3.2 has vision variants
        ),
        "mistral": ModelProfile(
            max_input_tokens=32768,
            max_output_tokens=4096,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
        ),
        "qwen2.5": ModelProfile(
            max_input_tokens=131072,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
        ),
    },
    # =========================================================================
    # QWEN (Alibaba Cloud via DashScope OpenAI-compatible API)
    # =========================================================================
    "qwen": {
        # Conservative default for unknown Qwen models
        "default": ModelProfile(
            max_input_tokens=131072,
            max_output_tokens=8192,
            supports_structured_output=True,
            supports_tool_calling=False,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
            is_reasoning_model=True,
            cost_per_1m_input=0.40,
            cost_per_1m_output=2.40,
        ),
        # qwen3-max: thinking-only model, NO tools, NO vision
        "qwen3-max": ModelProfile(
            max_input_tokens=262144,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=False,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
            is_reasoning_model=True,
            cost_per_1m_input=1.20,
            cost_per_1m_output=6.00,
        ),
        # qwen3.5-plus: tools + vision + thinking
        "qwen3.5-plus": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            is_reasoning_model=True,
            cost_per_1m_input=0.40,
            cost_per_1m_output=2.40,
        ),
        # qwen3.5-flash: tools + vision + thinking (cost-effective)
        "qwen3.5-flash": ModelProfile(
            max_input_tokens=1000000,
            max_output_tokens=65536,
            supports_structured_output=True,
            supports_tool_calling=True,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=True,
            is_reasoning_model=True,
            cost_per_1m_input=0.10,
            cost_per_1m_output=0.40,
        ),
    },
    # =========================================================================
    # PERPLEXITY (Search-augmented, limited capabilities)
    # =========================================================================
    "perplexity": {
        # Perplexity uses OpenAI-compatible API but with limitations
        "default": ModelProfile(
            max_input_tokens=127000,
            max_output_tokens=4096,
            supports_structured_output=False,  # No /parse endpoint
            supports_tool_calling=False,  # No tool support
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
            cost_per_1m_input=0.20,  # Perplexity pricing varies
            cost_per_1m_output=0.60,
            metadata={"search_augmented": True},
        ),
        "llama-3.1-sonar-small-128k-online": ModelProfile(
            max_input_tokens=127000,
            max_output_tokens=4096,
            supports_structured_output=False,
            supports_tool_calling=False,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
            cost_per_1m_input=0.20,
            cost_per_1m_output=0.20,
            metadata={"search_augmented": True},
        ),
        "llama-3.1-sonar-large-128k-online": ModelProfile(
            max_input_tokens=127000,
            max_output_tokens=4096,
            supports_structured_output=False,
            supports_tool_calling=False,
            supports_strict_mode=False,
            supports_streaming=True,
            supports_vision=False,
            cost_per_1m_input=1.0,
            cost_per_1m_output=1.0,
            metadata={"search_augmented": True},
        ),
    },
}


# =============================================================================
# CONSERVATIVE DEFAULT PROFILE
# =============================================================================
# Used when provider is unknown or model has no specific profile
CONSERVATIVE_DEFAULT = ModelProfile(
    max_input_tokens=8192,
    max_output_tokens=4096,
    supports_structured_output=False,
    supports_tool_calling=True,
    supports_strict_mode=False,
    supports_streaming=True,
    supports_vision=False,
)


def get_model_profile(llm: BaseChatModel | None, provider: str, model: str) -> ModelProfile:
    """
    Get capability profile for an LLM model.

    Priority order:
    1. Native .profile attribute from LLM (LangChain 1.1+)
    2. Specific model profile from FALLBACK_PROFILES
    3. Provider default profile from FALLBACK_PROFILES
    4. CONSERVATIVE_DEFAULT (safest defaults)

    Args:
        llm: LangChain BaseChatModel instance (optional, for native profile detection)
        provider: Provider name (openai, anthropic, deepseek, gemini, ollama, perplexity)
        model: Model identifier (e.g., "gpt-4.1-mini", "claude-sonnet-4-5")

    Returns:
        ModelProfile: Capability profile for the model

    Examples:
        >>> # With LLM instance
        >>> profile = get_model_profile(llm, "openai", "gpt-4.1-mini")
        >>> if profile.supports_strict_mode:
        ...     use_strict = True

        >>> # Without LLM instance (fallback only)
        >>> profile = get_model_profile(None, "deepseek", "deepseek-reasoner")
        >>> if not profile.supports_tool_calling:
        ...     raise ValueError("Model doesn't support tools")
    """
    # Priority 1: Check native .profile attribute (LangChain 1.1+)
    if llm is not None and hasattr(llm, "profile") and llm.profile is not None:
        native_profile = llm.profile
        logger.debug(
            "model_profile_from_native",
            provider=provider,
            model=model,
            source="native",
        )
        # Convert native profile to our ModelProfile format
        # LangChain's profile may have different attribute names
        return _convert_native_profile(native_profile, provider, model)

    # Priority 2: Look up in FALLBACK_PROFILES
    provider_profiles = FALLBACK_PROFILES.get(provider.lower(), {})

    # Try exact model match
    if model in provider_profiles:
        logger.debug(
            "model_profile_from_fallback",
            provider=provider,
            model=model,
            source="exact_match",
        )
        return provider_profiles[model]

    # Try partial model match (e.g., "gpt-4.1-mini-2024-07-18" -> "gpt-4.1-mini")
    for profile_model, profile in provider_profiles.items():
        if profile_model != "default" and model.startswith(profile_model):
            logger.debug(
                "model_profile_from_fallback",
                provider=provider,
                model=model,
                matched_model=profile_model,
                source="partial_match",
            )
            return profile

    # Priority 3: Provider default
    if "default" in provider_profiles:
        logger.debug(
            "model_profile_from_fallback",
            provider=provider,
            model=model,
            source="provider_default",
        )
        return provider_profiles["default"]

    # Priority 4: Conservative default
    logger.warning(
        "model_profile_using_conservative_default",
        provider=provider,
        model=model,
        msg=f"No profile found for {provider}/{model}, using conservative defaults",
    )
    return CONSERVATIVE_DEFAULT


def _convert_native_profile(native_profile: Any, provider: str, model: str) -> ModelProfile:
    """
    Convert LangChain native profile to our ModelProfile format.

    LangChain's profile may have different attribute names or structure.
    This function normalizes it to our standard format.

    Args:
        native_profile: Native profile object from LLM
        provider: Provider name
        model: Model name

    Returns:
        ModelProfile: Standardized profile
    """

    # Extract attributes safely with defaults
    def get_attr(obj: Any, name: str, default: Any) -> Any:
        return getattr(obj, name, default)

    # LangChain profile attributes may vary
    # Common attributes: max_tokens, context_window, supports_structured_output, etc.
    return ModelProfile(
        max_input_tokens=get_attr(native_profile, "context_window", 8192)
        or get_attr(native_profile, "max_input_tokens", 8192),
        max_output_tokens=get_attr(native_profile, "max_tokens", 4096)
        or get_attr(native_profile, "max_output_tokens", 4096),
        supports_structured_output=get_attr(native_profile, "supports_structured_output", True),
        supports_tool_calling=get_attr(native_profile, "supports_tool_calling", True)
        or get_attr(native_profile, "supports_tools", True),
        supports_strict_mode=get_attr(native_profile, "supports_strict_mode", False)
        and provider == "openai",  # Only OpenAI supports strict mode
        supports_streaming=get_attr(native_profile, "supports_streaming", True),
        supports_vision=get_attr(native_profile, "supports_vision", False)
        or get_attr(native_profile, "supports_image_input", False),
        # Cost info may not be in native profile
        cost_per_1m_input=get_attr(native_profile, "cost_per_1m_input", 0.0),
        cost_per_1m_output=get_attr(native_profile, "cost_per_1m_output", 0.0),
        is_reasoning_model=get_attr(native_profile, "is_reasoning_model", False),
        metadata={"source": "native", "provider": provider, "model": model},
    )


def supports_structured_output(provider: str, model: str | None = None) -> bool:
    """
    Quick check if a provider/model supports structured output.

    Convenience function for simple capability checks without full profile.

    Args:
        provider: Provider name
        model: Optional model name (uses provider default if not specified)

    Returns:
        bool: True if structured output is supported
    """
    profile = get_model_profile(None, provider, model or "default")
    return profile.supports_structured_output


def supports_tool_calling(provider: str, model: str | None = None) -> bool:
    """
    Quick check if a provider/model supports tool calling.

    Convenience function for simple capability checks without full profile.

    Args:
        provider: Provider name
        model: Optional model name (uses provider default if not specified)

    Returns:
        bool: True if tool calling is supported
    """
    profile = get_model_profile(None, provider, model or "default")
    return profile.supports_tool_calling


def is_reasoning_model(provider: str, model: str) -> bool:
    """
    Check if a model is a reasoning model (o-series, GPT-5, deepseek-reasoner).

    Reasoning models have special parameter requirements:
    - No temperature (or must be 1)
    - No top_p, frequency_penalty, presence_penalty
    - Support reasoning_effort parameter

    Args:
        provider: Provider name
        model: Model name

    Returns:
        bool: True if model is a reasoning model
    """
    profile = get_model_profile(None, provider, model)
    return profile.is_reasoning_model
