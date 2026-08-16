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
    ``model`` without providing a ``reasoning_effort``, the default's value
    may or may not fit the new model — e.g. a Qwen default
    ``ReasoningEffortToggleBudget`` propagated onto a DeepSeek override would
    crash the typed builder. It is therefore inherited only when it is
    PROVABLY compatible with the new model (:func:`_is_inheritable_reasoning_effort`),
    and dropped otherwise.

    That "provably" matters: this branch used to drop the value
    unconditionally, which silently erased an effort the admin had chosen.
    Measured 2026-07-27 — the three background extractors (memory, interests,
    journal) ran with no reasoning block at all, because the admin UI omits a
    field equal to the type's default (override semantics) and the column then
    stored NULL, which this function turned into "no reasoning" instead of
    "the default's low". A knob that cannot express its own default value is
    a broken knob.

    As a final safety net, :func:`_reconcile_reasoning_effort` still drops any
    ``reasoning_effort`` that does not match the effective model's
    ``reasoning_widget`` (so a stale DB override / seed / manual edit degrades
    to the model default instead of crashing the typed reasoning builder at
    LLM-instantiation time).
    """
    merged = defaults.model_dump()
    override_changes_model = (
        "model" in overrides
        and overrides["model"] is not None
        and overrides["model"] != defaults.model
    )
    override_provides_reasoning = "reasoning_effort" in overrides

    for key, value in overrides.items():
        # An empty string is never a valid override value — for `provider` it
        # even fails the LLMAgentConfig Literal and would turn EVERY merge of
        # that row into a 500 at read time. Treat it exactly like None (unset).
        if value is not None and value != "" and key in merged:
            merged[key] = value

    if (
        override_changes_model
        and not override_provides_reasoning
        and not _is_inheritable_reasoning_effort(defaults.reasoning_effort, merged.get("model"))
    ):
        merged["reasoning_effort"] = None

    return _reconcile_reasoning_effort(LLMAgentConfig(**merged))


def _is_inheritable_reasoning_effort(
    value: Any,
    model: str | None,
) -> bool:
    """Whether a default's ``reasoning_effort`` survives a model change.

    Inheritance requires proof, not optimism: an unknown model (a dynamically
    discovered Ollama tag, a catalogue that has not loaded yet) cannot be
    checked, so the value is dropped rather than risk the typed reasoning
    builder. A known model whose widget accepts the value keeps it.

    Args:
        value: The default's ``reasoning_effort`` (typed, may be ``None``).
        model: The effective model id after the override.

    Returns:
        True when the value can be carried over to ``model``.
    """
    if value is None or model is None:
        return False

    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    caps = ModelCapabilitiesCache.get(model)
    if caps is None:
        return False

    from src.domains.llm_config.reasoning_validation import reasoning_effort_matches_widget

    return reasoning_effort_matches_widget(caps, value)


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


def get_effective_context_window(model: str) -> int:
    """Resolve a model's context window from the DB-backed catalogue, then the table.

    Summarization triggers and compaction sizing previously read only the
    hand-maintained ``MODEL_CONTEXT_WINDOWS`` table, which drifts from what the
    admin LLM catalogue (``llm_models`` → :class:`ModelCapabilitiesCache`)
    declares — the same two-authorities trap the DB-source-of-truth release
    removed for every other capability. The cache is authoritative when it
    knows the model; the table stays as the safety net (prefix matching and
    ``DEFAULT_CONTEXT_WINDOW`` included) for models outside the catalogue and
    for the boot window before the cache is loaded.

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

    if caps is not None and caps.max_input_tokens > 0:
        return caps.max_input_tokens

    return get_model_context_window(model)
