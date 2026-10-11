"""Literal prose and nested executable dependencies have different semantics."""

import json

import pytest

from scripts.semantic_simulation.corpus import SCENARIOS
from scripts.semantic_simulation.execution import simulate_plan
from scripts.semantic_simulation.prompts import registry_for_probe
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.orchestration.validator import PlanValidator, ValidationResult
from src.domains.agents.registry.agent_registry import AgentRegistry

pytestmark = pytest.mark.unit


def test_literal_reference_prefix_survives_real_plan_validation_and_resolution() -> None:
    case = next(case for case in SCENARIOS if case.name == "literal_content_preserved")
    result = simulate_plan(
        case,
        json.dumps(
            {"steps": [{"id": "task", "tool_name": case.action, "parameters": case.expected}]}
        ),
        registry_for_probe(),
    )
    assert result["failures"] == []
    assert result["calls"][0]["arguments"] == case.expected


@pytest.mark.parametrize(
    "parameters",
    [
        {"payload": {"emails": ["$steps.absent.contacts[0].email"]}},
        {"notes": "from:$steps.absent.contacts[0].email to:me"},
        {"notes": "$steps.absent"},
    ],
)
def test_missing_real_references_are_rejected_even_in_nested_batches(
    parameters: dict[str, object],
) -> None:
    step = ExecutionStep(
        step_id="consumer",
        step_type=StepType.TOOL,
        tool_name="fictional",
        agent_name="event_agent",
        parameters=parameters,
    )
    result = ValidationResult(is_valid=True)
    PlanValidator(AgentRegistry())._validate_step_references([step], result)
    assert not result.is_valid
    assert any(item.context.get("missing_reference") == "absent" for item in result.errors)
