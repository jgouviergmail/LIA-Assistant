"""The ReAct loop reads each earlier turn with when the person wrote it (lot 17)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.nodes.react_history import window_messages_for_react
from src.infrastructure.llm.message_view import stamped_now
from tests.unit.domains.agents.nodes.test_react_history_prefix_stability import (
    PROMPT,
)
from tests.unit.domains.agents.nodes.test_react_history_prefix_stability import (
    sent as sent,
)

pytestmark = pytest.mark.unit


def _loop_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What the call node reads besides the thread (the stability harness's own)."""
    return {
        "exchange_rhythm": "occasional",
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_system_blocks": [PROMPT],
        "react_iteration": 0,
        "react_max_iterations_effective": 70,
        "react_elapsed_seconds": 0.0,
        "react_recovery_passes": [],
    }


TUESDAY = datetime(2026, 11, 10, 0, 12, tzinfo=UTC)  # 09:12 in Tokyo
FRIDAY = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)


def _thread() -> list[Any]:
    return [
        stamped_now(HumanMessage("I have the dentist tomorrow at 10.", id="h1"), TUESDAY),
        AIMessage("Noted.", id="a1"),
        stamped_now(HumanMessage("Is it still ahead of me?", id="h2"), FRIDAY),
    ]


def test_earlier_turns_carry_when_the_person_wrote_them_in_their_zone() -> None:
    windowed = window_messages_for_react(_thread(), turn_id=2, zone="Asia/Tokyo")

    assert windowed[0].content == "[Tue 10 Nov 2026, 09:12] I have the dentist tomorrow at 10."
    assert windowed[1].content == "Noted."


def test_the_question_reads_the_same_bytes_as_current_and_as_earlier() -> None:
    """The next turn reads this turn's prompt back through its question (ADR-309):
    a question stamped only once it is earlier would change its bytes and miss the
    cache the frequent rhythm writes."""
    asked = window_messages_for_react(_thread(), turn_id=2, zone="Asia/Tokyo")
    follow_up = stamped_now(HumanMessage("And the one after?", id="h3"), FRIDAY)
    next_turn = window_messages_for_react(
        [*_thread(), AIMessage("Yes.", id="a2"), follow_up], turn_id=3, zone="Asia/Tokyo"
    )

    assert asked[-1].content == "[Fri 13 Nov 2026, 18:30] Is it still ahead of me?"
    assert next_turn[2].content == asked[-1].content


async def test_the_loop_writes_the_moment_in_the_zone_its_state_holds(
    sent: list[list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.agents.nodes import react_nodes

    state = {
        **_loop_state(monkeypatch),
        "messages": _thread(),
        "current_turn_id": 2,
        "user_timezone": "Asia/Tokyo",
    }

    await react_nodes.react_call_model_node(state, config={})

    contents = [str(message.content) for message in sent[0]]
    assert "[Tue 10 Nov 2026, 09:12] I have the dentist tomorrow at 10." in contents
    assert "[Fri 13 Nov 2026, 18:30] Is it still ahead of me?" in contents


def test_the_stamped_history_is_the_same_bytes_on_every_call_of_a_turn() -> None:
    """A cached prefix survives: nothing in a stamp depends on the call."""
    first = window_messages_for_react(_thread(), turn_id=2, zone="Asia/Tokyo")
    second = window_messages_for_react(_thread(), turn_id=2, zone="Asia/Tokyo")

    assert [message.content for message in first] == [message.content for message in second]
