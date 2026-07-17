"""Validator prompt contract — the trailing instruction must not contradict
the structured-output tool.

The human message used to end with "Respond in {user_language}." — a free-text
instruction in last position that frontally contradicted the system prompt's
"never answer in free text". On deepseek-v4-flash (thinking off) this froze the
model into an EMPTY answer (no tool call, no text): 3/3 crashes reproduced,
3/3 tool calls once the line was replaced (A/B, 2026-07-17). The language
constraint now targets the TOOL PAYLOAD's free-text fields only.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.semantic_validator import (
    PlanSemanticValidator,
    SemanticValidationResult,
)
from src.infrastructure.llm.structured_output import StructuredOutputError

pytestmark = pytest.mark.unit


def _plan() -> ExecutionPlan:
    # Parameters are complete on purpose: validate() runs a deterministic
    # required-fields check BEFORE the LLM and an incomplete create_event plan
    # short-circuits into a clarification (never reaching _validate_with_llm).
    return ExecutionPlan(
        plan_id="p",
        user_id="u",
        session_id="s",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="event_agent",
                tool_name="create_event_tool",
                parameters={
                    "summary": "Rendez-vous",
                    "start_datetime": "2026-07-17T17:03:00",
                    "end_datetime": "2026-07-17T18:03:00",
                    "timezone": "Europe/Paris",
                },
            )
        ],
    )


def test_human_message_language_constraint_targets_tool_payload_only() -> None:
    messages = PlanSemanticValidator()._build_validation_prompt(
        _plan(), "create the appointment tomorrow at 9am", "fr"
    )
    human = str(messages[1].content)
    # The contradictory free-text instruction is gone…
    assert "Respond in fr" not in human
    # …replaced by the A/B-proven tool-only mandate + payload-language rule.
    assert "ONLY by calling the structured validation tool" in human
    assert "never as a text answer" in human
    assert "(issues, questions) in fr" in human


def test_system_prompt_keeps_tool_only_mandate() -> None:
    messages = PlanSemanticValidator()._build_validation_prompt(_plan(), "req", "en")
    system = str(messages[0].content)
    assert "never answer in free text" in system


def _ok_result() -> SemanticValidationResult:
    return SemanticValidationResult(
        is_valid=False,
        issues=[],
        confidence=0.9,
        requires_clarification=False,
        clarification_questions=[],
        validation_duration_seconds=0.1,
    )


async def test_structured_output_error_is_retried_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First empty-answer failure retries; the second attempt's verdict is used."""
    validator = PlanSemanticValidator()
    calls: list[int] = []

    async def flaky(*args: object, **kwargs: object) -> SemanticValidationResult:
        calls.append(1)
        if len(calls) == 1:
            raise StructuredOutputError("no tool call", provider="deepseek", schema_name="S")
        return _ok_result()

    monkeypatch.setattr(validator, "_validate_with_llm", flaky)
    result = await validator.validate(_plan(), "create the appointment", user_language="fr")
    assert len(calls) == 2
    assert result.used_fallback is False
    assert result.is_valid is False  # the real verdict, not the fail-open pass


async def test_double_structured_output_error_falls_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = PlanSemanticValidator()

    async def always_failing(*args: object, **kwargs: object) -> SemanticValidationResult:
        raise StructuredOutputError("no tool call", provider="deepseek", schema_name="S")

    monkeypatch.setattr(validator, "_validate_with_llm", always_failing)
    result = await validator.validate(_plan(), "create the appointment", user_language="fr")
    assert result.used_fallback is True
    assert result.is_valid is True  # documented fail-open
    assert result.fallback_reason == "validation_error:StructuredOutputError"
