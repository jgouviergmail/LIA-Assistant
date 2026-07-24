"""Unit tests for ``_build_resume_value`` — the HITL resume payload builder.

After the user answers an interrupt, this function turns their decision into the
dict handed back to the paused graph via ``Command(resume=...)``. Get it wrong
and **an action other than the one approved executes** — silently, since nothing
raises.

It dispatches on the FIRST pending action request's ``type``:

- ``draft_critique``  → ``{"action": confirm|edit|cancel, "draft_id", …}``
- ``plan_approval``   → ``{"decision": "APPROVE"|"REJECT"|"EDIT", …}``
- anything else       → ``{"approved": bool, "edited_args", "decisions"}``

That last branch is the default for the remaining HITL levels
(``destructive_confirm``, ``for_each_confirmation``, ``tool_confirmation``,
``entity_disambiguation``, ``clarification``), so it is very much live despite
the tool-level middleware being deprecated.

INPUT CONTRACT: the argument is a validated ``ToolApprovalDecision``, whose
field validator only admits ``approve`` / ``reject`` / ``edit`` (lowercase),
requires ``edited_action`` on an edit, and forbids an empty decision list. Tests
therefore use valid inputs only — several defensive fallbacks inside the
function (``"confirm"``/``"cancel"``/``"replan"`` mappings, the empty-decisions
guards) are unreachable through this call path and are deliberately NOT asserted
as behaviour.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.domains.agents.domain_schemas import ToolApprovalDecision
from src.domains.agents.services.hitl.resumption_strategies import _build_resume_value

pytestmark = pytest.mark.unit

RUN_ID = "run_test"
EDIT_ACTION = {"name": "search_contacts_tool", "args": {"query": "new"}}


def _build(decisions: list[dict[str, Any]], pending: list[dict] | None) -> dict[str, Any]:
    decision = ToolApprovalDecision(
        decisions=decisions,
        action_indices=list(range(len(decisions))),
    )
    return _build_resume_value(decision, pending, RUN_ID)


# ============================================================================
# Input contract (what can actually reach this function)
# ============================================================================


class TestInputContract:
    @pytest.mark.parametrize("bad_type", ["confirm", "cancel", "replan", "APPROVE", "wat"])
    def test_only_canonical_lowercase_types_are_accepted(self, bad_type: str) -> None:
        """Pins the upstream guard: anything else never reaches the builder."""
        with pytest.raises(ValidationError):
            ToolApprovalDecision(decisions=[{"type": bad_type}], action_indices=[0])

    def test_edit_requires_an_edited_action(self) -> None:
        with pytest.raises(ValidationError):
            ToolApprovalDecision(decisions=[{"type": "edit"}], action_indices=[0])

    def test_empty_decisions_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolApprovalDecision(decisions=[], action_indices=[])

    def test_action_indices_must_match_decisions(self) -> None:
        with pytest.raises(ValidationError):
            ToolApprovalDecision(decisions=[{"type": "approve"}], action_indices=[0, 1])


# ============================================================================
# Draft-critique branch
# ============================================================================


class TestDraftCritiqueBranch:
    PENDING = [{"type": "draft_critique", "draft_id": "draft_from_request"}]

    @pytest.mark.parametrize(
        ("decision_type", "expected_action"),
        [("approve", "confirm"), ("reject", "cancel")],
    )
    def test_action_mapping(self, decision_type: str, expected_action: str) -> None:
        assert _build([{"type": decision_type}], self.PENDING)["action"] == expected_action

    def test_edit_maps_to_edit(self) -> None:
        result = _build([{"type": "edit", "edited_action": EDIT_ACTION}], self.PENDING)
        assert result["action"] == "edit"

    def test_draft_id_prefers_the_decision(self) -> None:
        result = _build(
            [{"type": "approve", "draft_id": "from_decision"}],
            self.PENDING,
        )
        assert result["draft_id"] == "from_decision"

    def test_draft_id_falls_back_to_the_pending_request(self) -> None:
        assert _build([{"type": "approve"}], self.PENDING)["draft_id"] == "draft_from_request"

    def test_draft_id_falls_back_to_unknown(self) -> None:
        result = _build([{"type": "approve"}], [{"type": "draft_critique"}])
        assert result["draft_id"] == "unknown"

    def test_updated_content_accepts_both_key_names(self) -> None:
        by_new = _build(
            [{"type": "edit", "edited_action": EDIT_ACTION, "updated_content": {"body": "a"}}],
            self.PENDING,
        )
        by_legacy = _build(
            [{"type": "edit", "edited_action": EDIT_ACTION, "edited_content": {"body": "b"}}],
            self.PENDING,
        )
        assert by_new["updated_content"] == {"body": "a"}
        assert by_legacy["updated_content"] == {"body": "b"}

    def test_updated_content_is_none_when_absent(self) -> None:
        assert _build([{"type": "approve"}], self.PENDING)["updated_content"] is None

    def test_modification_instructions_only_present_when_provided(self) -> None:
        without = _build([{"type": "approve"}], self.PENDING)
        with_instructions = _build(
            [{"type": "approve", "modification_instructions": "make it shorter"}],
            self.PENDING,
        )
        assert "modification_instructions" not in without
        assert with_instructions["modification_instructions"] == "make it shorter"


# ============================================================================
# Plan-approval branch
# ============================================================================


class TestPlanApprovalBranch:
    PENDING = [{"type": "plan_approval"}]

    def test_approve(self) -> None:
        assert _build([{"type": "approve"}], self.PENDING) == {"decision": "APPROVE"}

    def test_reject_carries_a_default_reason(self) -> None:
        result = _build([{"type": "reject"}], self.PENDING)
        assert result["decision"] == "REJECT"
        assert result["rejection_reason"] == "User rejected plan"

    def test_reject_keeps_the_user_reason(self) -> None:
        result = _build([{"type": "reject", "rejection_reason": "wrong date"}], self.PENDING)
        assert result["rejection_reason"] == "wrong date"

    def test_edit_passes_explicit_modifications_through(self) -> None:
        mods = [{"step_id": "step_1", "field": "query", "value": "new"}]
        result = _build(
            [{"type": "edit", "edited_action": EDIT_ACTION, "modifications": mods}],
            self.PENDING,
        )
        assert result["decision"] == "EDIT"
        assert result["modifications"] == mods

    def test_edit_always_exposes_a_modifications_key(self) -> None:
        """The approval gate reads ``modifications`` unconditionally — it must
        never be missing, even when the user changed nothing resolvable."""
        result = _build([{"type": "edit", "edited_action": {"name": "t"}}], self.PENDING)
        assert result["decision"] == "EDIT"
        assert "modifications" in result


# ============================================================================
# Default (tool-level) branch — destructive_confirm, for_each, clarification…
# ============================================================================


class TestDefaultToolLevelBranch:
    PENDING = [{"type": "destructive_confirm"}]

    def test_approve_is_approved(self) -> None:
        result = _build([{"type": "approve"}], self.PENDING)
        assert result["approved"] is True
        assert result["edited_args"] is None

    def test_reject_is_not_approved(self) -> None:
        assert _build([{"type": "reject"}], self.PENDING)["approved"] is False

    def test_no_pending_requests_uses_this_branch(self) -> None:
        """Absent pending metadata, neither special format applies."""
        assert _build([{"type": "approve"}], None)["approved"] is True

    def test_edit_counts_as_approved_and_carries_args(self) -> None:
        result = _build([{"type": "edit", "edited_action": EDIT_ACTION}], self.PENDING)
        assert result["approved"] is True
        assert result["edited_args"] == {"query": "new"}

    def test_edit_without_args_leaves_edited_args_none(self) -> None:
        result = _build([{"type": "edit", "edited_action": {"name": "t"}}], self.PENDING)
        assert result["approved"] is True
        assert result["edited_args"] is None

    def test_only_the_first_edit_supplies_args(self) -> None:
        """Documented limitation ("single tool edit for now") — pinned so a
        future multi-edit implementation is a deliberate change."""
        result = _build(
            [
                {"type": "edit", "edited_action": {"name": "t", "args": {"pick": "first"}}},
                {"type": "edit", "edited_action": {"name": "t", "args": {"pick": "second"}}},
            ],
            self.PENDING,
        )
        assert result["edited_args"] == {"pick": "first"}

    def test_decisions_are_passed_through_verbatim(self) -> None:
        decisions = [{"type": "approve"}, {"type": "reject"}]
        assert _build(decisions, self.PENDING)["decisions"] == decisions

    @pytest.mark.parametrize(
        "decisions",
        [
            [{"type": "approve"}, {"type": "reject"}],
            [{"type": "reject"}, {"type": "approve"}],
            [{"type": "reject"}, {"type": "edit", "edited_action": EDIT_ACTION}],
        ],
    )
    def test_granular_rejection_is_collapsed_to_a_single_or(
        self, decisions: list[dict[str, Any]]
    ) -> None:
        """CHARACTERIZATION, not endorsement.

        ``ToolApprovalDecision`` documents "multiple tools (granular decisions)"
        — e.g. ``[{"type": "approve"}, {"type": "reject"}]`` — as a supported
        pattern. This branch reduces them with OR (``any``), and the granular
        ``decisions`` list it forwards is not read back by any consumer found in
        ``src/``, so a per-tool rejection does not survive this layer.

        Pinned rather than changed: flipping the reduction would alter the
        contract with the paused interrupt consumer, which this layer does not
        own. Any future change must be measured against this pin.
        """
        assert _build(decisions, self.PENDING)["approved"] is True


# ============================================================================
# Branch dispatch
# ============================================================================


class TestBranchDispatch:
    @pytest.mark.parametrize(
        ("pending_type", "expected_key"),
        [
            ("draft_critique", "action"),
            ("plan_approval", "decision"),
            ("destructive_confirm", "approved"),
            ("for_each_confirmation", "approved"),
            ("tool_confirmation", "approved"),
            ("entity_disambiguation", "approved"),
            ("clarification", "approved"),
        ],
    )
    def test_dispatch_is_driven_by_the_first_pending_type(
        self, pending_type: str, expected_key: str
    ) -> None:
        result = _build([{"type": "approve"}], [{"type": pending_type}])
        assert expected_key in result

    def test_only_the_first_pending_request_selects_the_format(self) -> None:
        """Mixed pending types resolve on the first entry — pinned because a
        silent change here would reformat every resume payload."""
        result = _build(
            [{"type": "approve"}],
            [{"type": "plan_approval"}, {"type": "draft_critique"}],
        )
        assert "decision" in result
        assert "action" not in result
