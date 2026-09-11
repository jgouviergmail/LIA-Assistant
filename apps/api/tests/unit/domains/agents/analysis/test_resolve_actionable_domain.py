"""``resolve_actionable_domain`` — the one declaration of an actionable turn.

Table-driven over the two shapes a checkpointed route arrives in (object and
msgpack dict), the router's closed vocabulary, and the domain resolution.
"""

from __future__ import annotations

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.analysis.query_intelligence_helpers import resolve_actionable_domain
from src.domains.agents.constants import INTENTION_ACTION, INTENTION_CONVERSATION
from src.domains.agents.domain_schemas import RouterOutput

pytestmark = pytest.mark.unit


def _qi(primary: str = "email") -> dict:
    return QueryIntelligence(
        original_query="q",
        english_query="q",
        immediate_intent="search",
        immediate_confidence=0.9,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="r",
        domains=[primary],
        primary_domain=primary,
    ).to_serializable_dict()


def _route(intention: str) -> RouterOutput:
    return RouterOutput(
        intention=intention, confidence=0.9, context_label="general", next_node="planner"
    )


class TestResolveActionableDomain:
    def test_action_route_with_domain_resolves(self) -> None:
        state = {"routing_history": [_route(INTENTION_ACTION)], "query_intelligence": _qi()}
        assert resolve_actionable_domain(state) == "email"

    def test_dict_route_after_a_checkpoint_round_trip_resolves_too(self) -> None:
        # LangGraph checkpoints round-trip through msgpack: the last route can
        # arrive as a plain dict — the reader must not depend on the object.
        state = {
            "routing_history": [_route(INTENTION_ACTION).model_dump()],
            "query_intelligence": _qi("event"),
        }
        assert resolve_actionable_domain(state) == "event"

    def test_conversation_route_is_not_actionable(self) -> None:
        state = {
            "routing_history": [_route(INTENTION_CONVERSATION)],
            "query_intelligence": _qi(),
        }
        assert resolve_actionable_domain(state) is None

    def test_last_route_wins_over_older_ones(self) -> None:
        state = {
            "routing_history": [_route(INTENTION_ACTION), _route(INTENTION_CONVERSATION)],
            "query_intelligence": _qi(),
        }
        assert resolve_actionable_domain(state) is None

    def test_an_unregistered_domain_is_not_actionable(self) -> None:
        """The domain becomes a Redis key tail and a word the heartbeat
        quotes: a model's stray spelling is refused here, on the same rule
        the product-outcomes capture applies (cold review, 2026-09-11)."""
        from src.domains.agents.registry.domain_bounds import is_registered_domain

        assert is_registered_domain("email") is True
        assert is_registered_domain("emails; DROP *") is False
        assert is_registered_domain(None) is False
        state = {
            "routing_history": [_route(INTENTION_ACTION)],
            "query_intelligence": _qi("not_a_domain"),
        }
        assert resolve_actionable_domain(state) is None

    def test_no_route_or_no_domain_is_none(self) -> None:
        assert resolve_actionable_domain({"query_intelligence": _qi()}) is None
        assert (
            resolve_actionable_domain({"routing_history": [], "query_intelligence": _qi()}) is None
        )
        assert resolve_actionable_domain({"routing_history": [_route(INTENTION_ACTION)]}) is None

    def test_the_producer_never_emits_the_key_the_old_reader_asked_for(self) -> None:
        """Pins the root cause: the serialized intelligence has no ``intent``."""
        assert "intent" not in _qi()
        assert "immediate_intent" in _qi()
