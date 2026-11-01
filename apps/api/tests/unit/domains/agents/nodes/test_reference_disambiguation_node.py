"""« Which of the items shown did you mean? » — asked before planning (ADR-367).

Production 2026-10-29: « reply to jerome's email » after a list holding several
of his e-mails drafted a reply to one the person had never been shown. When a
description fits several shown items, the turn now asks which one — a template
question, an answer read without a model — and only then plans.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from prometheus_client import REGISTRY

from src.domains.agents.analysis.query_intelligence_helpers import STATE_KEY_QUERY_INTELLIGENCE
from src.domains.agents.constants import (
    NODE_PLANNER,
    NODE_REACT_SETUP,
    NODE_REFERENCE_DISAMBIGUATION,
    NODE_RESPONSE,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_RESOLVED_CONTEXT,
    STATE_KEY_TURN_TYPE,
    TURN_TYPE_REFERENCE_ACTION,
)
from src.domains.agents.graph import route_from_reference_disambiguation
from src.domains.agents.nodes.reference_disambiguation_node import (
    CHOICE_DECLINED_REASON,
    asks_which_item,
    reference_disambiguation_node,
)
from src.domains.agents.services.reference_resolver import ResolvedContext
from src.domains.agents.tools import emails_tools  # noqa: F401 — registers "emails"

pytestmark = pytest.mark.unit

INTERRUPT = "src.domains.agents.nodes.reference_disambiguation_node.interrupt"

CANDIDATES = [
    {
        "id": "m1",
        "from": "Marc Dubois <marc@example.com>",
        "subject": "Photos du week-end",
        "to": "me@example.net",
        "date_formatted": "mardi 15 septembre 2026 à 17:24",
    },
    {
        "id": "m3",
        "from": "Marc Dubois <marc@example.com>",
        "subject": "Facture du garage",
        "to": "me@example.net",
        "date_formatted": "lundi 14 septembre 2026 à 09:12",
    },
]


def _state(**extra: Any) -> dict[str, Any]:
    context = ResolvedContext(
        items=[],
        confidence=1.0,
        method="descriptive_ambiguous",
        source_turn_id=None,
        source_domain="email",
        candidates=list(CANDIDATES),
        descriptor="Marc",
    )
    return {
        STATE_KEY_RESOLVED_CONTEXT: context.to_dict(),
        STATE_KEY_QUERY_INTELLIGENCE: {"immediate_intent": "send", "turn_type": "ACTION"},
        "user_language": "fr",
        **extra,
    }


def _count(outcome: str) -> float:
    return (
        REGISTRY.get_sample_value("context_disambiguation_answers_total", {"outcome": outcome})
        or 0.0
    )


async def _answered(*answers: object, state: dict[str, Any] | None = None) -> tuple[dict, list]:
    asked: list[dict[str, Any]] = []
    replies = iter(answers)

    def _interrupt(payload: dict[str, Any]) -> object:
        asked.append(payload)
        return next(replies)

    with patch(INTERRUPT, side_effect=_interrupt):
        result = await reference_disambiguation_node(state or _state(), config={})
    return result, asked


class TestTheQuestion:
    async def test_it_numbers_the_options_by_what_tells_them_apart(self) -> None:
        _, asked = await _answered({"action": "select", "selected_index": 1})

        (payload,) = asked
        (request,) = payload["action_requests"]
        assert request["type"] == "entity_disambiguation"
        assert request["descriptor"] == "Marc"
        assert request["reask"] is False
        assert [c["label"] for c in request["candidates"]] == [
            "Marc Dubois <marc@example.com> · Photos du week-end · mardi 15 septembre 2026 à 17:24",
            "Marc Dubois <marc@example.com> · Facture du garage · lundi 14 septembre 2026 à 09:12",
        ]
        assert payload["generate_question_streaming"] is True
        assert payload["hitl_type"] == "entity_disambiguation"
        assert payload["user_language"] == "fr"

    async def test_nothing_is_asked_without_candidates(self) -> None:
        resolved = ResolvedContext(
            items=[CANDIDATES[0]], confidence=1.0, method="descriptive", source_turn_id=1
        )
        with patch(INTERRUPT) as interrupt:
            result = await reference_disambiguation_node(
                {STATE_KEY_RESOLVED_CONTEXT: resolved.to_dict()}, config={}
            )
        assert result == {}
        interrupt.assert_not_called()


class TestTheAnswer:
    async def test_a_choice_becomes_the_turns_one_item(self) -> None:
        before = _count("select")
        result, _ = await _answered({"action": "select", "selected_index": 2})

        context = ResolvedContext.from_dict(result[STATE_KEY_RESOLVED_CONTEXT])
        assert context.items == [CANDIDATES[1]] and context.candidates == []
        assert context.source_domain == "email"
        assert result[STATE_KEY_TURN_TYPE] == TURN_TYPE_REFERENCE_ACTION
        # The planner reconstructs its intelligence from this dict.
        assert result[STATE_KEY_QUERY_INTELLIGENCE]["turn_type"] == "REFERENCE_ACTION"
        assert result[STATE_KEY_QUERY_INTELLIGENCE]["immediate_intent"] == "send"
        assert _count("select") == before + 1

    async def test_none_of_them_plans_a_new_lookup(self) -> None:
        result, _ = await _answered({"action": "none"})

        assert result == {STATE_KEY_RESOLVED_CONTEXT: None}

    async def test_a_refusal_ends_the_turn_with_nothing_done(self) -> None:
        result, _ = await _answered({"action": "cancel"})

        assert result[STATE_KEY_RESOLVED_CONTEXT] is None
        assert result[STATE_KEY_PLAN_APPROVED] is False
        assert result[STATE_KEY_PLAN_REJECTION_REASON] == CHOICE_DECLINED_REASON

    async def test_an_unclear_answer_is_asked_about_once_more(self) -> None:
        before = _count("select_after_reask")
        result, asked = await _answered(
            {"action": "unclear"}, {"action": "select", "selected_index": 1}
        )

        assert [p["action_requests"][0]["reask"] for p in asked] == [False, True]
        assert ResolvedContext.from_dict(result[STATE_KEY_RESOLVED_CONTEXT]).items == [
            CANDIDATES[0]
        ]
        assert _count("select_after_reask") == before + 1

    async def test_two_unclear_answers_cancel_never_guess(self) -> None:
        before = _count("unclear")
        result, asked = await _answered({"action": "unclear"}, {"action": "select"})

        assert len(asked) == 2
        assert result[STATE_KEY_PLAN_REJECTION_REASON] == CHOICE_DECLINED_REASON
        assert _count("unclear") == before + 1

    async def test_an_index_outside_the_options_is_unclear(self) -> None:
        _, asked = await _answered(
            {"action": "select", "selected_index": 7}, {"action": "select", "selected_index": 2}
        )
        assert len(asked) == 2


class TestTheRoutes:
    def test_the_router_asks_first_only_when_several_items_fit(self) -> None:
        assert asks_which_item(_state())
        chosen = ResolvedContext(
            items=[CANDIDATES[0]], confidence=1.0, method="x", source_turn_id=1
        )
        assert not asks_which_item({STATE_KEY_RESOLVED_CONTEXT: chosen.to_dict()})
        assert not asks_which_item({STATE_KEY_RESOLVED_CONTEXT: None})

    def test_a_choice_goes_on_to_the_planner_of_the_turns_mode(self) -> None:
        assert route_from_reference_disambiguation({}) == NODE_PLANNER
        with patch("src.domains.agents.graph.settings.react_agent_enabled", True):
            assert route_from_reference_disambiguation({"execution_mode": "react"}) == (
                NODE_REACT_SETUP
            )

    def test_a_declined_choice_goes_to_the_response(self) -> None:
        state = {STATE_KEY_PLAN_REJECTION_REASON: CHOICE_DECLINED_REASON}
        assert route_from_reference_disambiguation(state) == NODE_RESPONSE

    def test_the_question_is_a_step_of_the_route_not_another_route(self) -> None:
        from types import SimpleNamespace

        from src.domains.agents.graph import route_from_router

        decision = SimpleNamespace(intention="actionable", confidence=0.99, next_node=NODE_PLANNER)
        with patch("src.domains.agents.graph.note_route") as note_route:
            next_node = route_from_router(_state(routing_history=[decision]))

        assert next_node == NODE_REFERENCE_DISAMBIGUATION
        note_route.assert_called_once_with(NODE_PLANNER)

    def test_a_conversational_turn_is_never_diverted(self) -> None:
        from types import SimpleNamespace

        from src.domains.agents.graph import route_from_router

        decision = SimpleNamespace(
            intention="conversation", confidence=0.99, next_node=NODE_RESPONSE
        )
        assert route_from_router(_state(routing_history=[decision])) == NODE_RESPONSE
