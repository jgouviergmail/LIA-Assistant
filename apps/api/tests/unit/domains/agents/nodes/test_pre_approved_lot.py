"""Which drafts may be confirmed as ONE lot (ADR-288).

Only the members of a FOR_EACH step the person approved in THIS turn, all of
one type: they saw the list and said yes to the operation. Two independent
steps, a FOR_EACH nobody approved, a lot mixed with a stranger, or two types —
each draft is asked on its own.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.nodes.for_each_hitl_prep import is_pre_approved_lot

pytestmark = pytest.mark.unit


def _draft(draft_id: str, step_id: str | None, draft_type: str = "email") -> dict[str, Any]:
    return {"draft_id": draft_id, "draft_type": draft_type, "step_id": step_id}


def _ctx(*step_ids: str, approved: bool = True, plan_id: str = "p1", turn_id: int = 7) -> dict:
    return {
        "plan_id": plan_id,
        "turn_id": turn_id,
        "approved": approved,
        "steps": [{"step_id": sid} for sid in step_ids],
    }


class TestALotIsAnApprovedForEach:
    def test_members_of_an_approved_for_each_are_a_lot(self) -> None:
        drafts = [_draft("a", "step_2_item_0"), _draft("b", "step_2_item_1")]
        assert is_pre_approved_lot(drafts, _ctx("step_2"), plan_id="p1", turn_id=7) is True

    def test_two_independent_steps_are_not(self) -> None:
        drafts = [_draft("a", "step_1"), _draft("b", "step_2")]
        assert is_pre_approved_lot(drafts, None, plan_id="p1", turn_id=7) is False

    def test_a_for_each_nobody_approved_is_not(self) -> None:
        drafts = [_draft("a", "step_2_item_0"), _draft("b", "step_2_item_1")]
        ctx = _ctx("step_2", approved=False)
        assert is_pre_approved_lot(drafts, ctx, plan_id="p1", turn_id=7) is False

    def test_an_approval_from_another_turn_or_plan_is_not(self) -> None:
        drafts = [_draft("a", "step_2_item_0"), _draft("b", "step_2_item_1")]
        assert (
            is_pre_approved_lot(drafts, _ctx("step_2", turn_id=6), plan_id="p1", turn_id=7) is False
        )
        assert (
            is_pre_approved_lot(drafts, _ctx("step_2", plan_id="p0"), plan_id="p1", turn_id=7)
            is False
        )

    def test_a_stranger_in_the_lot_breaks_it(self) -> None:
        drafts = [_draft("a", "step_2_item_0"), _draft("b", "step_2_item_1"), _draft("c", "step_3")]
        assert is_pre_approved_lot(drafts, _ctx("step_2"), plan_id="p1", turn_id=7) is False

    def test_two_types_are_never_one_lot(self) -> None:
        drafts = [_draft("a", "step_2_item_0"), _draft("b", "step_2_item_1", "event")]
        assert is_pre_approved_lot(drafts, _ctx("step_2"), plan_id="p1", turn_id=7) is False

    def test_a_similar_step_name_is_not_a_member(self) -> None:
        """``step_2`` must not claim ``step_20_item_0``."""
        drafts = [_draft("a", "step_20_item_0"), _draft("b", "step_20_item_1")]
        assert is_pre_approved_lot(drafts, _ctx("step_2"), plan_id="p1", turn_id=7) is False

    def test_a_single_draft_is_not_a_lot(self) -> None:
        assert (
            is_pre_approved_lot(
                [_draft("a", "step_2_item_0")], _ctx("step_2"), plan_id="p1", turn_id=7
            )
            is False
        )
