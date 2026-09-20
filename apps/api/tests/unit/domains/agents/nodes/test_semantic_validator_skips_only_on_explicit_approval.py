"""The semantic validator skips its work only on the person's EXPLICIT approval.

Measured on dev 2026-09-19 (24 h of logs): 11 « plan approved, skipping » and
ZERO validations — the router resets ``plan_approved`` to ``None`` at every
turn, and the skip read « not refused » as « approved » since 2026-09-05
(ADR-263). An early « insufficient content » detection was therefore never
forwarded to the clarification node: the approval gate found no plan and the
person was told their plan was rejected instead of being asked a question.
"""

from __future__ import annotations

import pytest

from src.domains.agents.constants import (
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_SEMANTIC_VALIDATION,
)
from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.semantic_validator import (
    PlanSemanticValidator,
    SemanticValidationResult,
)

pytestmark = pytest.mark.unit


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p",
        user_id="u",
        session_id="s",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="event_agent",
                tool_name="get_events_tool",
                parameters={},
            )
        ],
    )


def _early_detection() -> SemanticValidationResult:
    return SemanticValidationResult(
        is_valid=False,
        issues=[],
        confidence=0.9,
        requires_clarification=True,
        clarification_questions=["Which day?"],
        validation_duration_seconds=0.0,
    )


@pytest.mark.parametrize("plan_approved", [None, False], ids=["nobody_looked", "refused"])
async def test_an_early_detection_is_forwarded_unless_the_person_approved(
    monkeypatch: pytest.MonkeyPatch, plan_approved: bool | None
) -> None:
    validated = []

    async def fake_validate(self, **kwargs):  # noqa: ANN001, ANN003
        validated.append(kwargs)
        return _early_detection()

    monkeypatch.setattr(PlanSemanticValidator, "validate", fake_validate)
    updates = await semantic_validator_node(
        {
            STATE_KEY_PLAN_APPROVED: plan_approved,
            STATE_KEY_EXECUTION_PLAN: None,
            STATE_KEY_SEMANTIC_VALIDATION: _early_detection(),
            STATE_KEY_PLANNER_ITERATION: 0,
            "user_language": "fr",
        }
    )
    # No plan yet: the planner's early detection is preserved for the clarification node.
    assert updates[STATE_KEY_SEMANTIC_VALIDATION].requires_clarification is True
    assert validated == []


async def test_a_fresh_turn_validates_its_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    validated = []

    async def fake_validate(self, **kwargs):  # noqa: ANN001, ANN003
        validated.append(kwargs)
        return SemanticValidationResult(
            is_valid=True,
            issues=[],
            confidence=1.0,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.0,
        )

    monkeypatch.setattr(PlanSemanticValidator, "validate", fake_validate)
    updates = await semantic_validator_node(
        {
            STATE_KEY_PLAN_APPROVED: None,
            STATE_KEY_EXECUTION_PLAN: _plan(),
            STATE_KEY_PLANNER_ITERATION: 0,
            "english_query": "what is on my agenda tomorrow",
            "user_language": "fr",
        }
    )
    assert len(validated) == 1
    assert updates[STATE_KEY_SEMANTIC_VALIDATION].is_valid is True


async def test_an_explicit_approval_skips_the_re_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The person confirmed through the clarification node: validating again
    # would re-detect the same issue and loop (the 2025-12-07 fix stands).
    async def fake_validate(self, **kwargs):  # noqa: ANN001, ANN003
        raise AssertionError("must not validate an approved plan again")

    monkeypatch.setattr(PlanSemanticValidator, "validate", fake_validate)
    updates = await semantic_validator_node(
        {
            STATE_KEY_PLAN_APPROVED: True,
            STATE_KEY_EXECUTION_PLAN: _plan(),
            STATE_KEY_PLANNER_ITERATION: 0,
            "english_query": "delete the event",
            "user_language": "fr",
        }
    )
    assert updates[STATE_KEY_SEMANTIC_VALIDATION].is_valid is True
    assert updates[STATE_KEY_SEMANTIC_VALIDATION].requires_clarification is False
