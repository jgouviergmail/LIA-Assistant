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


class TestTheAbandonedCallsAreAnswered:
    """A third invariant, and it is about STATE, not about the answer.

    The two above make the cut-short turn honest to the user. Neither cleans
    the checkpoint: the ``AIMessage`` keeps ``tool_calls`` nobody will ever
    answer, and LangGraph persists it. Measured in production on 2026-09-02 —
    one budget exit, then every following turn on that thread died on
    ``400 No tool output found for function call …`` with the same call id.
    The conversation was bricked, and the turn-start repair could only mend it
    after the fact.

    So the loop closes its own books: each abandoned call gets an explicit
    result saying it never ran and what to do next. The history is then valid
    BY CONSTRUCTION, and the model is told what it lost instead of silently
    re-deriving it next turn.
    """

    async def test_every_pending_call_gets_an_explicit_result(self) -> None:
        last = AIMessage(
            content=NARRATION,
            tool_calls=[
                {"name": "search_emails", "args": {}, "id": "call_1"},
                {"name": "list_events", "args": {}, "id": "call_2"},
            ],
        )

        result = await react_nodes.react_finalize_node(_state(last, iteration=6, budget=6), {})

        emitted = result.get("messages") or []
        assert [m.tool_call_id for m in emitted] == ["call_1", "call_2"]
        assert all(isinstance(m, ToolMessage) for m in emitted)

    async def test_the_result_is_flagged_as_an_error_not_a_success(self) -> None:
        """A call that never ran did not succeed; the model must not read it
        as data."""
        last = AIMessage(
            content=NARRATION,
            tool_calls=[{"name": "search_emails", "args": {}, "id": "call_1"}],
        )

        result = await react_nodes.react_finalize_node(_state(last, iteration=6, budget=6), {})

        assert result["messages"][0].status == "error"

    async def test_the_result_names_the_stop_reason_and_what_to_do(self) -> None:
        """A bare refusal is what a stalled model retries verbatim
        (loop_guard's documented lesson, applied here)."""
        last = AIMessage(
            content=NARRATION,
            tool_calls=[{"name": "search_emails", "args": {}, "id": "call_1"}],
        )

        result = await react_nodes.react_finalize_node(_state(last, iteration=6, budget=6), {})

        body = result["messages"][0].content
        assert "max_iterations" in body
        assert "not executed" in body.lower()

    async def test_the_tool_name_travels_with_the_result(self) -> None:
        last = AIMessage(
            content=NARRATION,
            tool_calls=[{"name": "search_emails", "args": {}, "id": "call_1"}],
        )

        result = await react_nodes.react_finalize_node(_state(last, iteration=6, budget=6), {})

        assert result["messages"][0].name == "search_emails"

    async def test_a_clean_run_emits_no_synthetic_result(self) -> None:
        """No pending call, nothing to close: the state update stays untouched."""
        result = await react_nodes.react_finalize_node(_state(AIMessage(ANSWER), iteration=2), {})

        assert not result.get("messages")

    async def test_a_call_without_an_id_cannot_be_answered_and_is_skipped(self) -> None:
        """Never invent a pairing: an id-less call is left to the turn-start
        repair, which removes it. The identified ones are still closed.

        ``AIMessage(tool_calls=[...])`` refuses a call with no ``id`` key, but
        ``id: None`` passes — and that is the shape a checkpoint round-trip can
        produce, since validation runs at construction only (measured). The
        guard is reachable, not defensive decoration.
        """
        last = AIMessage(
            content=NARRATION,
            tool_calls=[
                {"name": "search_emails", "args": {}, "id": "call_1"},
                {"name": "broken", "args": {}, "id": None},
            ],
        )

        result = await react_nodes.react_finalize_node(_state(last, iteration=6, budget=6), {})

        assert [m.tool_call_id for m in result["messages"]] == ["call_1"]

    async def test_the_promise_invariant_still_holds(self) -> None:
        """Closing the books must not resurrect the narration as an answer."""
        last = AIMessage(
            content=NARRATION,
            tool_calls=[{"name": "search_emails", "args": {}, "id": "call_1"}],
        )

        result = await react_nodes.react_finalize_node(_state(last, iteration=6, budget=6), {})

        assert result["react_agent_result"]["final_message"] == ""
        assert result["react_agent_result"]["truncation"]["reason"] == "max_iterations"

    async def test_the_history_it_leaves_is_provider_valid(self) -> None:
        """The whole point: what reaches the next turn must not be rejected.

        Replays the repaired history through the real Responses API serializer
        — the one that answered 400 on the production incident.
        """
        from langchain_openai.chat_models.base import _construct_responses_api_input

        last = AIMessage(
            content=[
                {"type": "text", "text": NARRATION},
                {
                    "type": "function_call",
                    "name": "search_emails",
                    "arguments": "{}",
                    "call_id": "call_1",
                },
            ],
            tool_calls=[{"name": "search_emails", "args": {}, "id": "call_1"}],
        )
        state = _state(last, iteration=6, budget=6)

        result = await react_nodes.react_finalize_node(state, {})

        history = state["messages"] + list(result["messages"])
        payload = _construct_responses_api_input(history)
        call_ids = {b.get("call_id") for b in payload if isinstance(b, dict)}
        answered = {
            b.get("call_id")
            for b in payload
            if isinstance(b, dict) and b.get("type") == "function_call_output"
        }
        assert "call_1" in call_ids
        assert "call_1" in answered, "the abandoned call reaches the provider unanswered"

    async def test_a_call_that_already_has_a_result_is_not_answered_twice(self) -> None:
        """Never duplicate a tool_call_id: two results for one call is exactly
        the malformed history this whole invariant exists to prevent."""
        last = AIMessage(
            content=NARRATION,
            tool_calls=[
                {"name": "search_emails", "args": {}, "id": "call_1"},
                {"name": "list_events", "args": {}, "id": "call_2"},
            ],
        )
        state = _state(last, iteration=6, budget=6)
        state["messages"].insert(
            -1, ToolMessage(content="already done", tool_call_id="call_1", name="search_emails")
        )

        result = await react_nodes.react_finalize_node(state, {})

        assert [m.tool_call_id for m in result["messages"]] == ["call_2"]

    async def test_the_reason_the_user_sees_is_the_reason_the_model_is_given(self) -> None:
        """One stop condition, one wording (ADR-248). Two defaulting rules would
        let the truncation banner and the tool result name different causes."""
        last = AIMessage(
            content=NARRATION,
            tool_calls=[{"name": "search_emails", "args": {}, "id": "call_1"}],
        )

        # No ceiling reached: the reason falls back to the shared default.
        result = await react_nodes.react_finalize_node(_state(last, iteration=2, budget=90), {})

        reason = result["react_agent_result"]["truncation"]["reason"]
        assert (
            reason in result["messages"][0].content
        ), "the model must be told the same stop condition the answer reports"
