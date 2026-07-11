"""
LLM Configuration Helper — Resolves effective LLM config for any agent type.

Resolution flow: LLM_DEFAULTS (code constants) → DB override (in-memory cache) → Effective config.

The `settings` parameter is kept for backward compatibility but is no longer used
for LLM config resolution (code constants replace .env settings).

Usage:
    >>> from src.core.llm_config_helper import get_llm_config_for_agent
    >>> config = get_llm_config_for_agent(settings, "router")
    >>> print(config.model)  # "gpt-4.1-nano" (from LLM_DEFAULTS)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.llm_agent_config import LLMAgentConfig
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.core.config import Settings

logger = get_logger(__name__)

# Canonical name mapping: aliases → canonical llm_type in LLM_DEFAULTS/LLM_TYPES_REGISTRY.
# New unified names (contact_agent, email_agent, etc.) map to the canonical names
# used in LLM_DEFAULTS (contacts_agent, emails_agent, etc.).
_ALIAS_MAP: dict[str, str] = {
    "contact_agent": "contacts_agent",
    "email_agent": "emails_agent",
    "event_agent": "calendar_agent",
    "file_agent": "drive_agent",
    "task_agent": "tasks_agent",
    "place_agent": "places_agent",
    "route_agent": "routes_agent",
}


def _resolve_canonical_type(agent_type: str) -> str:
    """Resolve an agent type alias to its canonical name in LLM_DEFAULTS."""
    return _ALIAS_MAP.get(agent_type, agent_type)


def get_llm_config_for_agent(settings: Settings, agent_type: str) -> LLMAgentConfig:
    """
    Get effective LLM config for a specific agent type.

    Resolution: LLM_DEFAULTS (code) → DB override cache (if exists) → Effective config.

    Args:
        settings: Settings instance (kept for backward compatibility, not used for LLM config)
        agent_type: Agent type identifier (e.g., "router", "response", "planner")

    Returns:
        LLMAgentConfig instance with effective parameters

    Raises:
        ValueError: If agent_type is not recognized
    """
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.domains.llm_config.constants import LLM_DEFAULTS

    canonical_type = _resolve_canonical_type(agent_type)

    defaults = LLM_DEFAULTS.get(canonical_type)
    if defaults is None:
        raise ValueError(
            f"Unknown agent_type '{agent_type}'. " f"Expected one of: {list(LLM_DEFAULTS.keys())}"
        )

    # Check for DB override in cache (sync read, zero latency)
    override = LLMConfigOverrideCache.get_override(canonical_type)
    if not override:
        return defaults

    # Merge: code defaults + DB overrides (non-null fields only)
    return merge_config(defaults, override)


def merge_config(defaults: LLMAgentConfig, overrides: dict[str, Any]) -> LLMAgentConfig:
    """Merge DB overrides onto code defaults, producing effective config.

    Special handling for ``reasoning_effort``: its shape depends on the
    target model's ``reasoning_widget``. When the override changes the
    ``model`` (and the default's ``reasoning_effort`` was set for the OLD
    model), inheriting the default's ``reasoning_effort`` would carry the
    wrong shape into the new model — e.g. a Qwen default
    ``ReasoningEffortToggleBudget`` propagated onto a DeepSeek override
    would crash the typed builder. Drop ``reasoning_effort`` in that case
    unless the override explicitly provides a value. As a final safety net,
    :func:`_reconcile_reasoning_effort` then drops any ``reasoning_effort``
    that still doesn't match the effective model's ``reasoning_widget`` (so a
    stale DB override / seed / manual edit degrades to the model default
    instead of crashing the typed reasoning builder at LLM-instantiation time).
    """
    merged = defaults.model_dump()
    override_changes_model = (
        "model" in overrides
        and overrides["model"] is not None
        and overrides["model"] != defaults.model
    )
    override_provides_reasoning = "reasoning_effort" in overrides
    if override_changes_model and not override_provides_reasoning:
        merged["reasoning_effort"] = None

    for key, value in overrides.items():
        if value is not None and key in merged:
            merged[key] = value
    return _reconcile_reasoning_effort(LLMAgentConfig(**merged))


def _reconcile_reasoning_effort(cfg: LLMAgentConfig) -> LLMAgentConfig:
    """Drop a ``reasoning_effort`` that is incompatible with ``cfg.model``.

    Robustness guarantee: changing a model/provider — or any stale value left
    over from a prior model (old DB override row, outdated seed, manual edit, a
    past bug) — must never crash the typed reasoning builder at ``get_llm()``
    time. If the stored ``reasoning_effort`` shape/value does not match the
    effective model's ``reasoning_widget``, fall back to the model's intrinsic
    default (``None``) and log a warning so the drift is visible. No-ops when
    there is nothing to check, when the model is unknown to the catalogue
    (e.g. a dynamically discovered Ollama model), or when the value is already
    valid.

    Args:
        cfg: The merged effective config (code defaults + DB overrides).

    Returns:
        ``cfg`` unchanged when its ``reasoning_effort`` is valid (or absent, or
        unverifiable), otherwise a copy with ``reasoning_effort`` set to ``None``.
    """
    if cfg.reasoning_effort is None or cfg.model is None:
        return cfg

    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    caps = ModelCapabilitiesCache.get(cfg.model)
    if caps is None:
        return cfg

    from src.domains.llm_config.reasoning_validation import reasoning_effort_matches_widget

    if reasoning_effort_matches_widget(caps, cfg.reasoning_effort):
        return cfg

    logger.warning(
        "llm_config_reasoning_effort_dropped",
        model=cfg.model,
        reasoning_widget=caps.reasoning_widget,
        reasoning_effort=cfg.reasoning_effort.model_dump(),
        msg=(
            "Stored reasoning_effort is incompatible with the effective model "
            "(wrong shape or out-of-range value); falling back to the model's "
            "default reasoning behaviour."
        ),
    )
    return cfg.model_copy(update={"reasoning_effort": None})


def get_provider_api_key(provider: str) -> str | None:
    """Get the decrypted API key registered for an LLM/TTS provider.

    Thin core-level facade over the in-memory ``LLMConfigOverrideCache``
    (sync read, no DB round-trip) so that domains can probe provider
    availability without importing the ``llm_config`` domain directly
    (coupling reduction, see ADR-126).

    Args:
        provider: Provider name (e.g. ``"elevenlabs"``, ``"openai"``).

    Returns:
        Decrypted API key string, or ``None`` if not configured.
    """
    from src.domains.llm_config.cache import LLMConfigOverrideCache

    return LLMConfigOverrideCache.get_api_key(provider)


def get_all_llm_configs(settings: Settings) -> dict[str, LLMAgentConfig]:
    """
    Get LLM configs for all registered agent types.

    Returns:
        Dictionary mapping agent_type to LLMAgentConfig
    """
    from src.domains.llm_config.constants import LLM_DEFAULTS

    return {
        agent_type: get_llm_config_for_agent(settings, agent_type) for agent_type in LLM_DEFAULTS
    }
