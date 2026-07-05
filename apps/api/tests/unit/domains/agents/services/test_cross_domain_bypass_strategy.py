"""Behavioral tests for :class:`CrossDomainBypassStrategy` (ADR-102).

These tests pin the cross-domain LLM-bypass fast path:

- ``CROSS_DOMAIN_MAPPINGS`` target domains must be on the singular axis so the
  ``primary_domain == target_domain`` comparison actually matches (the historical
  ``places`` vs ``place`` mismatch left the bypass permanently inert — every
  cross-domain reference query paid ~800 ms of avoidable multi-domain LLM plan).
- The bypass is gated by ``settings.planner_cross_domain_bypass_enabled`` so it
  can be disabled in production without a rebuild.
"""

from __future__ import annotations

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.services.planner.strategies.cross_domain_bypass import (
    CrossDomainBypassStrategy,
)
from src.domains.agents.services.reference_resolver import ResolvedContext


def _restaurant_of_meeting_intelligence(**overrides: object) -> QueryIntelligence:
    """Build the canonical 'restaurant of this meeting' cross-domain reference.

    A calendar event (source domain) was resolved with a ``location`` field, and
    the user now wants to search that location in the ``place`` domain.
    """
    params: dict[str, object] = {
        "original_query": "le restaurant de ce rendez-vous",
        "english_query": "the restaurant of this meeting",
        "immediate_intent": "search",
        "immediate_confidence": 0.9,
        "user_goal": UserGoal.FIND_INFORMATION,
        "goal_reasoning": "cross-domain reference",
        "turn_type": "REFERENCE_ACTION",
        "primary_domain": "place",
        "source_domain": "event",
        "resolved_context": ResolvedContext(
            items=[{"location": "Restaurant La Table"}],
            confidence=0.9,
            method="explicit",
            source_turn_id=1,
            source_domain="event",
        ),
    }
    params.update(overrides)
    return QueryIntelligence(**params)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_can_handle_true_for_cross_domain_reference() -> None:
    """The bypass fires when the resolved item's field maps to the primary domain.

    ``event.location`` maps to the ``place`` domain in ``CROSS_DOMAIN_MAPPINGS``;
    with ``primary_domain == "place"`` the strategy must accept the query and
    bypass the LLM planner.
    """
    strategy = CrossDomainBypassStrategy()
    intelligence = _restaurant_of_meeting_intelligence()

    assert await strategy.can_handle(intelligence) is True


@pytest.mark.asyncio
async def test_plan_bypasses_llm_with_zero_tokens() -> None:
    """The bypass plan is templated (no LLM planner call, zero tokens)."""
    strategy = CrossDomainBypassStrategy()
    intelligence = _restaurant_of_meeting_intelligence()

    result = await strategy.plan(intelligence=intelligence, config={})

    assert result.success is True
    assert result.tokens_used == 0
    assert result.used_template is True
    assert result.plan is not None


@pytest.mark.asyncio
async def test_can_handle_false_when_bypass_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The kill-switch ``planner_cross_domain_bypass_enabled`` disables the bypass.

    With the flag off the strategy must decline even an otherwise-eligible
    cross-domain reference, so the query falls through to the LLM planner
    (behavior unchanged from before the fix).
    """
    from src.core.config import get_settings

    monkeypatch.setattr(get_settings(), "planner_cross_domain_bypass_enabled", False, raising=False)
    strategy = CrossDomainBypassStrategy()
    intelligence = _restaurant_of_meeting_intelligence()

    assert await strategy.can_handle(intelligence) is False
