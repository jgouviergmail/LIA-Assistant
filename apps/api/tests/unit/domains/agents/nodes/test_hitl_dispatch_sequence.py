"""Several drafts in one turn are reviewed ONE AT A TIME (ADR-288).

Measured 2026-09-16 on Docker dev: "send an e-mail to X saying all is well and
an e-mail to Y about calling Hua" produced two drafts, ONE question on the
first, and the person's « Valider » sent BOTH — the second never shown on a
card, never editable. The queue behind it was written for FOR_EACH, where the
person had already approved the lot as a whole; it was applied to every
multi-draft turn, whatever the type and the mode.

These tests drive the REAL ``hitl_dispatch_node`` + ``route_from_hitl_dispatch``
in a compiled mini-graph with an in-memory checkpointer, resuming exactly as
the chat does. Contract:

- a queue that is NOT a pre-approved lot is consumed one draft per interrupt,
  each with its own card, its own edit loop and its own edit counter;
- the decisions are banked and executed together at the end, in order, each
  under its own type; a cancelled draft is skipped, not silently dropped;
- a pre-approved FOR_EACH lot keeps its single grouped confirmation.
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

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class _SpyModifier:
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
        sender_name: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(instructions)
        return {**original_draft, "subject": f"modified-v{len(self.calls)}"}


def _mail(draft_id: str, to: str) -> PendingDraftInfo:
    return PendingDraftInfo(
        draft_id=draft_id,
        draft_type="email",
        draft_content={"to": to, "subject": f"subject of {draft_id}", "body": "hello"},
        draft_summary="",
        registry_ids=[],
        tool_name="send_email_tool",
        step_id=f"step_{draft_id[-1]}",
    )


def _event(draft_id: str) -> PendingDraftInfo:
    return PendingDraftInfo(
        draft_id=draft_id,
        draft_type="event_create",
        draft_content={"summary": "Call Hua", "start_datetime": "2026-09-17T10:00:00+02:00"},
        draft_summary="",
        registry_ids=[],
        tool_name="create_event_tool",
        step_id="step_3",
    )


def _graph() -> Any:
    graph = StateGraph(MessagesState)
    graph.add_node(NODE_DRAFT_CRITIQUE, hitl_dispatch_node)
    graph.add_node("initiative", lambda state: {})
    graph.add_edge(START, NODE_DRAFT_CRITIQUE)
    graph.add_conditional_edges(
        NODE_DRAFT_CRITIQUE,
        route_from_hitl_dispatch,
        {NODE_DRAFT_CRITIQUE: NODE_DRAFT_CRITIQUE, "initiative": "initiative"},
    )
    graph.add_edge("initiative", END)
    return graph.compile(checkpointer=InMemorySaver())


def _input(first: PendingDraftInfo, *queued: PendingDraftInfo, grouped: bool = False) -> dict:
    return {
        "messages": [],
        "pending_draft_critique": first.model_dump(),
        "pending_drafts_queue": [d.model_dump() for d in queued],
        "pending_drafts_grouped": grouped,
        "user_language": "fr",
    }


def _request(result: dict[str, Any]) -> dict[str, Any]:
    interrupts = result.get("__interrupt__")
    assert interrupts, f"expected an interrupt, got keys={list(result.keys())}"
    request: dict[str, Any] = interrupts[0].value["action_requests"][0]
    return request


def _batch_ids(result: dict[str, Any]) -> list[tuple[str, str]]:
    action_result = result["draft_action_result"]
    assert action_result["action"] == "confirm_batch"
    return [(item["action"], item["draft_id"]) for item in action_result["batch"]]


class TestIndependentDraftsAreReviewedOneByOne:
    async def test_the_second_draft_gets_its_own_question(self) -> None:
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq"}}

        first = await graph.ainvoke(
            _input(_mail("draft-1", "a@x"), _mail("draft-2", "b@x")), config
        )
        request = _request(first)
        assert request["draft_id"] == "draft-1"
        assert "batch_total" not in request and "batch_drafts" not in request
        assert (request["sequence_index"], request["sequence_total"]) == (1, 2)

        second = await graph.ainvoke(Command(resume={"action": "confirm"}), config)
        request = _request(second)
        assert request["draft_id"] == "draft-2"
        assert request["draft_content"]["to"] == "b@x"
        assert (request["sequence_index"], request["sequence_total"]) == (2, 2)
        assert not second.get("draft_action_result")

    async def test_the_first_question_carries_the_whole_sequence(self) -> None:
        """The summary the person reads before the first card (ADR-289) lists
        every draft of the sequence; a later question repeats nothing."""
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq-summary"}}

        first = await graph.ainvoke(_input(_mail("draft-1", "a@x"), _event("draft-2")), config)
        drafts = _request(first)["sequence_drafts"]
        assert [(d["draft_id"], d["draft_type"]) for d in drafts] == [
            ("draft-1", "email"),
            ("draft-2", "event_create"),
        ]
        assert drafts[1]["draft_content"]["summary"] == "Call Hua"

        second = await graph.ainvoke(Command(resume={"action": "confirm"}), config)
        assert "sequence_drafts" not in _request(second)

    async def test_a_re_presented_first_draft_does_not_repeat_the_summary(self) -> None:
        spy = _SpyModifier()
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq-summary-edit"}}
        with patch(
            "src.domains.agents.services.hitl.draft_modifier.get_draft_modification_service",
            return_value=spy,
        ):
            first = await graph.ainvoke(
                _input(_mail("draft-1", "a@x"), _mail("draft-2", "b@x")), config
            )
            assert "sequence_drafts" in _request(first)
            edited = await graph.ainvoke(
                Command(resume={"action": "edit", "modification_instructions": "shorter"}),
                config,
            )
        request = _request(edited)
        assert request["draft_id"] == "draft-1"
        assert (request["sequence_index"], request["sequence_total"]) == (1, 2)
        assert "sequence_drafts" not in request

    async def test_the_decisions_are_executed_together_in_order(self) -> None:
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq-exec"}}
        await graph.ainvoke(_input(_mail("draft-1", "a@x"), _event("draft-2")), config)
        await graph.ainvoke(Command(resume={"action": "confirm"}), config)
        done = await graph.ainvoke(Command(resume={"action": "confirm"}), config)

        assert _batch_ids(done) == [("confirm", "draft-1"), ("confirm", "draft-2")]
        types = [item["draft_type"] for item in done["draft_action_result"]["batch"]]
        assert types == ["email", "event_create"], "each draft keeps its OWN type"
        assert done["pending_draft_critique"] is None
        assert done["pending_drafts_queue"] == []
        assert done["confirmed_drafts"] == []

    async def test_cancelling_the_first_still_asks_the_second(self) -> None:
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq-cancel-one"}}
        await graph.ainvoke(_input(_mail("draft-1", "a@x"), _mail("draft-2", "b@x")), config)
        second = await graph.ainvoke(
            Command(resume={"action": "cancel", "reason": "not this one"}), config
        )
        assert _request(second)["draft_id"] == "draft-2"

        done = await graph.ainvoke(Command(resume={"action": "confirm"}), config)
        assert _batch_ids(done) == [("cancel", "draft-1"), ("confirm", "draft-2")]
        assert done["draft_action_result"]["batch"][0]["reason"] == "not this one"

    async def test_cancelling_every_draft_is_a_plain_cancellation(self) -> None:
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq-cancel-all"}}
        await graph.ainvoke(_input(_mail("draft-1", "a@x"), _mail("draft-2", "b@x")), config)
        await graph.ainvoke(Command(resume={"action": "cancel"}), config)
        done = await graph.ainvoke(Command(resume={"action": "cancel"}), config)

        assert done["draft_action_result"]["action"] == "cancel"
        assert done["confirmed_drafts"] == []

    async def test_an_edit_changes_only_the_draft_on_screen(self) -> None:
        spy = _SpyModifier()
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq-edit"}}
        with patch(
            "src.domains.agents.services.hitl.draft_modifier.get_draft_modification_service",
            return_value=spy,
        ):
            await graph.ainvoke(_input(_mail("draft-1", "a@x"), _mail("draft-2", "b@x")), config)
            await graph.ainvoke(Command(resume={"action": "confirm"}), config)
            edited = await graph.ainvoke(
                Command(resume={"action": "edit", "modification_instructions": "shorter"}),
                config,
            )
            request = _request(edited)
            assert request["draft_id"] == "draft-2"
            assert request["draft_content"]["subject"] == "modified-v1"
            done = await graph.ainvoke(Command(resume={"action": "confirm"}), config)

        batch = done["draft_action_result"]["batch"]
        assert batch[0]["draft_content"]["subject"] == "subject of draft-1"
        assert batch[1]["draft_content"]["subject"] == "modified-v1"
        assert spy.calls == ["shorter"]

    async def test_the_edit_counter_restarts_for_each_draft(self) -> None:
        spy = _SpyModifier()
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq-counter"}}
        with patch(
            "src.domains.agents.services.hitl.draft_modifier.get_draft_modification_service",
            return_value=spy,
        ):
            await graph.ainvoke(_input(_mail("draft-1", "a@x"), _mail("draft-2", "b@x")), config)
            edited = await graph.ainvoke(
                Command(resume={"action": "edit", "modification_instructions": "x"}), config
            )
            assert edited["draft_edit_iteration"] == 1
            second = await graph.ainvoke(Command(resume={"action": "confirm"}), config)

        assert _request(second)["draft_id"] == "draft-2"
        assert second["draft_edit_iteration"] == 0

    async def test_running_out_of_edits_on_one_keeps_the_others(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The safety cancel is about ONE draft: what was confirmed before it
        is still executed, what was queued after it is reported cancelled."""
        monkeypatch.setattr(settings, "api_max_items_per_request", 1)
        spy = _SpyModifier()
        graph = _graph()
        config = {"configurable": {"thread_id": "t-seq-max"}}
        with patch(
            "src.domains.agents.services.hitl.draft_modifier.get_draft_modification_service",
            return_value=spy,
        ):
            await graph.ainvoke(
                _input(_mail("draft-1", "a@x"), _mail("draft-2", "b@x"), _mail("draft-3", "c@x")),
                config,
            )
            await graph.ainvoke(Command(resume={"action": "confirm"}), config)
            done = await graph.ainvoke(
                Command(resume={"action": "edit", "modification_instructions": "x"}), config
            )

        assert _batch_ids(done) == [
            ("confirm", "draft-1"),
            ("cancel", "draft-2"),
            ("cancel", "draft-3"),
        ]
        assert done["pending_draft_critique"] is None


class TestAPreApprovedLotStaysGrouped:
    async def test_one_confirmation_executes_the_whole_lot(self) -> None:
        graph = _graph()
        config = {"configurable": {"thread_id": "t-grouped"}}
        first = await graph.ainvoke(
            _input(_mail("draft-1", "a@x"), _mail("draft-2", "b@x"), grouped=True), config
        )
        request = _request(first)
        assert request["batch_total"] == 2
        assert [d["draft_id"] for d in request["batch_drafts"]] == ["draft-1", "draft-2"]
        assert "sequence_index" not in request

        done = await graph.ainvoke(Command(resume={"action": "confirm"}), config)
        assert _batch_ids(done) == [("confirm", "draft-1"), ("confirm", "draft-2")]
        assert done["pending_drafts_grouped"] is False
