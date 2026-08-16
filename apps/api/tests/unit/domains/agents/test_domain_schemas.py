"""Contract tests for ``ToolApprovalDecision`` (src/domains/agents/domain_schemas.py).

After the user answers a HITL interrupt, this schema is the gate every decision
payload passes through before the resume flow (``parse_approval_decision`` /
``build_structured_decision``) maps it to the interrupt's resume value. Get the
gate wrong and **an action other than the one approved executes** — silently,
since nothing raises downstream.

These tests were preserved from ``test_build_resume_value.py`` when the dead
``_build_resume_value`` helper was deleted with its unwired strategy class
(ADR-222): they never exercised that helper — they pin the schema validator
that still guards the live resume path.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.domains.agents.domain_schemas import ToolApprovalDecision

pytestmark = pytest.mark.unit


class TestToolApprovalDecisionContract:
    @pytest.mark.parametrize("bad_type", ["confirm", "cancel", "replan", "APPROVE", "wat"])
    def test_only_canonical_lowercase_types_are_accepted(self, bad_type: str) -> None:
        """Pins the guard: anything else never reaches the resume flow."""
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
