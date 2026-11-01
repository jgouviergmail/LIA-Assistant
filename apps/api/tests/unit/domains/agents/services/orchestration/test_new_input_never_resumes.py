"""A new input never resumes the question it replaces (ADR-367 amendment).

LangGraph treats a run as a RESUMPTION when its ``run_id`` equals the last
checkpoint's — the stream re-entry rule of ``pregel/_loop.py`` — even when the
input is a new state rather than a ``Command``. The chat reuses the run id of
the question it answers, so a message turned into a NEW request (a stale
question, a question abandoned for another request) re-ran the interrupted node,
which read a resume value nobody gave: measured on Docker dev 2026-10-31, « how
much is 12 times 7? » after two unclear answers cancelled the turn instead of
being answered. A normal run is declared fresh (``fresh_run_config``).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.domains.agents.services.orchestration.turn_input import fresh_run_config

pytestmark = pytest.mark.unit


class _State(TypedDict):
    log: Annotated[list[str], operator.add]
    msg: str


def _read(state: _State) -> dict[str, Any]:
    return {"log": [f"read:{state['msg']}"]}


def _ask(state: _State) -> dict[str, Any]:
    if state["msg"] == "ambiguous":
        first = interrupt("which one?")
        second = interrupt("which one, again?") if first == "unclear" else first
        return {"log": [f"answered:{second}"]}
    return {"log": ["acted"]}


def _graph() -> Any:
    graph = StateGraph(_State)
    graph.add_node("read", _read)
    graph.add_node("ask", _ask)
    graph.add_edge(START, "read")
    graph.add_edge("read", "ask")
    graph.add_edge("ask", END)
    return graph.compile(checkpointer=MemorySaver())


async def _asked_twice(app: Any, config: dict[str, Any]) -> None:
    await app.ainvoke({"msg": "ambiguous", "log": []}, config)
    await app.ainvoke(Command(resume="unclear"), config)
    assert (await app.aget_state(config)).next == ("ask",)


CONFIG: dict[str, Any] = {"configurable": {"thread_id": "t"}, "metadata": {"run_id": "run-1"}}


async def test_the_same_run_id_with_a_new_input_resumes_the_question() -> None:
    """The trap itself: without the flag, the new input never reaches the graph's start."""
    app = _graph()
    await _asked_twice(app, CONFIG)

    out = await app.ainvoke({"msg": "a new request"}, CONFIG)

    assert "read:a new request" not in out["log"]


async def test_a_fresh_run_starts_over_from_its_input() -> None:
    app = _graph()
    await _asked_twice(app, CONFIG)

    out = await app.ainvoke({"msg": "a new request"}, fresh_run_config(CONFIG))

    assert out["log"][-2:] == ["read:a new request", "acted"]
    assert (await app.aget_state(CONFIG)).next == ()


def test_the_flag_never_touches_the_caller_s_config() -> None:
    config = {"configurable": {"thread_id": "t"}}
    fresh = fresh_run_config(config)
    assert config == {"configurable": {"thread_id": "t"}}
    assert fresh["configurable"]["thread_id"] == "t"
