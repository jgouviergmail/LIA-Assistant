"""A declared gap runs one recovery pass, and the thread keeps one answer (ADR-310).

The real nodes, the real router and the real messages reducer, driven step by
step; only the model is scripted. The first test is the 2026-09-23 turn made
right: a draft that declares a gap is re-opened, the model corrects its call,
and the thread keeps the answer alone. The second pins the bound: a pass that
changes nothing ends the turn, with the gap still declared.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.core.config import settings
from src.domains.agents.constants import (
    NODE_REACT_EXECUTE_TOOLS,
    NODE_REACT_FINALIZE,
    NODE_REACT_RECOVERY,
)
from src.domains.agents.models import add_messages_with_truncate
from src.domains.agents.nodes import react_nodes as rn
from src.domains.agents.nodes.react_recovery import react_recovery_node
from src.domains.agents.nodes.routing import route_from_react_call_model

pytestmark = pytest.mark.unit


def _apply(state: dict[str, Any], update: dict[str, Any]) -> None:
    """Merge a node's update the way the graph does."""
    for key, value in update.items():
        if key == "messages":
            state[key] = add_messages_with_truncate(state[key], value)
        else:
            state[key] = value


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A scripted model: each call pops the next reply and records what it was sent."""
    script: dict[str, Any] = {"replies": [], "sent": []}
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])
    monkeypatch.setattr(settings, "react_recovery_passes_max", 1)

    async def fake_stream(
        _llm: Any, messages: list[BaseMessage], emit: Any, config: Any
    ) -> AIMessage:
        script["sent"].append(list(messages))
        reply: AIMessage = script["replies"].pop(0)
        return reply

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )
    return script


def _turn() -> dict[str, Any]:
    return {
        "messages": [HumanMessage("Weather in Lyon tomorrow?", id="h1")],
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_system_blocks": ["You are LIA."],
        "react_iteration": 0,
        "react_max_iterations_effective": 70,
        "react_elapsed_seconds": 0.0,
        "react_recovery_passes": [],
    }


async def test_a_gap_is_recovered_and_the_draft_leaves_the_thread(
    model: dict[str, Any],
) -> None:
    model["replies"] = [
        AIMessage("Draft. <unresolved>- forecast for tomorrow</unresolved>", id="d1"),
        AIMessage(
            "",
            id="a2",
            tool_calls=[{"id": "c2", "name": "forecast", "args": {"date": "2026-09-25"}}],
        ),
        AIMessage("Sunny, 21 degrees.", id="f1"),
    ]
    state = _turn()

    _apply(state, await rn.react_call_model_node(state, config={}))
    assert route_from_react_call_model(state) == NODE_REACT_RECOVERY
    _apply(state, await react_recovery_node(state, {}))
    assert "d1" not in [m.id for m in state["messages"]]

    _apply(state, await rn.react_call_model_node(state, config={}))
    second = model["sent"][1]
    assert [type(m).__name__ for m in second[-3:]] == ["HumanMessage", "AIMessage", "HumanMessage"]
    assert "RECOVERY LADDER" in str(second[-1].content)
    assert route_from_react_call_model(state) == NODE_REACT_EXECUTE_TOOLS

    _apply(state, {"messages": [ToolMessage("Sunny", tool_call_id="c2", id="t2")]})
    _apply(state, await rn.react_call_model_node(state, config={}))
    assert route_from_react_call_model(state) == NODE_REACT_FINALIZE

    result = await rn.react_finalize_node(state, {})
    assert result["react_agent_result"]["recovery"] == {"passes": 1, "outcome": "resolved"}
    assert [m.id for m in state["messages"]] == ["h1", "a2", "t2", "f1"]


async def test_a_pass_that_changes_nothing_ends_the_turn(model: dict[str, Any]) -> None:
    gap = "<unresolved>- forecast for tomorrow</unresolved>"
    model["replies"] = [AIMessage(f"Draft. {gap}", id="d1"), AIMessage(f"Still. {gap}", id="d2")]
    state = _turn()

    _apply(state, await rn.react_call_model_node(state, config={}))
    _apply(state, await react_recovery_node(state, {}))
    _apply(state, await rn.react_call_model_node(state, config={}))

    assert route_from_react_call_model(state) == NODE_REACT_FINALIZE
    result = await rn.react_finalize_node(state, {})
    assert result["react_agent_result"]["recovery"] == {
        "passes": 1,
        "outcome": "still_unresolved",
    }
    assert [m.id for m in state["messages"]] == ["h1", "d2"]


async def test_an_empty_answer_after_the_pass_keeps_the_draft(model: dict[str, Any]) -> None:
    """Final review: the pass's reply came back empty, the draft had already left
    the thread, and the turn handed the response node nothing — counted `resolved`."""
    draft = "Draft. <unresolved>- forecast for tomorrow</unresolved>"
    model["replies"] = [AIMessage(draft, id="d1"), AIMessage("", id="e1")]
    state = _turn()

    _apply(state, await rn.react_call_model_node(state, config={}))
    _apply(state, await react_recovery_node(state, {}))
    _apply(state, await rn.react_call_model_node(state, config={}))

    assert route_from_react_call_model(state) == NODE_REACT_FINALIZE
    result = (await rn.react_finalize_node(state, {}))["react_agent_result"]
    assert result["final_message"] == draft
    assert result["recovery"] == {"passes": 1, "outcome": "still_unresolved"}


async def test_a_budget_cut_during_the_pass_keeps_the_draft(
    model: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A budget that stops the pass mid-call leaves calls nobody answers: the
    finalize publishes no message carrying them (invariant 1) — and must not
    publish NOTHING when a complete draft existed."""
    monkeypatch.setattr(settings, "react_progress_extension_enabled", False)
    draft = "Draft. <unresolved>- forecast for tomorrow</unresolved>"
    model["replies"] = [
        AIMessage(draft, id="d1"),
        AIMessage("", id="a2", tool_calls=[{"id": "c2", "name": "forecast", "args": {}}]),
    ]
    state = _turn()
    state["react_max_iterations_effective"] = 2

    _apply(state, await rn.react_call_model_node(state, config={}))
    _apply(state, await react_recovery_node(state, {}))
    _apply(state, await rn.react_call_model_node(state, config={}))

    assert route_from_react_call_model(state) == NODE_REACT_FINALIZE
    result = (await rn.react_finalize_node(state, {}))["react_agent_result"]
    assert result["final_message"] == draft
    assert result["recovery"]["outcome"] == "cut"
