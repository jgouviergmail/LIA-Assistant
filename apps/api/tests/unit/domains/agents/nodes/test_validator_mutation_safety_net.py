"""F-B — invalid MUTATION plans are never executed by the max-iterations bypass.

Prod 2026-07-17: the replanner failed to converge on a create_event plan (wrong
date), auto-replans exhausted, and the router's max-iterations bypass executed
the still-invalid plan — a calendar event on the wrong day. The validator node
now converts that terminal case to a HITL clarification (mutations only);
read-only plans keep the harmless bypass.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.constants import (
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_SEMANTIC_VALIDATION,
)
from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.semantic_validator import (
    SemanticIssue,
    SemanticIssueType,
    SemanticValidationResult,
    plan_contains_mutation,
)

pytestmark = pytest.mark.unit


def _plan(tool_name: str) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p",
        user_id="u",
        session_id="s",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="event_agent",
                tool_name=tool_name,
                parameters={"summary": "Rendez-vous"},
            )
        ],
    )


# --------------------------------------------------------------------------- #
# plan_contains_mutation (pure)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "tool,expected",
    [
        ("create_event_tool", True),
        ("delete_task_tool", True),
        ("send_email_tool", True),
        ("get_events_tool", False),
        ("get_contacts_tool", False),
    ],
)
def test_plan_contains_mutation_by_tool(tool: str, expected: bool) -> None:
    assert plan_contains_mutation(_plan(tool)) is expected


def test_plan_contains_mutation_tolerates_none_and_dict() -> None:
    assert plan_contains_mutation(None) is False
    assert plan_contains_mutation({"steps": [{"tool_name": "create_event_tool"}]}) is True
    assert plan_contains_mutation({"steps": [{"tool_name": "get_events_tool"}]}) is False


# --------------------------------------------------------------------------- #
# validator node — the F-B decision
# --------------------------------------------------------------------------- #


def _invalid_result() -> SemanticValidationResult:
    return SemanticValidationResult(
        is_valid=False,
        issues=[
            SemanticIssue(
                issue_type=SemanticIssueType.WRONG_PARAMETERS,
                description="La date de début est incorrecte (samedi 18 à 9h30 demandé).",
            )
        ],
        confidence=0.9,
        requires_clarification=False,
        clarification_questions=[],
        validation_duration_seconds=0.1,
    )


def _state(plan: ExecutionPlan, iteration: int) -> dict:
    return {
        STATE_KEY_EXECUTION_PLAN: plan,
        STATE_KEY_PLANNER_ITERATION: iteration,
        "english_query": "create the appointment Saturday July 18 at 9:30 with Jérôme",
        "user_language": "fr",
    }


async def test_exhausted_mutation_becomes_clarification(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.domains.agents.orchestration.semantic_validator import PlanSemanticValidator

    async def fake_validate(self, **kwargs):  # noqa: ANN001, ANN003
        return _invalid_result()

    monkeypatch.setattr(PlanSemanticValidator, "validate", fake_validate)

    exhausting = settings.planner_max_replans  # current + 1 > max → clarify
    updates = await semantic_validator_node(_state(_plan("create_event_tool"), exhausting))

    result = updates[STATE_KEY_SEMANTIC_VALIDATION]
    assert result.requires_clarification is True
    # The specific mismatch is surfaced (localized issue description), not a generic fallback.
    assert result.clarification_questions
    assert "date" in result.clarification_questions[0].lower()
    # planner_iteration NOT bumped (keeps the router on the clarification branch).
    assert STATE_KEY_PLANNER_ITERATION not in updates


async def test_exhausted_readonly_keeps_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.domains.agents.orchestration.semantic_validator import PlanSemanticValidator

    async def fake_validate(self, **kwargs):  # noqa: ANN001, ANN003
        return _invalid_result()

    monkeypatch.setattr(PlanSemanticValidator, "validate", fake_validate)

    exhausting = settings.planner_max_replans
    updates = await semantic_validator_node(_state(_plan("get_events_tool"), exhausting))

    result = updates[STATE_KEY_SEMANTIC_VALIDATION]
    assert result.requires_clarification is False  # read-only → keep bypass
    assert updates[STATE_KEY_PLANNER_ITERATION] == exhausting + 1  # incremented → bypass


async def test_below_exhaustion_mutation_auto_replans(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.domains.agents.orchestration.semantic_validator import PlanSemanticValidator

    async def fake_validate(self, **kwargs):  # noqa: ANN001, ANN003
        return _invalid_result()

    monkeypatch.setattr(PlanSemanticValidator, "validate", fake_validate)

    below = settings.planner_max_replans - 1  # current + 1 == max → still auto-replan
    updates = await semantic_validator_node(_state(_plan("create_event_tool"), below))

    result = updates[STATE_KEY_SEMANTIC_VALIDATION]
    assert result.requires_clarification is False
    assert updates[STATE_KEY_PLANNER_ITERATION] == below + 1  # normal auto-replan increment
