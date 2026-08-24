"""
LLM Configuration Helper — Resolves effective LLM config for any agent type.

Resolution flow: LLM_DEFAULTS (code constants) → DB override (in-memory cache) → Effective config.

The `settings` parameter is kept for backward compatibility but is no longer used
for LLM config resolution (code constants replace .env settings).

Usage:
    >>> from src.core.llm_config_helper import get_llm_config_for_agent
    >>> config = get_llm_config_for_agent(settings, "planner")
    >>> print(config.model)  # "gpt-4.1-nano" (from LLM_DEFAULTS)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.constants import CAPABILITY_PROVENANCE_DECLARED
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
        agent_type: Agent type identifier (e.g., "planner", "response")

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
    effective = defaults if not override else merge_config(defaults, override)

    # Report only, never reject: this model came from a code default or from an
    # admin decision, and the catalogue is evidence, not authority over a human
    # (ADR-244). The hard filter applies to policy candidates alone.
    from src.infrastructure.llm.capability_gate import report_configured_model

    if effective.model:
        report_configured_model(canonical_type, effective.model)

    return effective


def merge_config(defaults: LLMAgentConfig, overrides: dict[str, Any]) -> LLMAgentConfig:
    """Merge DB overrides onto code defaults, producing effective config.

    ``reasoning_effort`` used to need special handling: its SHAPE depended on
    the target model's ``reasoning_widget``, so a Qwen default propagated onto
    a DeepSeek override crashed the typed builder, and two guards existed to
    drop a value that could not be proven compatible. ADR-245 removed the four
    shapes and the builders; one intent fits every model and the translator
    coerces its level to the nearest the model offers.

    So the value is simply inherited. That is not merely simpler, it is more
    faithful in both directions:

    - dropping it silently erased an effort the admin had chosen. Measured
      2026-07-27 — the three background extractors (memory, interests, journal)
      ran with no reasoning block at all, because the admin UI omits a field
      equal to the type's default and the column then stored NULL. A knob that
      cannot express its own default value is a broken knob;
    - and dropping a ``level="none"`` inherited onto a model whose own default
      is thinking-on silently TURNED REASONING ON — the opposite of what the
      operator wrote, and billed accordingly.
    """
    merged = defaults.model_dump()

    for key, value in overrides.items():
        # An empty string is never a valid override value — for `provider` it
        # even fails the LLMAgentConfig Literal and would turn EVERY merge of
        # that row into a 500 at read time. Treat it exactly like None (unset).
        if value is not None and value != "" and key in merged:
            merged[key] = value

    # A model change no longer drops an inherited reasoning value (ADR-245).
    # The two guards that did are gone with the shape-dispatching builders they
    # protected: nothing raises on a mismatch any more, the translator coerces
    # the level to the nearest the new model offers, and it says so. Dropping
    # was the worse answer -- a default of ``level="none"`` inherited onto a
    # model whose own default is thinking-on silently TURNED REASONING ON,
    # which is the opposite of what the operator wrote.
    return LLMAgentConfig(**merged)


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


def get_effective_context_window(model: str) -> int:
    """Resolve a model's context window from the DB-backed catalogue, then the table.

    Neither internal source is authoritative on its own. The catalogue carried
    column defaults on 89 of 114 rows (``gpt-5.2`` at 8 192 against a real
    272 000), and ``MODEL_CONTEXT_WINDOWS`` is wrong on 10 of its 56 entries
    (``gpt-5.2`` at 1 047 576, ``claude-opus-4-6`` at 200 000 against
    1 000 000). The **provenance** decides: an ``imported`` or ``verified``
    catalogue row wins; a ``declared`` one falls back to the table, which stays
    the safety net (prefix matching and ``DEFAULT_CONTEXT_WINDOW`` included)
    for models outside the catalogue and for the boot window before the cache
    is loaded.

    Args:
        model: Model identifier as configured (date-suffixed ids are retried
            after ``normalize_model_name``, mirroring ``get_model_profile``).

    Returns:
        Context window in tokens (always > 0).
    """
    from src.core.config.llm import get_model_context_window
    from src.core.llm_utils import normalize_model_name
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    caps = ModelCapabilitiesCache.get(model)
    if caps is None:
        normalized = normalize_model_name(model)
        if normalized != model:
            caps = ModelCapabilitiesCache.get(normalized)

    if (
        caps is not None
        and caps.max_input_tokens > 0
        and caps.capability_provenance != CAPABILITY_PROVENANCE_DECLARED
    ):
        return caps.max_input_tokens

    return get_model_context_window(model)
