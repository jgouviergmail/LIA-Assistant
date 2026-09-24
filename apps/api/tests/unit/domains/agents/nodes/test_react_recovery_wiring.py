"""The recovery pass is wired into the ReAct nodes (ADR-310).

The call node shows the model, after each pass's anchor, its draft and the
directive — composed from the checkpointed records, so a resumed call shows
them again — and writes neither to the thread. The finalize node reports what
the passes achieved.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.domains.agents.nodes import react_nodes as rn

pytestmark = pytest.mark.unit

PASS = {"anchor_id": "t1", "draft": "D", "unresolved": ["A"]}


@pytest.fixture
def state() -> dict[str, Any]:
    return {
        "messages": [
            HumanMessage(content="Weather tomorrow?", id="h1"),
            AIMessage(content="", id="a1", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
            ToolMessage(content="Served 2026-09-24.", id="t1", tool_call_id="c1", name="t"),
        ],
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_iteration": 2,
        "react_system_blocks": ["You are LIA."],
        "react_elapsed_seconds": 0.0,
        "react_recovery_passes": [PASS],
    }


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[BaseMessage]]:
    """What the node hands to the model, one list per call."""
    captured: list[list[BaseMessage]] = []
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])

    async def fake_stream(
        _llm: Any, messages: list[BaseMessage], emit: Any, config: Any
    ) -> AIMessage:
        captured.append(list(messages))
        return AIMessage(content="done", id="out")

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )
    return captured


async def test_the_call_shows_the_draft_and_the_directive_after_the_anchor(
    state: dict[str, Any], sent: list[list[BaseMessage]]
) -> None:
    await rn.react_call_model_node(state, config={})

    messages = sent[0]
    at = [m.id for m in messages].index("t1")
    assert isinstance(messages[at + 1], AIMessage) and messages[at + 1].content == "D"
    assert isinstance(messages[at + 2], HumanMessage)
    assert "RECOVERY LADDER" in str(messages[at + 2].content)


async def test_the_directive_survives_a_resume(
    state: dict[str, Any], sent: list[list[BaseMessage]]
) -> None:
    """A HITL interrupt re-enters the call node: it composes the same messages again."""
    await rn.react_call_model_node(state, config={})
    await rn.react_call_model_node(state, config={})

    assert all(any("RECOVERY LADDER" in str(m.content) for m in call) for call in sent)


async def test_the_directive_never_reaches_the_checkpoint(
    state: dict[str, Any], sent: list[list[BaseMessage]]
) -> None:
    result = await rn.react_call_model_node(state, config={})

    assert [m.id for m in result["messages"]] == ["out"]
    assert [m.id for m in state["messages"]] == ["h1", "a1", "t1"]


async def test_a_turn_without_a_pass_sends_what_it_sent_before(
    state: dict[str, Any], sent: list[list[BaseMessage]]
) -> None:
    state["react_recovery_passes"] = []
    await rn.react_call_model_node(state, config={})

    assert [m.id for m in sent[0][1:]] == ["h1", "a1", "t1"]


async def test_finalize_reports_the_outcome() -> None:
    state = {
        "messages": [HumanMessage("q", id="h1"), AIMessage("answer", id="f1")],
        "react_iteration": 5,
        "react_elapsed_seconds": 1.0,
        "react_recovery_passes": [{"anchor_id": "h1", "draft": "D", "unresolved": ["A"]}],
    }
    result = await rn.react_finalize_node(state, {})

    assert result["react_agent_result"]["recovery"] == {"passes": 1, "outcome": "resolved"}


async def test_finalize_without_a_pass_reports_nothing() -> None:
    state = {"messages": [HumanMessage("q"), AIMessage("answer")], "react_iteration": 2}
    result = await rn.react_finalize_node(state, {})

    assert "recovery" not in result["react_agent_result"]
