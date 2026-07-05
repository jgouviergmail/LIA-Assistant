"""Parity guard for the domain vocabulary (single source: ``DOMAIN_REGISTRY``).

The multi-agent system names domains on **two axes**, both derived from the
single source of truth :data:`DOMAIN_REGISTRY`
(``src/domains/agents/registry/domain_taxonomy.py``):

- **Singular axis** — the domain *name* (registry key): ``place``, ``contact``,
  ``email``… This is what ``QueryIntelligence.primary_domain`` /
  ``QueryIntelligence.domains`` / ``source_domain`` hold at runtime (they are
  populated from ``get_routable_domains()``).
- **Result-key axis** — the plural ``DomainConfig.result_key``: ``places``,
  ``contacts``, ``emails``… This is what ``$context.<key>`` references,
  ``CONTEXT_DOMAIN_*`` constants and ``structured_data`` carry.

A derived table becomes **inert** the moment one of its domain tokens is
compared against the *wrong* axis — the comparison silently never matches,
producing either a silent functional error or a wasted LLM retry. This guard,
modelled on ``drafts/display.py::assert_registry_completeness`` (ADR-085),
fails on any off-vocabulary token so those regressions cannot ship.

Two kinds of assertion:

1. **Strict, axis-aware** — for tables whose tokens are *compared* against a
   runtime domain value. The token must be on the exact expected axis.
2. **Tolerant, non-orphan** — for definitional / display tables that
   legitimately carry both forms plus a few documented auxiliary result types
   and legacy display aliases. Every token must still resolve to a canonical
   domain; a brand-new typo (outside the whole vocabulary) fails.

See ADR-102 (Domain Vocabulary Single Source).
"""

from __future__ import annotations

import src.domains.agents.constants as agent_constants
from src.domains.agents.display.html_renderer import HtmlRenderer
from src.domains.agents.orchestration.validator import VALID_CONTEXT_REFERENCE_DOMAINS
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.agents.services.analysis.goal_inferrer import _GOAL_PATTERNS
from src.domains.agents.services.context_resolution_service import _DATA_KEY_TO_RESULT_KEY
from src.domains.agents.services.planner.domain_constants import CROSS_DOMAIN_MAPPINGS
from src.domains.agents.utils.type_domain_mapping import TYPE_TO_DOMAIN_MAP

# ---------------------------------------------------------------------------
# The two canonical axes — both derived from the single source of truth.
# ---------------------------------------------------------------------------
CANONICAL_DOMAINS: frozenset[str] = frozenset(DOMAIN_REGISTRY)
CANONICAL_RESULT_KEYS: frozenset[str] = frozenset(
    config.result_key for config in DOMAIN_REGISTRY.values()
)

# Auxiliary registry item types that legitimately have NO routable domain in
# DOMAIN_REGISTRY: they are sub-results of a routable domain (calendar
# containers vs events, GPS location vs place) or transient UI payloads
# (MCP/skill interactive widgets). Both singular and result-key forms are
# declared explicitly so the tolerant guards below stay meaningful.
AUXILIARY_TYPES: frozenset[str] = frozenset(
    {
        "calendar",
        "calendars",  # list_calendars_tool — calendar containers (not events)
        "location",
        "locations",  # get_current_location_tool — GPS position (not a place)
        "mcp_app",
        "mcp_apps",  # MCP Apps interactive widgets (evolution F2.5)
        "skill_app",
        "skill_apps",  # Skill rich outputs (frame/image widgets)
    }
)

# Legacy display-only aliases tolerated by the alias-tolerant HTML renderer:
# both the canonical form and the alias are registered as rendering fallbacks.
# They are NOT condition tests — no comparison depends on them — so they are
# permitted for the display map only, never on a comparison axis.
LEGACY_DISPLAY_ALIASES: frozenset[str] = frozenset(
    {
        "drive",  # legacy rename drive -> file/files
        "articles",  # Wikipedia card data key
        "search",  # generic search-result card
    }
)

# Accepted vocabularies for the tolerant guards.
ACCEPTED_DOMAIN_TOKENS: frozenset[str] = CANONICAL_DOMAINS | CANONICAL_RESULT_KEYS | AUXILIARY_TYPES
ACCEPTED_DISPLAY_TOKENS: frozenset[str] = ACCEPTED_DOMAIN_TOKENS | LEGACY_DISPLAY_ALIASES


# ===========================================================================
# (a) Strict, axis-aware guards — comparison-consumer tables
# ===========================================================================


def test_cross_domain_mappings_target_is_canonical_singular() -> None:
    """``CROSS_DOMAIN_MAPPINGS`` target is compared to ``primary_domain``.

    ``CrossDomainBypassStrategy`` matches ``intelligence.primary_domain ==
    target_domain``. ``primary_domain`` is a singular ``DOMAIN_REGISTRY`` name,
    so every ``target_domain`` MUST be a singular name — a plural result_key
    (e.g. ``places``) makes the comparison never match and the LLM-bypass dies.
    """
    offenders = {
        field: target
        for field, (target, _tool, _param) in CROSS_DOMAIN_MAPPINGS.items()
        if target not in CANONICAL_DOMAINS
    }
    assert not offenders, (
        "CROSS_DOMAIN_MAPPINGS target_domain must be a singular DOMAIN_REGISTRY "
        f"name (compared against primary_domain). Off-vocabulary: {offenders}"
    )


def test_goal_patterns_domain_is_canonical_singular() -> None:
    """``_GOAL_PATTERNS`` domain is matched against ``QueryIntelligence.domains``.

    ``GoalInferrer`` matches ``pattern_domain in domains``. ``domains`` is a
    list of singular ``DOMAIN_REGISTRY`` names, so every pattern domain MUST be
    a singular name — a plural (``contacts``) or a non-domain (``drive``) makes
    the fast-path strategy inert.
    """
    offenders = sorted(
        {domain for (_intent, domain) in _GOAL_PATTERNS if domain not in CANONICAL_DOMAINS}
    )
    assert not offenders, (
        "_GOAL_PATTERNS domain keys must be singular DOMAIN_REGISTRY names "
        f"(matched against intelligence.domains). Off-vocabulary: {offenders}"
    )


def test_valid_context_reference_domains_are_result_keys() -> None:
    """``PlanValidator``'s ``$context`` allow-list must be canonical result_keys.

    ``$context.<token>`` references address prior results by result_key, so every
    allowed token MUST be a canonical result_key — a singular name or a legacy
    alias (``drive``) would reject legitimate references (e.g. ``$context.files``).
    """
    offenders = sorted(
        token for token in VALID_CONTEXT_REFERENCE_DOMAINS if token not in CANONICAL_RESULT_KEYS
    )
    assert not offenders, (
        "VALID_CONTEXT_REFERENCE_DOMAINS must contain canonical result_keys only. "
        f"Off-vocabulary: {offenders}"
    )


def test_context_resolution_data_key_map_values_are_result_keys() -> None:
    """The turn-domain detection map must return canonical result_keys.

    Its value is compared against ``item.meta.domain`` / ``_derive_domain_from_type``
    (both result_keys) in STRATEGY 3; a singular or legacy value never matches.
    """
    offenders = {
        data_key: value
        for data_key, value in _DATA_KEY_TO_RESULT_KEY.items()
        if value not in CANONICAL_RESULT_KEYS
    }
    assert not offenders, (
        "_DATA_KEY_TO_RESULT_KEY values must be canonical result_keys. "
        f"Off-vocabulary: {offenders}"
    )


# ===========================================================================
# (b) Tolerant, non-orphan guards — definitional / display tables
# ===========================================================================


def test_type_domain_map_tokens_resolve_to_canonical() -> None:
    """Every ``TYPE_TO_DOMAIN_MAP`` value resolves to a canonical/auxiliary token.

    The singular element must be a canonical domain name (or a declared
    auxiliary type); the result-key element must be a canonical result_key (or
    a declared auxiliary type).
    """
    singular_vocab = CANONICAL_DOMAINS | AUXILIARY_TYPES
    result_key_vocab = CANONICAL_RESULT_KEYS | AUXILIARY_TYPES
    offenders: dict[str, str] = {}
    for type_name, (singular, result_key) in TYPE_TO_DOMAIN_MAP.items():
        if singular not in singular_vocab:
            offenders[f"{type_name}[domain]"] = singular
        if result_key not in result_key_vocab:
            offenders[f"{type_name}[result_key]"] = result_key
    assert not offenders, (
        "TYPE_TO_DOMAIN_MAP tokens must resolve to a canonical domain / result_key "
        f"or a declared auxiliary type. Off-vocabulary: {offenders}"
    )


def test_context_domain_constants_resolve_to_canonical() -> None:
    """Every ``CONTEXT_DOMAIN_*`` constant is a canonical result_key/auxiliary type.

    ``CONTEXT_DOMAIN_*`` are the ``$steps``/``structured_data`` keys and live on
    the result-key axis.
    """
    context_domain_values = {
        name: value
        for name, value in vars(agent_constants).items()
        if name.startswith("CONTEXT_DOMAIN_") and isinstance(value, str)
    }
    # Sanity: the constants exist (guards against a silent rename/removal).
    assert context_domain_values, "No CONTEXT_DOMAIN_* constants found to validate"
    offenders = {
        name: value
        for name, value in context_domain_values.items()
        if value not in ACCEPTED_DOMAIN_TOKENS
    }
    assert not offenders, (
        "CONTEXT_DOMAIN_* must be a canonical result_key or a declared auxiliary "
        f"type. Off-vocabulary: {offenders}"
    )


def test_html_renderer_component_keys_resolve_to_canonical() -> None:
    """Every ``HtmlRenderer`` component key resolves to a canonical/auxiliary/legacy token.

    The renderer is keyed on the result-key axis but keeps singular and legacy
    aliases as defensive rendering fallbacks. A brand-new key outside the whole
    accepted display vocabulary is a typo and must fail.
    """
    keys = set(HtmlRenderer()._components)
    offenders = sorted(key for key in keys if key not in ACCEPTED_DISPLAY_TOKENS)
    assert not offenders, (
        "HtmlRenderer component keys must resolve to a canonical domain, result_key, "
        f"auxiliary type or a declared legacy display alias. Off-vocabulary: {offenders}"
    )
