"""A cut-short run must never be served as a finished one.

Measured in production on 2026-08-28 (run 11:29:01→11:29:33): six ReAct
iterations, each executing a tool, then the iteration ceiling. The router left
for the finalize node, and ``react_finalize_node`` took the content of the LAST
``AIMessage`` as the answer — a message that still carried UNEXECUTED
``tool_calls`` and whose text was the model's narration of intent ("give me a
minute, I'll get you those numbers"). The user received a promise, the pending
calls were dropped in silence, and nothing said the search had been cut. There
is no background continuation in this product: a turn ends when the answer is
sent, so a promise is simply a dead end.

Two invariants follow, and they are independent:

- a message that still has ``tool_calls`` is mid-thought, never an answer;
- when the loop stops early, the reason travels to the response synthesis so the
  answer can say it — honestly, with what WAS found.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.domains.agents.nodes import react_nodes

pytestmark = [pytest.mark.unit]

NARRATION = "Je plonge dans tes emails. Donne-moi une minute, je te sors ça."
ANSWER = "Ton escale à Doha dure 3 h 40."


def _state(last: Any, iteration: int = 3, budget: int | None = 6) -> dict[str, Any]:
    return {
        "messages": [HumanMessage("Combien durent mes escales ?"), last],
        "react_iteration": iteration,
        "react_max_iterations_effective": budget,
        "react_elapsed_seconds": 1.0,
        "react_start_time": 0.0,
    }


def _mid_thought() -> AIMessage:
    return AIMessage(
        content=NARRATION,
        tool_calls=[{"id": "c1", "name": "search_emails", "args": {"q": "vol"}}],
    )


class TestAPromiseIsNeverAnAnswer:
    async def test_a_message_with_pending_tool_calls_is_not_the_final_message(self) -> None:
        result = await react_nodes.react_finalize_node(_state(_mid_thought()), {})

        assert result["react_agent_result"]["final_message"] == "", (
            "the narration accompanying unexecuted tool calls must not be served; "
            "an empty final message makes the response node synthesise from what "
            "the tools DID return — the same path the draft handoff already uses"
        )

    async def test_a_real_final_answer_still_passes_through(self) -> None:
        """No regression: a clean completion keeps its answer."""
        result = await react_nodes.react_finalize_node(
            _state(AIMessage(content=ANSWER), iteration=2), {}
        )

        assert result["react_agent_result"]["final_message"] == ANSWER
        assert result["react_agent_result"].get("truncation") is None


class TestTheReasonTravels:
    async def test_hitting_the_iteration_ceiling_is_reported(self) -> None:
        result = await react_nodes.react_finalize_node(
            _state(_mid_thought(), iteration=6, budget=6), {}
        )

        truncation = result["react_agent_result"]["truncation"]
        assert truncation["reason"] == "max_iterations"
        assert truncation["iterations"] == 6

    async def test_pending_calls_without_a_ceiling_are_reported_too(self) -> None:
        """The loop can also stop on a draft handoff or a graph interrupt."""
        result = await react_nodes.react_finalize_node(
            _state(_mid_thought(), iteration=2, budget=90), {}
        )

        assert result["react_agent_result"]["truncation"]["reason"] == "pending_tool_calls"

    async def test_a_clean_run_reports_no_truncation(self) -> None:
        result = await react_nodes.react_finalize_node(
            _state(AIMessage(content=ANSWER), iteration=2, budget=90), {}
        )

        assert "truncation" not in result["react_agent_result"]


class TestOnePredicateForBothReaders:
    """The router decides, the finalize explains — on the same arithmetic."""

    def test_the_router_uses_the_shared_predicate(self) -> None:
        import inspect

        from src.domains.agents.nodes import routing

        source = inspect.getsource(routing.route_from_react_call_model)
        assert "react_exit_reason" in source, (
            "a second copy of the budget arithmetic would let the router stop "
            "for a reason the answer never mentions"
        )

    def test_the_predicate_names_each_stop_condition(self) -> None:
        assert react_nodes.react_exit_reason(_state(AIMessage(""), 6, 6)) == "max_iterations"
        assert react_nodes.react_exit_reason(_state(AIMessage(""), 2, 90)) is None

    def test_the_compute_budget_is_a_named_reason(self) -> None:
        from src.core.config import settings

        state = _state(AIMessage(""), iteration=2, budget=90)
        state["react_elapsed_seconds"] = float(settings.react_agent_timeout_seconds) + 1.0

        assert react_nodes.react_exit_reason(state) == "compute_budget"


class TestTheAnswerIsToldToSayIt:
    async def test_the_honesty_block_carries_the_truncation(self) -> None:
        from src.domains.agents.services.runtime_failure_directive import (
            build_run_honesty_block,
        )

        state = {
            "messages": [ToolMessage(content="ok", tool_call_id="c1")],
            "react_agent_result": {
                "final_message": "",
                "iteration_count": 6,
                "mode": "react",
                "truncation": {"reason": "max_iterations", "iterations": 6},
            },
        }

        block = await build_run_honesty_block(state)

        assert block, "a cut-short run must always produce an honesty directive"
        assert "6" in block

    async def test_it_does_not_depend_on_the_diagnostics_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Telling the truth about our own run is not an observability feature."""
        from src.core.config import settings
        from src.domains.agents.services.runtime_failure_directive import (
            build_run_honesty_block,
        )

        monkeypatch.setattr(settings, "diagnostics_enabled", False, raising=False)
        state = {
            "messages": [],
            "react_agent_result": {"truncation": {"reason": "max_iterations", "iterations": 6}},
        }

        assert await build_run_honesty_block(state)

    async def test_a_clean_turn_still_costs_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings
        from src.domains.agents.services.runtime_failure_directive import (
            build_run_honesty_block,
        )

        monkeypatch.setattr(settings, "diagnostics_enabled", False, raising=False)

        assert await build_run_honesty_block({"messages": []}) == ""
