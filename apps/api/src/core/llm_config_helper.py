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
    """Merge DB overrides onto code defaults, producing effective config."""
    merged = defaults.model_dump()
    for key, value in overrides.items():
        if value is not None and key in merged:
            merged[key] = value
    return LLMAgentConfig(**merged)


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
