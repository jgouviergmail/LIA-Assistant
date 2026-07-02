"""Replay-safety tests for the draft-critique HITL loop (F24, 2026-07).

LangGraph re-executes the whole node on every resume: past ``interrupt()``
calls return their cached decisions, but everything else re-runs live. The
historical in-node while-loop therefore RE-RAN every past
``modifier.modify()`` LLM call on each resume — the confirmed draft could
differ from the one the user validated on screen.

These tests drive the REAL ``hitl_dispatch_node`` + ``route_from_hitl_dispatch``
inside a compiled mini-graph with an in-memory checkpointer, simulating true
interrupt/resume sequences, and assert the core invariant:

    the executed content is EXACTLY the content the user last saw,
    and each modification LLM call runs EXACTLY once.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.core.config import settings
from src.domains.agents.constants import NODE_DRAFT_CRITIQUE
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.hitl_dispatch_node import hitl_dispatch_node
from src.domains.agents.nodes.routing import route_from_hitl_dispatch
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo


class _SpyModifier:
    """Deterministic draft-modifier spy: counts calls, returns v1, v2, ..."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def modify(
        self,
        original_draft: dict[str, Any],
        instructions: str,
        draft_type: str,
        user_language: str,
        run_id: str,
        contact_context: Any = None,
    ) -> dict[str, Any]:
        self.calls.append(instructions)
        return {**original_draft, "summary": f"modified-v{len(self.calls)}"}


def _make_draft(draft_type: str = "event_create") -> PendingDraftInfo:
    return PendingDraftInfo(
        draft_id="draft-1",
        draft_type=draft_type,
        draft_content={"summary": "original", "start_datetime": "2026-07-03T10:00:00+02:00"},
        draft_summary="",
        registry_ids=[],  # empty → _build_contact_context is a no-op (no DB)
        tool_name="create_event_tool",
        step_id="step_0",
    )


def _build_graph() -> Any:
    graph = StateGraph(MessagesState)
    graph.add_node(NODE_DRAFT_CRITIQUE, hitl_dispatch_node)
    graph.add_node("initiative", lambda state: {})  # terminal stub
    graph.add_edge(START, NODE_DRAFT_CRITIQUE)
    graph.add_conditional_edges(
        NODE_DRAFT_CRITIQUE,
        route_from_hitl_dispatch,
        {NODE_DRAFT_CRITIQUE: NODE_DRAFT_CRITIQUE, "initiative": "initiative"},
    )
    graph.add_edge("initiative", END)
    return graph.compile(checkpointer=InMemorySaver())


def _initial_input(draft: PendingDraftInfo) -> dict[str, Any]:
    return {
        "messages": [],
        "pending_draft_critique": draft.model_dump(),
        "pending_drafts_queue": [],
        "user_language": "fr",
    }


def _interrupt_payload(result: dict[str, Any]) -> dict[str, Any]:
    interrupts = result.get("__interrupt__")
    assert interrupts, f"expected an interrupt, got keys={list(result.keys())}"
    return interrupts[0].value


@pytest.mark.unit
@pytest.mark.asyncio
class TestDraftCritiqueReplaySafety:
    """The executed draft is the one the user saw; modify() runs once per edit."""

    async def test_edit_then_confirm_runs_modify_exactly_once(self) -> None:
        spy = _SpyModifier()
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-edit-confirm"}}

        with patch(
            "src.domains.agents.services.hitl.draft_modifier.get_draft_modification_service",
            return_value=spy,
        ):
            # 1. Initial presentation → interrupt
            result = await graph.ainvoke(_initial_input(_make_draft()), config)
            payload = _interrupt_payload(result)
            assert payload["action_requests"][0]["draft_content"]["summary"] == "original"

            # 2. User asks for a modification → modify() runs, draft persisted,
            #    self-loop presents the MODIFIED draft in a new interrupt
            result = await graph.ainvoke(
                Command(resume={"action": "edit", "modification_instructions": "change title"}),
                config,
            )
            payload = _interrupt_payload(result)
            assert payload["action_requests"][0]["draft_content"]["summary"] == "modified-v1"
            assert spy.calls == ["change title"]

            # 3. User confirms → THE INVARIANT: executed content == displayed content,
            #    and the resume did NOT re-run the past modification
            result = await graph.ainvoke(Command(resume={"action": "confirm"}), config)

        action_result = result["draft_action_result"]
        assert action_result["action"] == "confirm"
        assert action_result["draft_content"]["summary"] == "modified-v1"
        assert spy.calls == ["change title"], "modify() must run exactly once per edit"
        assert result["pending_draft_critique"] is None
        assert result["draft_edit_iteration"] == 0  # loop state reset

    async def test_two_edits_then_confirm(self) -> None:
        spy = _SpyModifier()
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-two-edits"}}

        with patch(
            "src.domains.agents.services.hitl.draft_modifier.get_draft_modification_service",
            return_value=spy,
        ):
            await graph.ainvoke(_initial_input(_make_draft()), config)
            await graph.ainvoke(
                Command(resume={"action": "edit", "modification_instructions": "first"}), config
            )
            result = await graph.ainvoke(
                Command(resume={"action": "edit", "modification_instructions": "second"}), config
            )
            payload = _interrupt_payload(result)
            assert payload["action_requests"][0]["draft_content"]["summary"] == "modified-v2"

            result = await graph.ainvoke(Command(resume={"action": "confirm"}), config)

        assert result["draft_action_result"]["draft_content"]["summary"] == "modified-v2"
        assert spy.calls == ["first", "second"], "one modify() per edit — never replayed"

    async def test_clarify_question_surfaces_on_next_payload(self) -> None:
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-clarify"}}

        result = await graph.ainvoke(_initial_input(_make_draft()), config)
        assert "clarification_question" not in _interrupt_payload(result)["action_requests"][0]

        result = await graph.ainvoke(
            Command(resume={"action": "clarify", "clarification_question": "Quel titre ?"}),
            config,
        )
        payload = _interrupt_payload(result)
        assert payload["action_requests"][0]["clarification_question"] == "Quel titre ?"

        # The question is consumed after being shown: a subsequent edit-less
        # self-loop clears it
        result = await graph.ainvoke(
            Command(resume={"action": "edit", "modification_instructions": ""}), config
        )
        payload = _interrupt_payload(result)
        assert "clarification_question" not in payload["action_requests"][0]

    async def test_cancel_is_terminal_and_resets_loop_state(self) -> None:
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-cancel"}}

        await graph.ainvoke(_initial_input(_make_draft()), config)
        result = await graph.ainvoke(
            Command(resume={"action": "cancel", "reason": "changed my mind"}), config
        )

        assert result["draft_action_result"]["action"] == "cancel"
        assert result["pending_draft_critique"] is None
        assert result["draft_edit_iteration"] == 0

    async def test_replan_changes_type_and_self_loops(self) -> None:
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-replan"}}

        await graph.ainvoke(_initial_input(_make_draft(draft_type="event_update")), config)
        result = await graph.ainvoke(Command(resume={"action": "replan"}), config)

        payload = _interrupt_payload(result)
        assert payload["action_requests"][0]["draft_type"] == "event_delete"

        result = await graph.ainvoke(Command(resume={"action": "confirm"}), config)
        assert result["draft_action_result"]["draft_type"] == "event_delete"

    async def test_max_iterations_safety_cancel(self) -> None:
        graph = _build_graph()
        config = {"configurable": {"thread_id": "t-max"}}

        # Seed the loop counter at the limit (read from settings — never hardcoded)
        state = _initial_input(_make_draft())
        state["draft_edit_iteration"] = settings.api_max_items_per_request

        result = await graph.ainvoke(state, config)

        assert result["draft_action_result"]["action"] == "cancel"
        assert "Maximum modification iterations" in result["draft_action_result"]["reason"]
        assert result["pending_draft_critique"] is None
