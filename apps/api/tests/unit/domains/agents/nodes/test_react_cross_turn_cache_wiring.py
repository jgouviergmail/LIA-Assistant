"""The ReAct call node shapes each call by the turn's exchange rhythm (ADR-308, ADR-311).

For occasional exchanges a call sends exactly what it sent before ADR-308; for
frequent exchanges the turn's context follows the question. The rhythm is read
from the turn's state, which the router wrote at the turn's start, never from
the instance setting; nothing of the layout is written to the checkpoint.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.core.config import settings
from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.nodes import react_nodes as rn

pytestmark = pytest.mark.unit

PROMPT = (
    f"You are LIA.\n\n{DYNAMIC_CONTEXT_MARKER} (all variable data below) ---\n\nDate: 2026-09-23"
)
MEMORY = "<UserMemories>Likes tea.</UserMemories>"


@pytest.fixture
def state() -> dict[str, Any]:
    return {
        "messages": [
            HumanMessage(content="earlier", id="h0"),
            AIMessage(content="earlier answer", id="a0"),
            HumanMessage(content="Check my emails.", id="h1"),
            AIMessage(content="", id="a1", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
            ToolMessage(content="Retrieved 3 emails.", id="t1", tool_call_id="c1", name="t"),
        ],
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_iteration": 1,
        "react_system_blocks": [PROMPT, MEMORY],
        "react_elapsed_seconds": 0.0,
    }


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[list[BaseMessage]]:
    """What the node hands to the model, one list per call."""
    captured: list[list[BaseMessage]] = []
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])
    monkeypatch.setattr(rn, "react_slot_provider", lambda: "deepseek")

    async def fake_stream(
        _llm: Any, messages: list[BaseMessage], emit: Any, config: Any
    ) -> AIMessage:
        captured.append(list(messages))
        return AIMessage(content="done", id="out")

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )
    return captured


async def test_occasional_exchanges_send_what_a_call_sent_before(
    state: dict[str, Any], sent: list[list[BaseMessage]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The instance default says frequent: the turn's own rhythm decides.
    monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", True)
    state["exchange_rhythm"] = "occasional"
    await rn.react_call_model_node(state, config={})
    assert sent[0][:2] == [SystemMessage(content=PROMPT), SystemMessage(content=MEMORY)]
    assert [m.id for m in sent[0][2:]] == ["h0", "a0", "h1", "a1", "t1"]


async def test_frequent_exchanges_place_the_turn_s_context_after_the_question(
    state: dict[str, Any], sent: list[list[BaseMessage]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", False)
    state["exchange_rhythm"] = "frequent"
    await rn.react_call_model_node(state, config={})
    messages = sent[0]
    assert "Date:" not in str(messages[0].content)
    question_at = next(i for i, m in enumerate(messages) if m.id == "h1")
    context = messages[question_at + 1]
    assert isinstance(context, SystemMessage)
    assert "Date: 2026-09-23" in str(context.content) and MEMORY in str(context.content)
    assert [m.id for m in messages[question_at + 2 :]] == ["a1", "t1"]


async def test_the_layout_never_reaches_the_checkpoint(
    state: dict[str, Any], sent: list[list[BaseMessage]]
) -> None:
    state["exchange_rhythm"] = "frequent"
    result = await rn.react_call_model_node(state, config={})
    assert [m.id for m in result["messages"]] == ["out"]
    assert state["messages"][2].content == "Check my emails."
    assert state["react_system_blocks"] == [PROMPT, MEMORY]
