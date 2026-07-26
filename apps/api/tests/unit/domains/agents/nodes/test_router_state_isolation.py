"""The router decides; it never writes to the conversation.

The router's decision is a structured `RouterOutput`. If it ever leaked into
``state["messages"]``, the user would read raw routing JSON in their chat —
``{"intention": "action", "confidence": 0.9, ...}`` — instead of an answer.

That invariant used to be checked only by end-to-end tests that invoked the
whole graph against a real provider (``tests/unit/test_router_state.py``), so
in practice it was never checked at all: every one of them was skipped for want
of an API key. The invariant is a property of ONE node's return value, and that
is testable here, hermetically, in milliseconds.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.constants import (
    STATE_KEY_MESSAGES,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.nodes.router_node_v3 import get_router_v3_edge, router_node_v3

pytestmark = pytest.mark.unit


def _intelligence(**overrides: Any) -> QueryIntelligence:
    """A REAL QueryIntelligence — the router serializes it into the state.

    A duck-typed stand-in silently omits `to_serializable_dict()`, which the
    router calls to persist the analysis; using the production dataclass keeps
    that contract honest (and the state round-trip representative).
    """
    base: dict[str, Any] = {
        "original_query": "cherche jean",
        "english_query": "find jean",
        "immediate_intent": "search",
        "immediate_confidence": 0.9,
        "user_goal": next(iter(UserGoal)),
        "goal_reasoning": "the user is looking for a contact",
        "domains": ["contact"],
        "primary_domain": "contact",
        "turn_type": "ACTION",
        "route_to": "planner",
        "confidence": 0.9,
        "reasoning_trace": ["domain=contact", "intent=search", "route=planner"],
    }
    base.update(overrides)
    return QueryIntelligence(**base)


@pytest.fixture
def analyzer() -> MagicMock:
    """Stub QueryAnalyzerService — the router's only collaborator."""
    service = MagicMock()
    service.analyze_full = AsyncMock(return_value=_intelligence())
    return service


@pytest.fixture(autouse=True)
def patched_analyzer(analyzer: MagicMock):
    """Route every `get_query_analyzer_service()` call to the stub.

    The router imports it lazily inside the coroutine, so the source module is
    the correct patch target.
    """
    with patch(
        "src.domains.agents.services.query_analyzer_service.get_query_analyzer_service",
        return_value=analyzer,
    ):
        yield analyzer


def _state(*messages: Any) -> dict[str, Any]:
    """Minimal state: the router only reads the message list."""
    return {STATE_KEY_MESSAGES: list(messages)}


def _config() -> dict[str, Any]:
    return {"configurable": {"run_id": "run-test"}, "metadata": {"run_id": "run-test"}}


class TestRouterDoesNotTouchMessages:
    """The core invariant."""

    async def test_state_update_carries_no_messages_key(self) -> None:
        """A `messages` key here would be MERGED into the conversation."""
        update = await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        assert STATE_KEY_MESSAGES not in update, (
            "the router returned a messages update — its routing decision would "
            "be appended to the user's chat"
        )

    async def test_decision_lands_in_routing_history(self) -> None:
        """Where it does belong: an append-only decision log."""
        update = await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        history = update[STATE_KEY_ROUTING_HISTORY]
        assert len(history) == 1
        decision = history[0]
        assert decision.intention == "action"
        assert decision.next_node == "planner"
        assert decision.context_label == "contact"
        assert decision.domains == ["contact"]

    async def test_history_appends_rather_than_replaces(self) -> None:
        """A turn must not erase the previous turns' decisions."""
        previous = MagicMock()
        state = _state(HumanMessage(content="et maintenant ?"))
        state[STATE_KEY_ROUTING_HISTORY] = [previous]

        update = await router_node_v3(state, _config())

        history = update[STATE_KEY_ROUTING_HISTORY]
        assert len(history) == 2
        assert history[0] is previous

    async def test_no_routing_field_leaks_into_any_message(self) -> None:
        """Belt and braces: the raw JSON keys must appear nowhere in messages.

        This is the shape the end-to-end tests asserted on the final answer;
        asserting it on the node's own output catches the leak at its source.
        """
        original = [HumanMessage(content="cherche jean"), AIMessage(content="D'accord.")]
        update = await router_node_v3(_state(*original), _config())

        emitted = " ".join(
            str(getattr(message, "content", "")) for message in update.get(STATE_KEY_MESSAGES, [])
        )
        for key in ("intention", "confidence", "context_label", "next_node", "reasoning"):
            assert f'"{key}"' not in emitted


class TestRouterClearsPerTurnState:
    """Stale per-turn values are how a previous turn's verdict leaks forward."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("plan_approved", None),
            ("plan_rejection_reason", None),
            ("validation_result", None),
            ("semantic_validation", None),
            ("planner_iteration", 0),
            ("initiative_iteration", 0),
            ("initiative_results", []),
        ],
    )
    async def test_per_turn_key_is_reset(self, key: str, expected: Any) -> None:
        state = _state(HumanMessage(content="cherche jean"))
        state.update(
            {
                "plan_approved": True,
                "plan_rejection_reason": "stale reason",
                "validation_result": {"stale": True},
                "semantic_validation": {"stale": True},
                "planner_iteration": 3,
                "initiative_iteration": 2,
                "initiative_results": [{"stale": True}],
            }
        )

        update = await router_node_v3(state, _config())

        assert update[key] == expected


class TestRouterEdge:
    """The edge reads the decision the node just wrote."""

    def test_edge_follows_the_last_decision(self) -> None:
        decision = MagicMock(next_node="planner")
        assert get_router_v3_edge({STATE_KEY_ROUTING_HISTORY: [decision]}) == "planner"

    def test_edge_defaults_to_response_without_history(self) -> None:
        """Fail-safe: answer the user rather than route nowhere."""
        assert get_router_v3_edge({}) == "response"
        assert get_router_v3_edge({STATE_KEY_ROUTING_HISTORY: []}) == "response"

    def test_edge_defaults_to_response_on_a_decision_without_next_node(self) -> None:
        assert get_router_v3_edge({STATE_KEY_ROUTING_HISTORY: [object()]}) == "response"


class TestRouterQueryExtraction:
    """What the router hands to the analyzer."""

    async def test_last_human_message_is_the_query(self, patched_analyzer: MagicMock) -> None:
        await router_node_v3(
            _state(
                HumanMessage(content="première demande"),
                AIMessage(content="réponse"),
                HumanMessage(content="deuxième demande"),
            ),
            _config(),
        )

        assert "deuxième demande" in str(patched_analyzer.analyze_full.await_args)

    async def test_empty_message_list_does_not_raise(self) -> None:
        """A turn with no message must not crash the graph's entry node."""
        update = await router_node_v3(_state(), _config())

        assert STATE_KEY_ROUTING_HISTORY in update
