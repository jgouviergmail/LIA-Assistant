"""
Model Profiles — LLM Capability Detection (DB-backed).

Provides a unified way to query LLM capabilities (structured output, tool
calling, max tokens, etc.) across providers. Uses LangChain's native
``.profile`` attribute when available, otherwise falls back to the
DB-backed :class:`ModelCapabilitiesCache` (populated at boot from the
``llm_models`` table).

Architecture (after the v1.x DB-source-of-truth release):
- Priority 1: Native ``.profile`` attribute (provider-specific, most accurate)
- Priority 2: ``ModelCapabilitiesCache`` exact match
- Priority 3: ``ModelCapabilitiesCache`` after ``normalize_model_name()``
- Priority 4: ``CONSERVATIVE_DEFAULT`` (safe defaults — emits a warning)

Usage:
    >>> from src.infrastructure.llm.model_profiles import get_model_profile
    >>> profile = get_model_profile(llm, "openai", "gpt-4.1-mini")
    >>> if profile.supports_tool_calling:
    ...     llm = llm.bind_tools(tools)
    >>> if profile.supports_structured_output:
    ...     llm = llm.with_structured_output(schema, strict=profile.supports_strict_mode)
"""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from src.core.llm_utils import normalize_model_name
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
        cost_per_1m_cached_input: Cost per 1M cached input tokens (USD)
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
    cost_per_1m_cached_input: float | None = None
    cost_per_1m_output: float = 0.0
    is_reasoning_model: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# NOTE: The legacy ``FALLBACK_PROFILES`` in-code catalogue (~30+ models)
# was removed in the v1.x DB-source-of-truth release. Capabilities now
# live in the ``llm_models`` table and are exposed at runtime via
# ``ModelCapabilitiesCache`` (priority 2 in ``get_model_profile``).
# Pricing lives in ``llm_model_pricing`` and is read separately by
# ``AsyncPricingService``.
#
# The full historical snapshot is preserved for re-deployment in
# ``apps/api/alembic/versions/2026_05_05_0002-llm_models_backfill.py``
# (MODELS_DATA + IMAGE_PROVIDERS).

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

    Priority order (after the v1.x DB-source-of-truth refactor):
    1. Native ``.profile`` attribute from the LLM instance (LangChain 1.1+)
    2. :class:`ModelCapabilitiesCache` lookup by ``model_name``
       (DB-sourced, populated at boot from ``llm_models``)
    3. Same lookup with ``normalize_model_name()`` to strip date suffixes
       (e.g. ``gpt-4.1-mini-2025-04-14`` → ``gpt-4.1-mini``)
    4. :data:`CONSERVATIVE_DEFAULT` (safest defaults — logs a warning)

    ``FALLBACK_PROFILES`` was deleted in the v1.x DB-source-of-truth release.
    The runtime catalogue is now :class:`ModelCapabilitiesCache` (DB-backed).

    Args:
        llm: LangChain BaseChatModel instance (optional, for native detection)
        provider: Provider name (kept for native-profile metadata; ignored by
            the cache lookup since ``model_name`` is globally unique)
        model: Model identifier (e.g., "gpt-4.1-mini", "claude-sonnet-4-5")

    Returns:
        :class:`ModelProfile`: Capability profile for the model.
    """
    # Priority 1: Check native .profile attribute (LangChain 1.1+)
    if llm is not None and getattr(llm, "profile", None) is not None:
        logger.debug(
            "model_profile_from_native",
            provider=provider,
            model=model,
            source="native",
        )
        return _convert_native_profile(llm.profile, provider, model)

    # Priority 2: ModelCapabilitiesCache exact match (hot path, O(1))
    # Imported lazily to avoid an import cycle at module load time
    # (model_capabilities_cache imports ModelProfile from this file).
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    cached = ModelCapabilitiesCache.get(model)
    if cached is not None:
        logger.debug(
            "model_profile_from_cache",
            provider=provider,
            model=model,
            source="cache_exact",
        )
        return cached

    # Priority 3: Same lookup after normalizing the model name (date suffixes).
    # Avoid a second hit when the name is already normalized.
    normalized = normalize_model_name(model)
    if normalized != model:
        cached = ModelCapabilitiesCache.get(normalized)
        if cached is not None:
            logger.debug(
                "model_profile_from_cache",
                provider=provider,
                model=model,
                normalized=normalized,
                source="cache_normalized",
            )
            return cached

    # Priority 4: Conservative default (warning so ops can spot misconfigured models).
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
