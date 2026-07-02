"""Replay-safety tests for the FOR_EACH bulk-confirmation node (F9, 2026-07).

Historically the FOR_EACH confirmation lived inside task_orchestrator as a
while-loop around ``interrupt()``: every resume re-executed the whole node,
re-fetching the providers (real API calls) and re-running every past LLM
item-filter call (non-deterministic) — the previews the user approved could
diverge from the items executed.

These tests drive the REAL ``for_each_confirm_node`` + its REAL router inside
a compiled mini-graph (InMemorySaver, true interrupt/resume sequences) and
assert the invariant:

    the item list the user last saw is EXACTLY the list handed back for
    execution, and each LLM filter call runs EXACTLY once.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.core.config import settings
from src.domains.agents.constants import (
    HITL_DECISION_APPROVE,
    HITL_DECISION_EDIT,
    HITL_DECISION_REJECT,
    NODE_FOR_EACH_CONFIRM,
    NODE_TASK_ORCHESTRATOR,
    STATE_KEY_FOR_EACH_HITL_CTX,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.for_each_confirm_node import for_each_confirm_node
from src.domains.agents.nodes.routing import route_from_for_each_confirm


class _SpyFilter:
    """Deterministic item-filter spy: records calls, returns scripted indices."""

    def __init__(self, scripted: list[list[int]]) -> None:
        self.scripted = scripted
        self.calls: list[str] = []

    async def filter(
        self,
        item_previews: list[dict[str, Any]],
        exclude_criteria: str,
        user_language: str,
        run_id: str,
    ) -> list[int]:
        self.calls.append(exclude_criteria)
        return self.scripted[len(self.calls) - 1]


def _make_ctx(n_items: int = 4) -> dict[str, Any]:
    return {
        "run_id": "run-1",
        "plan_id": "plan-1",
        "turn_id": 1,
        "steps": [{"step_id": "s1", "tool_name": "delete_email_tool", "for_each_max": n_items}],
        "pre_executed_steps": {"get_emails": {"emails": [{"id": f"e{i}"} for i in range(n_items)]}},
        "pre_exec_registry": {},
        "item_previews": [{"label": f"item-{i}"} for i in range(n_items)],
        "total_affected": n_items,
        "filtered_indices": None,
        "iteration": 0,
        "approved": False,
    }


def _build_graph() -> Any:
    graph = StateGraph(MessagesState)
    graph.add_node(NODE_FOR_EACH_CONFIRM, for_each_confirm_node)
    graph.add_node(NODE_TASK_ORCHESTRATOR, lambda state: {})  # capture stub
    graph.add_node("initiative", lambda state: {})  # terminal stub
    graph.add_edge(START, NODE_FOR_EACH_CONFIRM)
    graph.add_conditional_edges(
        NODE_FOR_EACH_CONFIRM,
        route_from_for_each_confirm,
        {
            NODE_FOR_EACH_CONFIRM: NODE_FOR_EACH_CONFIRM,
            NODE_TASK_ORCHESTRATOR: NODE_TASK_ORCHESTRATOR,
            "initiative": "initiative",
        },
    )
    graph.add_edge(NODE_TASK_ORCHESTRATOR, END)
    graph.add_edge("initiative", END)
    return graph.compile(checkpointer=InMemorySaver())


def _initial_input(ctx: dict[str, Any]) -> dict[str, Any]:
    return {"messages": [], STATE_KEY_FOR_EACH_HITL_CTX: ctx, "user_language": "fr"}


def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any]:
    interrupts = result.get("__interrupt__")
    assert interrupts, f"expected an interrupt, got keys={list(result.keys())}"
    return interrupts[0].value


@pytest.mark.unit
@pytest.mark.asyncio
class TestForEachConfirmReplaySafety:
    """The approved list is exactly the last displayed list; filters run once."""

    async def test_approve_hands_context_back_untouched(self) -> None:
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-approve"}}

        result = await graph.ainvoke(_initial_input(_make_ctx()), config)
        payload = _interrupt_payload(result)
        assert payload["action_requests"][0]["total_affected"] == 4

        result = await graph.ainvoke(Command(resume={"decision": HITL_DECISION_APPROVE}), config)

        ctx = result[STATE_KEY_FOR_EACH_HITL_CTX]
        assert ctx["approved"] is True
        assert ctx["filtered_indices"] is None
        assert len(ctx["item_previews"]) == 4

    async def test_edit_then_approve_filter_runs_once_and_list_matches(self) -> None:
        spy = _SpyFilter(scripted=[[0, 2, 3]])
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-edit"}}

        with patch(
            "src.domains.agents.nodes.for_each_confirm_node.get_item_filter_service",
            return_value=spy,
        ):
            await graph.ainvoke(_initial_input(_make_ctx()), config)
            result = await graph.ainvoke(
                Command(
                    resume={"decision": HITL_DECISION_EDIT, "exclude_criteria": "remove item-1"}
                ),
                config,
            )
            # The NEXT interrupt shows the filtered list (checkpointed before it)
            payload = _interrupt_payload(result)
            previews = payload["action_requests"][0]["item_previews"]
            assert [p["label"] for p in previews] == ["item-0", "item-2", "item-3"]

            result = await graph.ainvoke(
                Command(resume={"decision": HITL_DECISION_APPROVE}), config
            )

        ctx = result[STATE_KEY_FOR_EACH_HITL_CTX]
        assert ctx["approved"] is True
        # THE INVARIANT: what is handed back for execution is what was displayed
        assert [p["label"] for p in ctx["item_previews"]] == ["item-0", "item-2", "item-3"]
        assert ctx["filtered_indices"] == [0, 2, 3]
        assert spy.calls == ["remove item-1"], "filter must run exactly once, never replayed"

    async def test_two_edits_cumulative_index_mapping(self) -> None:
        # 4 items → keep [0,2,3] → then keep [1,2] of the remaining → original [2,3]
        spy = _SpyFilter(scripted=[[0, 2, 3], [1, 2]])
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-two-edits"}}

        with patch(
            "src.domains.agents.nodes.for_each_confirm_node.get_item_filter_service",
            return_value=spy,
        ):
            await graph.ainvoke(_initial_input(_make_ctx()), config)
            await graph.ainvoke(
                Command(resume={"decision": HITL_DECISION_EDIT, "exclude_criteria": "first"}),
                config,
            )
            result = await graph.ainvoke(
                Command(resume={"decision": HITL_DECISION_EDIT, "exclude_criteria": "second"}),
                config,
            )
            payload = _interrupt_payload(result)
            previews = payload["action_requests"][0]["item_previews"]
            assert [p["label"] for p in previews] == ["item-2", "item-3"]

            result = await graph.ainvoke(
                Command(resume={"decision": HITL_DECISION_APPROVE}), config
            )

        ctx = result[STATE_KEY_FOR_EACH_HITL_CTX]
        assert ctx["filtered_indices"] == [2, 3]  # cumulative mapping to ORIGINAL items
        assert spy.calls == ["first", "second"]

    async def test_reject_cancels_and_purges_context(self) -> None:
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-reject"}}

        await graph.ainvoke(_initial_input(_make_ctx()), config)
        result = await graph.ainvoke(
            Command(resume={"decision": HITL_DECISION_REJECT, "rejection_reason": "non"}), config
        )

        assert result[STATE_KEY_FOR_EACH_HITL_CTX] is None
        assert result["for_each_cancelled"] is True
        assert result["draft_action_result"]["action"] == "cancel"
        assert result["draft_action_result"]["draft_type"] == "for_each_bulk"

    async def test_all_items_excluded_cancels(self) -> None:
        spy = _SpyFilter(scripted=[[]])
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-all-excluded"}}

        with patch(
            "src.domains.agents.nodes.for_each_confirm_node.get_item_filter_service",
            return_value=spy,
        ):
            await graph.ainvoke(_initial_input(_make_ctx()), config)
            result = await graph.ainvoke(
                Command(resume={"decision": HITL_DECISION_EDIT, "exclude_criteria": "everything"}),
                config,
            )

        assert result[STATE_KEY_FOR_EACH_HITL_CTX] is None
        assert result["for_each_cancelled"] is True

    async def test_max_iterations_safety_cancel(self) -> None:
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-max"}}

        ctx = _make_ctx()
        ctx["iteration"] = settings.api_max_items_per_request  # read from settings

        result = await graph.ainvoke(_initial_input(ctx), config)

        assert result[STATE_KEY_FOR_EACH_HITL_CTX] is None
        assert result["draft_action_result"]["reason"] == "Max HITL iterations reached"
