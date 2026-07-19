"""Unit tests: clarification cancel-abort path (Lot 1 Phase 0).

Runtime-proven defect: a cancel intent during a clarification interrupt had
no exit — the flow replanned (with or without the cancel text) and the
validator re-flagged the same issues, looping back into the same interrupt.

The abort contract under test:
    - resume ``{"clarification": ..., "cancelled": True}`` → clarification_node
      returns the plan-rejection state (no replan, not approved, reason set)
      and raises the self-cleaning ``clarification_cancelled`` flag;
    - ``route_from_clarification`` sends that state to ``response``;
    - every normal path resets the flag to False so a stale value from an
      earlier turn can never divert a later clarification.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.domains.agents.constants import (
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_SEMANTIC_VALIDATION,
)
from src.domains.agents.nodes.clarification_node import clarification_node
from src.domains.agents.nodes.routing import route_from_clarification

INTERRUPT_PATH = "src.domains.agents.nodes.clarification_node.interrupt"


def _state_requiring_clarification() -> dict:
    """Minimal graph state that makes clarification_node reach interrupt()."""
    return {
        STATE_KEY_SEMANTIC_VALIDATION: {
            "requires_clarification": True,
            "clarification_questions": ["Which address should be used?"],
            "issues": [
                {
                    "issue_type": "wrong_parameters",
                    "description": "placeholder address",
                    "severity": "high",
                }
            ],
        },
        "user_language": "fr",
    }


@pytest.mark.unit
class TestClarificationNodeAbort:
    async def test_cancelled_resume_returns_rejection_state(self) -> None:
        resume = {"clarification": "Non, annule cette action", "cancelled": True}
        with patch(INTERRUPT_PATH, return_value=resume):
            result = await clarification_node(_state_requiring_clarification())

        assert result[STATE_KEY_NEEDS_REPLAN] is False
        assert result[STATE_KEY_PLAN_APPROVED] is False
        assert result[STATE_KEY_PLAN_REJECTION_REASON]
        assert result[STATE_KEY_SEMANTIC_VALIDATION]["clarification_cancelled"] is True
        # The clarification loop must be closed on abort too.
        assert result[STATE_KEY_SEMANTIC_VALIDATION]["requires_clarification"] is False

    async def test_info_resume_keeps_replan_path_and_resets_flag(self) -> None:
        resume = {"clarification": "utilise jean.dupont@gmail.com"}
        with patch(INTERRUPT_PATH, return_value=resume):
            result = await clarification_node(_state_requiring_clarification())

        assert result[STATE_KEY_NEEDS_REPLAN] is True
        assert STATE_KEY_PLAN_REJECTION_REASON not in result
        # Self-cleaning: normal passes explicitly reset the abort flag.
        assert result[STATE_KEY_SEMANTIC_VALIDATION]["clarification_cancelled"] is False


@pytest.mark.unit
class TestRouteFromClarification:
    def test_cancelled_routes_to_response(self) -> None:
        state = {STATE_KEY_SEMANTIC_VALIDATION: {"clarification_cancelled": True}}
        assert route_from_clarification(state) == "response"

    def test_normal_pass_routes_to_semantic_validator(self) -> None:
        state = {STATE_KEY_SEMANTIC_VALIDATION: {"clarification_cancelled": False}}
        assert route_from_clarification(state) == "semantic_validator"

    def test_missing_flag_defaults_to_semantic_validator(self) -> None:
        assert route_from_clarification({STATE_KEY_SEMANTIC_VALIDATION: {}}) == "semantic_validator"
        assert route_from_clarification({}) == "semantic_validator"
