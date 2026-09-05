"""The consultation register, measured on a REAL compiled graph (ADR-263, lot 4).

The method this file exists to enforce. Lot 3 shipped a card no message ever
carried, and the reason was not the mechanism — the mechanism was tested and
green. It was that the test drove the mechanism directly instead of driving the
PATH the application takes, so a ``run_id`` rebuilt one layer above went
unnoticed.

A collector is exactly the same kind of trap: ``ContextVar`` semantics differ
between a plain ``await`` and a task, and LangGraph decides which one runs a
node. So the property is proven where it must hold — inside a compiled
``StateGraph``, with a fan-out node built like ``parallel_executor`` and a
sequential node built like the ReAct loop.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Annotated, Any
from unittest.mock import patch

import pytest
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.treatments import collected_treatments, treatment_collector

pytestmark = [pytest.mark.unit]


def _merge(left: list[str], right: list[str]) -> list[str]:
    return [*left, *right]


class _TurnState(TypedDict):
    """The smallest state a two-node graph needs."""

    seen: Annotated[list[str], _merge]


@pytest.fixture(autouse=True)
def _running_turn() -> Any:
    gate_runtime.reset_policy_cache()
    with (
        patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id="11111111-1111-4111-8111-111111111111",
                thread_id="thread-1",
                execution_mode="pipeline",
                is_automated_source=False,
            ),
        ),
    ):
        yield


async def _tool(name: str = "x") -> dict[str, Any]:
    await asyncio.sleep(0)
    return {"success": True, "data": {"name": name}}


def _build_graph(*, raising: bool = False, hanging: bool = False) -> Any:
    """Compile a graph shaped like the two execution modes.

    Args:
        raising: Make the sequential node raise, as a failing turn does.
        hanging: Make the sequential node hang, so the turn can be cancelled.

    Returns:
        The compiled graph.
    """
    fan_out = gate_runtime.gated("get_emails_tool", _tool)
    step = gate_runtime.gated("get_calendar_events_tool", _tool)

    async def _parallel(_state: _TurnState) -> dict[str, list[str]]:
        # The ``parallel_executor`` shape: independent tasks under one gather.
        await asyncio.gather(*(fan_out(name=f"m{index}") for index in range(3)))
        return {"seen": ["parallel"]}

    async def _sequential(_state: _TurnState) -> dict[str, list[str]]:
        # The ReAct shape: plain awaits, one after the other.
        for index in range(3):
            await step(name=f"s{index}")
        if raising:
            raise RuntimeError("the turn failed")
        if hanging:
            await asyncio.sleep(60)
        return {"seen": ["sequential"]}

    builder: StateGraph[_TurnState] = StateGraph(_TurnState)
    builder.add_node("parallel", _parallel)
    builder.add_node("sequential", _sequential)
    builder.add_edge(START, "parallel")
    builder.add_edge("parallel", "sequential")
    builder.add_edge("sequential", END)
    return builder.compile()


class TestTheRealGraph:
    async def test_both_node_shapes_are_collected(self) -> None:
        graph = _build_graph()
        with treatment_collector(run_id="run-1") as rows:
            await graph.ainvoke({"seen": []})
            collected = list(rows)

        assert len(collected) == 6, f"lost a consultation: {[r.tool_name for r in collected]}"
        assert {row.tool_name for row in collected} == {
            "get_emails_tool",
            "get_calendar_events_tool",
        }

    async def test_the_turns_run_id_is_the_one_recorded(self) -> None:
        """The lot-3 defect, pinned one layer down: the PARENT names the run."""
        graph = _build_graph()
        with treatment_collector(run_id="run-42") as rows:
            await graph.ainvoke({"seen": []})
            collected = list(rows)

        assert {row.run_id for row in collected} == {"run-42"}

    async def test_a_turn_that_RAISES_keeps_what_it_had_consulted(self) -> None:
        graph = _build_graph(raising=True)
        with treatment_collector(run_id="run-1") as rows:
            with pytest.raises(RuntimeError):
                await graph.ainvoke({"seen": []})
            collected = list(rows)

        assert len(collected) == 6, "a failed turn lost its consultations"

    async def test_a_turn_that_is_CANCELLED_keeps_what_it_had_consulted(self) -> None:
        graph = _build_graph(hanging=True)
        with treatment_collector(run_id="run-1") as rows:
            task = asyncio.create_task(graph.ainvoke({"seen": []}))
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            collected = list(rows)

        assert len(collected) == 6, "a cancelled turn lost its consultations"

    async def test_no_collector_published_runs_the_turn_unchanged(self) -> None:
        graph = _build_graph()
        state = await graph.ainvoke({"seen": []})

        assert sorted(state["seen"]) == ["parallel", "sequential"]
        assert list(collected_treatments()) == []

    async def test_two_concurrent_turns_do_not_mix_their_registers(self) -> None:
        """One process serves many users; a shared list would merge them."""
        graph = _build_graph()

        async def _turn(run_id: str) -> list[str]:
            with treatment_collector(run_id=run_id) as rows:
                await graph.ainvoke({"seen": []})
                return [row.run_id for row in rows]

        first, second = await asyncio.gather(_turn("run-a"), _turn("run-b"))

        assert set(first) == {"run-a"}, "another turn's consultations leaked in"
        assert set(second) == {"run-b"}
        assert len(first) == len(second) == 6
