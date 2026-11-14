"""The person's notes are wired into the ReAct nodes and the response (ADR-385).

The call node reads what joined, shows it to this call and every later one after the
message the loop had, and records it — never in the thread. The loop's two exits (the
finalize node, the hand-off of a draft) close the notes and fold them into the turn's
question; the response is given the same completed request.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.domains.agents.api.turn_notes import TakenNote
from src.domains.agents.nodes import react_nodes as rn
from src.domains.agents.nodes import react_turn_notes as notes

pytestmark = pytest.mark.unit

WRITTEN = datetime(2026, 11, 13, 17, 42, tzinfo=UTC)
NOTE = "only the ones open on Sunday"


def _record(anchor_id: str = "t1") -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "text": NOTE,
        "written_at": WRITTEN.isoformat(),
        "anchor_id": anchor_id,
        "passes_before": 0,
    }


@pytest.fixture
def state() -> dict[str, Any]:
    return {
        "messages": [
            HumanMessage(content="Restaurants near the station?", id="h1"),
            AIMessage(content="", id="a1", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
            ToolMessage(content="Twelve places.", id="t1", tool_call_id="c1", name="t"),
        ],
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_iteration": 1,
        "react_system_blocks": ["You are LIA."],
        "react_elapsed_seconds": 0.0,
        "user_timezone": "Europe/Paris",
    }


@pytest.fixture
def read(monkeypatch: pytest.MonkeyPatch) -> list[TakenNote]:
    """What the door hands the next call; emptied once read."""
    pending: list[TakenNote] = []

    async def read_turn_notes() -> list[TakenNote]:
        taken = list(pending)
        pending.clear()
        return taken

    monkeypatch.setattr(notes, "read_turn_notes", read_turn_notes)
    return pending


@pytest.fixture
def closed(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    calls: list[bool] = []

    async def close_turn_notes() -> None:
        calls.append(True)

    monkeypatch.setattr(notes, "close_turn_notes", close_turn_notes)
    return calls


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


def _note_after(messages: list[BaseMessage], anchor_id: str) -> BaseMessage:
    at = [m.id for m in messages].index(anchor_id)
    return messages[at + 1]


async def test_a_note_read_at_a_call_is_shown_to_that_call_and_recorded(
    state: dict[str, Any], read: list[TakenNote], sent: list[list[BaseMessage]]
) -> None:
    read.append(TakenNote(uuid4(), NOTE, WRITTEN))

    result = await rn.react_call_model_node(state, config={})

    note = _note_after(sent[0], "t1")
    assert isinstance(note, HumanMessage) and str(note.content).endswith(NOTE)
    [record] = result["react_turn_notes"]
    assert record["anchor_id"] == "t1" and record["text"] == NOTE


async def test_a_recorded_note_is_shown_at_every_later_call_and_never_written_to_the_thread(
    state: dict[str, Any], read: list[TakenNote], sent: list[list[BaseMessage]]
) -> None:
    state["react_turn_notes"] = [_record()]

    result = await rn.react_call_model_node(state, config={})

    assert str(_note_after(sent[0], "t1").content).endswith(NOTE)
    assert [m.id for m in result["messages"]] == ["out"]
    assert "react_turn_notes" not in result
    assert [m.id for m in state["messages"]] == ["h1", "a1", "t1"]


async def test_a_call_with_no_note_sends_what_it_sent_before(
    state: dict[str, Any], read: list[TakenNote], sent: list[list[BaseMessage]]
) -> None:
    await rn.react_call_model_node(state, config={})

    assert [m.id for m in sent[0][1:]] == ["h1", "a1", "t1"]


async def test_finalize_closes_the_notes_and_folds_them_into_the_question(
    state: dict[str, Any], closed: list[bool]
) -> None:
    state["messages"].append(AIMessage("Here are three.", id="f1"))
    state["react_turn_notes"] = [_record()]

    result = await rn.react_finalize_node(state, {})

    assert closed == [True]
    [folded] = result["messages"]
    assert folded.id == "h1" and str(folded.content).endswith(NOTE)
    assert str(folded.content).startswith("Restaurants near the station?\n\n")


async def test_finalize_without_a_note_writes_no_message(
    state: dict[str, Any], closed: list[bool]
) -> None:
    state["messages"].append(AIMessage("Here are three.", id="f1"))

    result = await rn.react_finalize_node(state, {})

    assert closed == [True]
    assert "messages" not in result


async def test_a_cut_loop_answers_its_calls_and_folds_the_notes(
    state: dict[str, Any], closed: list[bool]
) -> None:
    """The abandoned calls' results and the folded question travel in one update."""
    state["messages"].append(
        AIMessage(content="", id="a2", tool_calls=[{"name": "t", "args": {}, "id": "c2"}])
    )
    state["react_turn_notes"] = [_record()]
    state["react_iteration"] = 10_000

    result = await rn.react_finalize_node(state, {})

    kinds = [(type(m).__name__, m.id) for m in result["messages"]]
    assert ("HumanMessage", "h1") in kinds
    assert any(kind == "ToolMessage" for kind, _ in kinds)


async def test_a_draft_hand_off_closes_the_notes_and_folds_them(
    state: dict[str, Any], closed: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    state["react_turn_notes"] = [_record()]
    tool_result = ToolMessage(content="draft", id="t2", tool_call_id="c2", name="t")

    async def execute_call(*_args: object) -> dict[str, object]:
        return {
            "messages": [tool_result],
            "pending_draft_critique": {"draft_id": "d1"},
            "react_agent_result": {"final_message": "", "iteration_count": 1, "mode": "react"},
        }

    async def no_store() -> object:
        return None

    monkeypatch.setattr(rn, "execute_call", execute_call)
    monkeypatch.setattr(
        "src.domains.agents.context.store.get_tool_context_store", no_store, raising=True
    )
    result = await rn._execute_react_calls(state, {})

    assert closed == [True]
    messages = result["messages"]
    assert isinstance(messages, list)
    assert messages[0] is tool_result
    assert messages[1].id == "h1" and str(messages[1].content).endswith(NOTE)


async def test_a_segment_that_continues_the_loop_keeps_the_notes_open(
    state: dict[str, Any], closed: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    state["react_turn_notes"] = [_record()]

    async def execute_call(*_args: object) -> dict[str, object]:
        return {"messages": [ToolMessage(content="r", id="t2", tool_call_id="c2", name="t")]}

    async def no_store() -> object:
        return None

    monkeypatch.setattr(rn, "execute_call", execute_call)
    monkeypatch.setattr(
        "src.domains.agents.context.store.get_tool_context_store", no_store, raising=True
    )
    result = await rn._execute_react_calls(state, {})

    assert closed == []
    assert [m.id for m in result["messages"]] == ["t2"]


def test_the_response_is_given_the_completed_request(monkeypatch: pytest.MonkeyPatch) -> None:
    # The package re-exports the node FUNCTION under the module's name.
    response_node = importlib.import_module("src.domains.agents.nodes.response_node")

    question = HumanMessage("Restaurants near the station?", id="h1")
    folded = notes.fold_notes(question, [_record()], "Europe/Paris")
    state: dict[str, Any] = {
        "messages": [folded, AIMessage("Here are three.", id="f1")],
        "react_turn_notes": [_record()],
        "user_timezone": "Europe/Paris",
    }
    monkeypatch.setattr(
        response_node,
        "get_qi_attr",
        lambda _state, attr, default=None: (
            "Restaurants near the station?" if attr == "original_query" else default
        ),
    )

    history, _last, query = response_node._build_conversation_history(state, "run", False)

    assert query == folded.content
    assert NOTE not in history
