"""Whether this answer may carry a habit proposal card, and how it reaches the stream (ADR-375).

The choice of the proposal is habits' (``habits.chat_proposal``, proven on
PostgreSQL); what is pinned here is the turn's side: no card under a run
nobody typed, under rows that stay out of the chat or on a surface that draws
no card; the turn's own domain handed to the choice; the card handed to the
stream on the chips' channel; and an answer that never pays for a card that
could not be had.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from src.domains.agents.nodes import turn_proposal
from src.domains.agents.nodes.turn_proposal import resolve_turn_proposal
from src.domains.agents.services.streaming.followup_metadata import (
    NO_TURN_EXTRAS,
    pop_turn_extras,
)
from src.domains.habits.models import ProposalKind
from src.domains.habits.proposal_facts import AutomateNeedFacts
from src.domains.habits.proposal_schemas import HabitProposalResponse

pytestmark = pytest.mark.unit

USER = uuid4()
PROPOSAL = HabitProposalResponse(
    id=uuid4(),
    kind=ProposalKind.AUTOMATE_NEED,
    key="weather",
    facts=AutomateNeedFacts(
        domain="weather",
        cadence="weekdays",
        hour=7,
        minute=30,
        distinct_days=14,
        active_days=22,
        part_of_day="morning",
    ),
    created_at=datetime(2026, 11, 1, tzinfo=UTC),
    updated_at=datetime(2026, 11, 7, tzinfo=UTC),
)
# The router's own record of an actionable turn on the weather domain.
ACTION_ON_WEATHER: dict[str, Any] = {
    "routing_history": [{"intention": "action"}],
    "query_intelligence": {"primary_domain": "weather"},
}


@pytest.fixture
def turn(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A typed chat turn whose card reaches the person, and a recording claim."""
    state: dict[str, Any] = {
        "context": SimpleNamespace(user_id=USER, is_automated_source=False),
        "reaches": True,
        "claimed": [],
        "answer": PROPOSAL,
    }

    async def claim(user_id: Any, domain: str | None, *, settings: Any, now: datetime) -> Any:
        state["claimed"].append((user_id, domain))
        if isinstance(state["answer"], Exception):
            raise state["answer"]
        return state["answer"]

    monkeypatch.setattr(turn_proposal, "runtime_context_if_running", lambda: state["context"])
    monkeypatch.setattr(turn_proposal, "chat_cards_reach_the_person", lambda: state["reaches"])
    monkeypatch.setattr(turn_proposal, "claim_chat_proposal", claim)
    return state


async def test_the_card_reaches_the_stream_as_the_proposals_json(turn: dict[str, Any]) -> None:
    await resolve_turn_proposal(ACTION_ON_WEATHER, "run-card")

    assert turn["claimed"] == [(USER, "weather")]
    assert pop_turn_extras("run-card").habit_proposal == PROPOSAL.model_dump(mode="json")


async def test_a_turn_with_no_actionable_domain_still_asks_without_one(
    turn: dict[str, Any],
) -> None:
    await resolve_turn_proposal({"routing_history": [{"intention": "conversation"}]}, "run-chat")

    assert turn["claimed"] == [(USER, None)]
    pop_turn_extras("run-chat")


async def test_nothing_to_show_hands_nothing(turn: dict[str, Any]) -> None:
    turn["answer"] = None

    await resolve_turn_proposal(ACTION_ON_WEATHER, "run-empty")

    assert pop_turn_extras("run-empty") == NO_TURN_EXTRAS


@pytest.mark.parametrize(
    "closed",
    ["outside_a_run", "a_routine", "rows_out_of_the_chat"],
)
async def test_a_turn_that_cannot_show_a_card_never_claims_one(
    turn: dict[str, Any], closed: str
) -> None:
    if closed == "outside_a_run":
        turn["context"] = None
    elif closed == "a_routine":
        turn["context"] = SimpleNamespace(user_id=USER, is_automated_source=True)
    else:
        turn["reaches"] = False

    await resolve_turn_proposal(ACTION_ON_WEATHER, f"run-{closed}")

    assert turn["claimed"] == []
    assert pop_turn_extras(f"run-{closed}") == NO_TURN_EXTRAS


async def test_a_failing_claim_costs_the_answer_nothing(turn: dict[str, Any]) -> None:
    turn["answer"] = RuntimeError("database unreachable")

    await resolve_turn_proposal(ACTION_ON_WEATHER, "run-broken")

    assert pop_turn_extras("run-broken") == NO_TURN_EXTRAS
