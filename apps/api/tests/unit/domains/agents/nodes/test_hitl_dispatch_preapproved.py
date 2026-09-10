"""A draft the person already approved on their ticket is not asked again (lot 7).

Driven through the REAL ``hitl_dispatch_node`` on a compiled graph, so the
assertion is about what LangGraph sees — an interrupt or none — and not about
a helper's return value. The replay is let through on the IDENTITY of what
was shown (draft type and content digest, ADR-092), the approval is spent on
the first match, and a rebuilt draft that differs asks again.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.domains.agents.api.run_origin import (
    ApprovedDraft,
    RunOrigin,
    out_of_turn_origin_ctx,
)
from src.domains.agents.constants import NODE_DRAFT_CRITIQUE
from src.domains.agents.effects.digest import drafts_digest
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.hitl_dispatch_node import hitl_dispatch_node
from src.domains.agents.nodes.routing import route_from_hitl_dispatch
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

CONTENT = {
    "tool_name": "mcp_x_delete",
    "tool_label": "x: delete",
    "tool_args": {"target": "the archive"},
}


def _draft(content: dict[str, Any] | None = None) -> PendingDraftInfo:
    return PendingDraftInfo(
        draft_id="draft-1",
        draft_type="tool_call",
        draft_content=content if content is not None else dict(CONTENT),
        draft_summary="",
        registry_ids=[],  # no registry, no database
        tool_name="mcp_x_delete",
        step_id=None,
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


def _input(draft: PendingDraftInfo) -> dict[str, Any]:
    return {
        "messages": [],
        "pending_draft_critique": draft.model_dump(),
        "pending_drafts_queue": [],
        "user_language": "fr",
    }


def _origin(approved: ApprovedDraft | None) -> RunOrigin:
    return RunOrigin(
        kind="workboard",
        ticket_id="t-1",
        run_id="r-1",
        can_carry_draft=True,
        approved_draft=approved,
    )


async def _present(draft: PendingDraftInfo, origin: RunOrigin | None) -> dict[str, Any]:
    token = out_of_turn_origin_ctx.set(origin) if origin is not None else None
    try:
        result: dict[str, Any] = await _graph().ainvoke(
            _input(draft), {"configurable": {"thread_id": "t-preapproved"}}
        )
        return result
    finally:
        if token is not None:
            out_of_turn_origin_ctx.reset(token)


class TestTheApprovedDraftRunsWithoutAsking:
    async def test_the_identical_draft_is_confirmed_by_the_ticket(self) -> None:
        origin = _origin(ApprovedDraft(draft_type="tool_call", digest=drafts_digest([CONTENT])))

        result = await _present(_draft(), origin)

        assert "__interrupt__" not in result
        assert result["draft_action_result"]["action"] == "confirm"
        assert result["draft_action_result"]["draft_content"] == CONTENT
        assert result["pending_draft_critique"] is None

    async def test_the_approval_is_spent_by_the_match(self) -> None:
        origin = _origin(ApprovedDraft(draft_type="tool_call", digest=drafts_digest([CONTENT])))
        await _present(_draft(), origin)
        assert origin.approved_draft is None

    async def test_the_content_the_person_approved_is_what_runs(self) -> None:
        """ADR-092 pointed at the replay: the executed content is the REBUILT
        one, which matched the digest, so it is byte for byte what was shown."""
        origin = _origin(ApprovedDraft(draft_type="tool_call", digest=drafts_digest([CONTENT])))
        rebuilt = {**CONTENT}  # a fresh dict, same identity
        result = await _present(_draft(rebuilt), origin)
        assert result["draft_action_result"]["draft_content"] == CONTENT


class TestAnythingElseAsksAgain:
    async def test_a_different_content_interrupts(self) -> None:
        origin = _origin(ApprovedDraft(draft_type="tool_call", digest=drafts_digest([CONTENT])))
        other = {**CONTENT, "tool_args": {"target": "everything"}}

        result = await _present(_draft(other), origin)

        assert result["__interrupt__"], "a draft that differs must be shown again"
        assert origin.approved_draft is not None, "an unmatched approval is not spent"

    async def test_a_different_type_interrupts(self) -> None:
        origin = _origin(ApprovedDraft(draft_type="email", digest=drafts_digest([CONTENT])))
        result = await _present(_draft(), origin)
        assert result["__interrupt__"]

    async def test_a_run_without_an_approval_interrupts(self) -> None:
        result = await _present(_draft(), _origin(None))
        assert result["__interrupt__"]

    async def test_the_chat_is_untouched(self) -> None:
        result = await _present(_draft(), None)
        assert result["__interrupt__"]
        assert result["__interrupt__"][0].value["action_requests"][0]["draft_id"] == "draft-1"


class TestABatchIsOneIdentity:
    """Approving three drafts approves those three, in that order, and nothing else."""

    SECOND = {"tool_name": "mcp_x_delete", "tool_label": "x: delete", "tool_args": {"target": "b"}}

    def _queued(self) -> dict[str, Any]:
        return {
            "draft_id": "draft-2",
            "draft_type": "tool_call",
            "draft_content": dict(self.SECOND),
            "draft_summary": "",
            "registry_ids": [],
            "tool_name": "mcp_x_delete",
            "step_id": None,
        }

    async def _present_batch(self, origin: RunOrigin) -> dict[str, Any]:
        from src.domains.agents.api.run_origin import out_of_turn_origin_ctx as ctx

        token = ctx.set(origin)
        try:
            payload = {**_input(_draft()), "pending_drafts_queue": [self._queued()]}
            result: dict[str, Any] = await _graph().ainvoke(
                payload, {"configurable": {"thread_id": "t-batch"}}
            )
            return result
        finally:
            ctx.reset(token)

    async def test_the_whole_batch_is_confirmed_on_its_own_identity(self) -> None:
        from src.domains.agents.effects.digest import drafts_digest

        origin = _origin(
            ApprovedDraft(draft_type="tool_call", digest=drafts_digest([CONTENT, self.SECOND]))
        )
        result = await self._present_batch(origin)

        assert "__interrupt__" not in result
        assert result["draft_action_result"]["action"] == "confirm_batch"
        assert [item["draft_id"] for item in result["draft_action_result"]["batch"]] == [
            "draft-1",
            "draft-2",
        ]

    async def test_an_approval_of_one_draft_never_confirms_a_batch(self) -> None:
        """The person saw one; the run built two: ask again, with both."""
        from src.domains.agents.effects.digest import drafts_digest

        origin = _origin(ApprovedDraft(draft_type="tool_call", digest=drafts_digest([CONTENT])))
        result = await self._present_batch(origin)

        assert result["__interrupt__"]
        assert result["__interrupt__"][0].value["action_requests"][0]["batch_total"] == 2
