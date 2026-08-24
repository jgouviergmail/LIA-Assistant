"""The admin Pricing form must be told what the RUNTIME will accept.

``reasoning_enum_values`` can only NARROW a ladder the code already derives
from ``(provider, model)``. A form that offers a free-text list therefore asks
the operator to declare something they cannot declare, and lets them silently
REMOVE depths by copying a ladder that belongs to another family -- the exact
shape of the ``off`` incident, where four rows declared a level the ladder does
not have and the intersection dropped it in silence.

This endpoint publishes the family's own ladder so the form can render it as a
menu. It resolves WITHOUT the catalogue narrowing on purpose: the narrowing is
what the operator is about to choose, so offering the already-narrowed ladder
would make a saved restriction impossible to widen again.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

pytestmark = pytest.mark.unit


def _payload(provider: str, model: str):  # type: ignore[no-untyped-def]
    """Build the response the router returns, without a DB or a client."""
    from src.domains.llm.router import _reasoning_family_payload

    return _reasoning_family_payload(provider, model)


def test_it_publishes_the_family_ladder_not_the_narrowed_one() -> None:
    """The menu must show every depth the family offers, narrowing excluded."""
    payload = _payload("anthropic", "claude-opus-4-6")

    assert payload.reasoning_family == "anthropic_adaptive"
    assert payload.reasoning_levels == ["none", "low", "medium", "high", "max"]
    assert payload.source == "family"


def test_the_published_ladder_is_the_one_the_runtime_resolves() -> None:
    """One authority: the endpoint calls the translator's own resolver.

    Publishing anything else is how the dropdown came to offer ``minimal`` on a
    model whose API refuses it (ADR-184 applied to reasoning).
    """
    for provider, model in (
        ("anthropic", "claude-opus-4-5"),
        ("openai", "gpt-5.2"),
        ("deepseek", "deepseek-v4-flash"),
    ):
        payload = _payload(provider, model)
        resolved = resolve_reasoning_profile(provider, model)
        assert payload.reasoning_levels == list(resolved.levels), model
        assert payload.reasoning_family == resolved.family, model
        assert payload.reasoning_can_disable is resolved.can_disable, model


def test_a_model_no_rule_matches_says_so_instead_of_offering_nothing() -> None:
    """The confusing case, answered explicitly.

    A model no family rule matches produces NO reasoning kwarg, and its
    declared ladder is never even read. The form has to say that rather than
    render an empty list of checkboxes that looks like a loading bug.
    """
    payload = _payload("openai", "some-model-nobody-has-taught-us")

    assert payload.reasoning_family == "none"
    assert payload.reasoning_levels == []
    assert payload.source == "unknown"


def test_an_empty_model_name_resolves_to_no_family_rather_than_raising() -> None:
    """The form asks while the operator is still typing the model name."""
    payload = _payload("openai", "")

    assert payload.reasoning_family == "none"
    assert payload.reasoning_levels == []


def test_the_budget_bounds_published_are_the_family_s_own() -> None:
    """The bound the validator enforces is the bound the form is shown."""
    payload = _payload("anthropic", "claude-opus-4-5")
    resolved = resolve_reasoning_profile("anthropic", "claude-opus-4-5")

    assert resolved.budget_range is not None
    assert payload.reasoning_supports_budget is True
    assert payload.reasoning_budget_range is not None
    assert (
        payload.reasoning_budget_range.min,
        payload.reasoning_budget_range.max,
    ) == resolved.budget_range
