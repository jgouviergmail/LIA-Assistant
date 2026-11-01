"""How a pass's drafts reach the confirmation sequence (ADR-288, spec 2026-10-29 D5).

An iterative MCP task can queue several acts in one step, and a plan several
draft steps: the first is presented, the others queued, and they are ONE lot only
for the members of a FOR_EACH the person approved this turn. A tool confirmation
takes its own key. Both sequence keys are always written, so a previous turn's
values never leak into this one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.nodes.execution_state import _route_drafts
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo

pytestmark = [pytest.mark.unit]


def _draft(draft_id: str, draft_type: str = "tool_call", step_id: str = "s1") -> PendingDraftInfo:
    return PendingDraftInfo(
        draft_id=draft_id,
        draft_type=draft_type,
        draft_content={"tool_label": "Notes: delete note"},
        draft_summary="delete n2",
        registry_ids=[],
        tool_name="mcp_user_ab12cd34_delete_note",
        step_id=step_id,
    )


def _route(*drafts: PendingDraftInfo, state: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    outcome: Any = SimpleNamespace(pending_drafts=list(drafts))
    _route_drafts(result, outcome, state or {}, "plan-1", "run-1")  # type: ignore[arg-type]
    return result


class TestTheSequence:
    def test_several_drafts_are_asked_one_at_a_time(self) -> None:
        result = _route(_draft("d1"), _draft("d2", step_id="s2"), _draft("d3", step_id="s3"))

        assert result["pending_draft_critique"]["draft_id"] == "d1"
        assert [d["draft_id"] for d in result["pending_drafts_queue"]] == ["d2", "d3"]
        assert result["pending_drafts_grouped"] is False, "not a pre-approved FOR_EACH lot"
        assert result["confirmed_drafts"] == []

    def test_a_single_draft_is_presented_with_nothing_queued(self) -> None:
        result = _route(_draft("d1"))

        assert result["pending_draft_critique"]["draft_id"] == "d1"
        assert "pending_drafts_queue" not in result
        assert result["pending_drafts_grouped"] is False

    def test_a_tool_confirmation_takes_its_own_key(self) -> None:
        result = _route(_draft("t1", draft_type="tool_confirmation"), _draft("d1"))

        assert result["pending_tool_confirmation"]["draft_id"] == "t1"
        assert result["pending_draft_critique"]["draft_id"] == "d1"

    def test_no_draft_still_resets_the_sequence_keys(self) -> None:
        result = _route()

        assert result == {"pending_drafts_grouped": False, "confirmed_drafts": []}
