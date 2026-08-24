"""T8: what the admin UI is offered is exactly what the API accepts (ADR-245).

The published-vs-enforced contract of ADR-184, applied to reasoning. Before
this, ``GET /llm-config/metadata`` published the CATALOGUE columns
(``reasoning_widget`` + ``reasoning_enum_values``) while the write path
validated against something else -- which is how the UI came to offer
``minimal`` on ``gpt-5.2``, whose API refuses it.

Every level this payload offers is fed to ``validate_reasoning_effort``, and
every level it withholds is fed to it too. The first set must be accepted and
the second rejected: whatever a validator can reject, its producer must be able
to read.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from src.core.reasoning_intent import LEVELS, ReasoningIntent
from src.domains.llm_config.reasoning_validation import validate_reasoning_effort
from src.domains.llm_config.service import LLMConfigService

pytestmark = pytest.mark.unit


def _profile(model_id: str, declared: list[str] | None = None) -> SimpleNamespace:
    """A cached ``ModelProfile`` stand-in, with the catalogue's optional ladder."""
    return SimpleNamespace(
        model_id=model_id,
        reasoning_enum_values=declared,
        reasoning_doc_i18n_key=None,
        max_output_tokens=32768,
    )


def _catalogue_pairs() -> list[tuple[str, str]]:
    """(provider, model) for every code default, plus the shapes they miss."""
    from src.domains.llm_config.constants import LLM_DEFAULTS

    pairs = {(cfg.provider, cfg.model) for cfg in LLM_DEFAULTS.values() if cfg.model}
    pairs.update(
        {
            ("anthropic", "claude-opus-4-5"),  # budget family
            ("gemini", "gemini-3.5-flash"),  # mandatory reasoning (can_disable=False)
            ("deepseek", "deepseek-v4-flash"),  # toggle family
            ("perplexity", "sonar-reasoning-pro"),  # always-on family
            ("openai", "gpt-4.1"),  # negative rule
        }
    )
    return sorted(pairs)


@pytest.mark.parametrize(("provider", "model"), _catalogue_pairs())
def test_every_offered_level_is_accepted_by_the_validator(provider: str, model: str) -> None:
    payload = LLMConfigService._reasoning_metadata(provider, _profile(model))
    caps = _profile(model)
    for level in payload["reasoning_levels"]:
        validate_reasoning_effort(caps, ReasoningIntent(level=level), provider)


@pytest.mark.parametrize(("provider", "model"), _catalogue_pairs())
def test_every_withheld_level_is_refused_by_the_validator(provider: str, model: str) -> None:
    """The other half of the contract: the UI hides nothing the API would take.

    A level absent from the payload but accepted by the API would be a
    capability the admin cannot reach -- the mirror image of the ``minimal``
    bug, and just as invisible.
    """
    payload = LLMConfigService._reasoning_metadata(provider, _profile(model))
    offered = set(payload["reasoning_levels"])
    if not offered:
        return  # a non-reasoning model refuses everything; covered below
    caps = _profile(model)
    for level in LEVELS:
        if level in offered or level == "provider_default":
            continue
        with pytest.raises(HTTPException):
            validate_reasoning_effort(caps, ReasoningIntent(level=level), provider)


@pytest.mark.parametrize(("provider", "model"), _catalogue_pairs())
def test_the_published_ladder_is_ascending(provider: str, model: str) -> None:
    """The dropdown renders the payload in order, so the payload IS the order.

    ``none`` is prepended when the model can be switched off, which is only
    correct because it sits below every depth on the ordinal ladder. Asserting
    the property rather than the insertion point catches a family declared out
    of order too.
    """
    from src.core.reasoning_intent import level_ordinal

    levels = LLMConfigService._reasoning_metadata(provider, _profile(model))["reasoning_levels"]
    ordinals = [level_ordinal(level) for level in levels]
    assert ordinals == sorted(ordinals), levels
    assert len(set(levels)) == len(levels), f"duplicate level published: {levels}"
    assert "provider_default" not in levels, "the identity is not a depth"


def test_a_non_reasoning_model_offers_nothing() -> None:
    payload = LLMConfigService._reasoning_metadata("openai", _profile("gpt-4.1"))
    assert payload["reasoning_levels"] == []
    assert payload["reasoning_family"] == "none"


def test_a_mandatory_reasoning_model_does_not_offer_off() -> None:
    """``gemini-3.5-flash`` cannot stop thinking; offering 'none' would misprice it."""
    payload = LLMConfigService._reasoning_metadata("gemini", _profile("gemini-3.5-flash"))
    assert payload["reasoning_levels"], "the model reasons, so it must offer levels"
    assert "none" not in payload["reasoning_levels"]
    assert payload["reasoning_can_disable"] is False


def test_a_narrowed_ladder_still_offers_off() -> None:
    """A catalogue row narrows DEPTHS, never the ability to turn reasoning off."""
    payload = LLMConfigService._reasoning_metadata(
        "anthropic", _profile("claude-opus-4-6", declared=["low", "medium", "high", "max"])
    )
    assert payload["reasoning_levels"][0] == "none"
    assert payload["reasoning_can_disable"] is True


def test_the_budget_range_published_is_the_one_enforced() -> None:
    """Publishing a different range than the validator enforces is the ADR-184 trap."""
    payload = LLMConfigService._reasoning_metadata("anthropic", _profile("claude-opus-4-5"))
    assert payload["reasoning_supports_budget"] is True
    published = payload["reasoning_budget_range"]
    assert published is not None
    caps = _profile("claude-opus-4-5")
    validate_reasoning_effort(caps, ReasoningIntent(budget_tokens=published.min), "anthropic")
    validate_reasoning_effort(caps, ReasoningIntent(budget_tokens=published.max), "anthropic")
    for outside in (published.min - 1, published.max + 1):
        with pytest.raises(HTTPException):
            validate_reasoning_effort(caps, ReasoningIntent(budget_tokens=outside), "anthropic")


def test_the_payload_publishes_the_bounds_and_nothing_else() -> None:
    """No always-null sentinel travels on this endpoint.

    ``off_sentinel`` / ``dynamic_sentinel`` belonged to the budget widget
    ADR-245 removed; they still exist on the CATALOGUE type, which the model
    admin edits. Shipping them here as two permanent nulls is how a demoted
    concept gets read again by mistake.
    """
    payload = LLMConfigService._reasoning_metadata("anthropic", _profile("claude-opus-4-5"))
    published = payload["reasoning_budget_range"]
    assert published is not None
    assert set(published.model_dump()) == {"min", "max"}


def test_a_level_family_publishes_no_budget_range() -> None:
    """Offering a budget input the API would 422 is the same trap, mirrored."""
    payload = LLMConfigService._reasoning_metadata("openai", _profile("gpt-5.2"))
    assert payload["reasoning_supports_budget"] is False
    assert payload["reasoning_budget_range"] is None
    with pytest.raises(HTTPException):
        validate_reasoning_effort(
            _profile("gpt-5.2"), ReasoningIntent(budget_tokens=1024), "openai"
        )


def test_exclude_from_output_is_advertised_only_where_it_reaches_the_provider() -> None:
    """Derived from the renderers, so the switch cannot outlive the kwarg."""
    gemini: Any = LLMConfigService._reasoning_metadata("gemini", _profile("gemini-3.5-pro"))
    openai: Any = LLMConfigService._reasoning_metadata("openai", _profile("gpt-5.2"))
    assert gemini["reasoning_supports_exclude"] is True
    assert openai["reasoning_supports_exclude"] is False


def test_a_discovered_model_with_no_catalogue_row_publishes_an_empty_ladder() -> None:
    """Live Ollama discovery: no row, no rule -- and the translator emits nothing."""
    payload = LLMConfigService._reasoning_metadata("ollama", None)
    assert payload["reasoning_levels"] == []
    assert payload["reasoning_doc_i18n_key"] is None
