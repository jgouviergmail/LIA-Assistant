"""One ReAct call may hand up several confirmations; each is asked in turn (spec D5).

An MCP App server keeps its task tool in ReAct (spec D8), and its sub-loop can
queue several confirmations in one task. The loop used to read ONE draft off a
call: the others were lost. The first is now presented and the rest queued —
the existing one-at-a-time sequence of ADR-288, never grouped.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from src.domains.agents.nodes.react_call_execution import Executed, _draft_update
from src.domains.agents.nodes.react_drafts import extract_drafts
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = [pytest.mark.unit]


def _pending(draft_id: str) -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "draft_type": "tool_call",
        "draft_content": {"tool_name": "mcp_user_abcd1234_delete_note", "tool_args": {}},
        "draft_summary": "Confirm the deletion",
        "registry_ids": [draft_id],
        "tool_name": "mcp_user_abcd1234_delete_note",
        "step_id": None,
    }


def _answer() -> ToolMessage:
    return ToolMessage(content="done", tool_call_id="c1", name="mcp_user_abcd1234_task")


class TestEveryConfirmationOfACallIsAsked:
    def test_extract_drafts_reads_every_draft_of_one_call(self) -> None:
        output = UnifiedToolOutput.data_success(
            message="Archived two notes.",
            metadata={
                "requires_confirmation": True,
                "pending_drafts": [_pending("d1"), _pending("d2")],
            },
        )

        assert [d["draft_id"] for d in extract_drafts(output, "mcp_user_abcd1234_task")] == [
            "d1",
            "d2",
        ]

    def test_react_queues_all_but_the_first(self) -> None:
        update = _draft_update(
            Executed(_answer(), drafts=[_pending("d1"), _pending("d2")]),
            {"react_iteration": 3},  # type: ignore[typeddict-item]
        )

        assert update["pending_draft_critique"] == _pending("d1")
        assert update["pending_drafts_queue"] == [_pending("d2")]
        assert update["pending_drafts_grouped"] is False, "never a lot: asked one at a time"
        assert update["react_agent_result"] == {
            "final_message": "",
            "iteration_count": 3,
            "mode": "react",
        }

    def test_a_call_without_a_draft_clears_any_previous_question(self) -> None:
        update = _draft_update(Executed(_answer()), {})  # type: ignore[typeddict-item]

        assert update["pending_draft_critique"] is None
        assert update["pending_drafts_queue"] == []
        assert "react_agent_result" not in update
