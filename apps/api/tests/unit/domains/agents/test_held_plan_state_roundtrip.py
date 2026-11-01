"""The resume's two state keys are declared, survive the checkpoint and reset per turn (spec D7).

A key a node writes and ``MessagesState`` does not declare is dropped in silence
by LangGraph; a value that does not survive the msgpack round trip is lost at the
HITL resume — the very moment these two keys exist for; and a value a new turn
does not reset is inherited by it.
"""

from __future__ import annotations

from typing import Any, get_type_hints

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.draft_sequence import draft_turn_reset

pytestmark = [pytest.mark.unit]

HELD_PLAN: dict[str, Any] = {
    "plan_id": "plan-1",
    "held": {"s2": ["draft_a"], "s3": ["draft_a", "draft_b"]},
    "ordered": ["s3"],
    "pending": {"s1": ["draft_a"], "s4": ["draft_b"]},
    "resumed": ["s5"],
    "not_run": {"s6": "refused"},
}
EXECUTED_DRAFTS: dict[str, Any] = {
    "draft_a": {
        "status": "success",
        "data": {"deleted_id": "n-42", "_draft_content": {"tool_args": {"note_id": "n-42"}}},
        "message": "Done",
        "draft_id": "draft_a",
        "draft_type": "tool_call",
        "action": "confirm",
    }
}


class TestTheResumeKeys:
    def test_both_keys_are_declared(self) -> None:
        declared = get_type_hints(MessagesState, include_extras=True)

        assert "held_plan" in declared and "executed_drafts" in declared

    def test_held_plan_round_trips(self) -> None:
        serializer = JsonPlusSerializer()
        state = {"held_plan": HELD_PLAN, "executed_drafts": EXECUTED_DRAFTS}

        restored = serializer.loads_typed(serializer.dumps_typed(state))

        assert restored == state

    def test_a_new_turn_starts_with_neither(self) -> None:
        reset = draft_turn_reset()

        assert reset["held_plan"] is None
        assert reset["executed_drafts"] == {}
