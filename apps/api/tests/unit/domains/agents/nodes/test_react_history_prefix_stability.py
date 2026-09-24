"""Every call of a ReAct turn resends the previous call's prompt whole (ADR-309, amended).

Measured in production on 2026-09-24, the morning after the flag went live: the
loop's history was dropped by blocks aligned on the LENGTH of the thread, and the
messages reducer trims the thread's head as the turn's own tool results arrive.
Each trim moved the block boundary, so the history's first message changed in
the middle of a turn — the provider read back the prompt and the tools alone and
billed the rest again: 94,403 to 152,869 tokens on three calls of one routine run,
while the thread still held more history than the window shows.

The real node and the real reducer, driven call by call; only the model is
scripted, and the state's token budget is lowered so that the head is trimmed on
every tool result, as production's was.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.core.config import settings
from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.models import add_messages_with_truncate, count_messages_tokens_cached
from src.domains.agents.nodes import react_nodes as rn

pytestmark = pytest.mark.unit

PROMPT = (
    f"You are LIA.\n\n{DYNAMIC_CONTEXT_MARKER} (all variable data below) ---\n\nDate: 2026-09-24"
)
RESULT = "data " * 400  # a tool result of about 400 tokens
PAST_TURNS = 20
LOOP_CALLS = 6


def _past_turn(number: int) -> list[BaseMessage]:
    return [
        HumanMessage(f"question {number}", id=f"h{number}"),
        AIMessage(
            "", id=f"c{number}", tool_calls=[{"id": f"k{number}", "name": "search", "args": {}}]
        ),
        ToolMessage(RESULT, tool_call_id=f"k{number}", id=f"r{number}", name="search"),
        AIMessage(f"answer {number}", id=f"a{number}"),
    ]


def _apply(state: dict[str, Any], update: dict[str, Any]) -> None:
    """Merge a node's update the way the graph does."""
    for key, value in update.items():
        if key == "messages":
            state[key] = add_messages_with_truncate(state[key], value)
        else:
            state[key] = value


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[BaseMessage]]:
    """What the node hands to the model, one list per call; the model always calls a tool."""
    captured: list[list[BaseMessage]] = []
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])
    monkeypatch.setattr(rn, "react_slot_provider", lambda: "deepseek")
    monkeypatch.setattr(settings, "react_agent_history_window_turns", 5)
    monkeypatch.setattr(settings, "react_cross_turn_history_block_fraction", 0.5)
    monkeypatch.setattr(settings, "max_messages_history", 10_000)

    async def fake_stream(
        _llm: Any, messages: list[BaseMessage], emit: Any, config: Any
    ) -> AIMessage:
        captured.append(list(messages))
        call = len(captured)
        return AIMessage(
            "", id=f"loop{call}", tool_calls=[{"id": f"x{call}", "name": "search", "args": {}}]
        )

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )
    return captured


def _thread(turn_id: int, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A thread whose state sits at its token budget, at the start of turn ``turn_id``."""
    messages: list[BaseMessage] = []
    for number in range(1, PAST_TURNS + 1):
        messages += _past_turn(number)
    messages.append(HumanMessage("the routine's question", id="now"))
    monkeypatch.setattr(settings, "max_tokens_history", count_messages_tokens_cached(messages) + 50)
    return {
        "messages": add_messages_with_truncate([], messages),
        "current_turn_id": turn_id,
        "exchange_rhythm": "frequent",
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_system_blocks": [PROMPT],
        "react_iteration": 0,
        "react_max_iterations_effective": 70,
        "react_elapsed_seconds": 0.0,
        "react_recovery_passes": [],
    }


async def _run_loop(state: dict[str, Any], calls: int) -> None:
    """Each call's tool result lands through the reducer, which trims the head."""
    for _ in range(calls):
        update = await rn.react_call_model_node(state, config={})
        _apply(state, update)
        call_id = update["messages"][-1].tool_calls[0]["id"]
        _apply(state, {"messages": [ToolMessage(RESULT, tool_call_id=call_id, name="search")]})


def _shape(messages: list[BaseMessage]) -> list[tuple[str, str | None, str]]:
    return [(type(m).__name__, m.id, str(m.content)[:40]) for m in messages]


@pytest.mark.parametrize(("turn_id", "kept"), [(21, 5), (22, 6), (23, 7)])
async def test_a_trimmed_head_never_changes_the_prompt_already_sent(
    sent: list[list[BaseMessage]], monkeypatch: pytest.MonkeyPatch, turn_id: int, kept: int
) -> None:
    state = _thread(turn_id=turn_id, monkeypatch=monkeypatch)

    await _run_loop(state, LOOP_CALLS)

    assert "h1" not in [m.id for m in state["messages"]], "the head was never trimmed"
    # The counter decides how many previous turns are kept (W=5, B=3), each whole.
    assert [m.id for m in sent[0][1 : 1 + 2 * kept]] == [
        f"{kind}{number}"
        for number in range(PAST_TURNS - kept + 1, PAST_TURNS + 1)
        for kind in "ha"
    ]
    for previous, current in zip(sent, sent[1:], strict=False):
        assert _shape(current[: len(previous)]) == _shape(previous)


async def test_the_next_turn_reads_this_turn_s_prefix_through_its_question(
    sent: list[list[BaseMessage]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Turn 21 keeps 5 turns and turn 22 keeps 6 (W=5, B=3): the same block.
    state = _thread(turn_id=PAST_TURNS + 1, monkeypatch=monkeypatch)
    await _run_loop(state, 2)
    _apply(state, {"messages": [AIMessage("the routine's answer", id="done")]})
    _apply(state, {"messages": [HumanMessage("a follow-up", id="next")]})
    state["current_turn_id"] = PAST_TURNS + 2
    state["react_iteration"] = 0

    await _run_loop(state, 1)

    first_of_turn, next_turn = sent[0], sent[-1]
    through_question = [m.id for m in first_of_turn].index("now") + 1
    assert _shape(next_turn[:through_question]) == _shape(first_of_turn[:through_question])
