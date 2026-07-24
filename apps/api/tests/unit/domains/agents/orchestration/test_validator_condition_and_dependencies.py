"""Unit tests for two untested, correctness-critical gates in ``PlanValidator``.

``_validate_condition_safe`` is the **security whitelist** for CONDITIONAL step
conditions: it AST-parses the condition (after masking ``$steps.X.field``
references) and rejects any node outside a small safe set. A regression here
either lets an unsafe expression through the static gate, or wrongly rejects a
legitimate condition (killing a valid plan).

``_validate_dependencies`` is the **DAG gate**: it rejects plans whose steps
reference a non-existent dependency or form a cycle — both of which would
otherwise deadlock or misorder execution.

Both are pure (no DB/LLM), so they are exercised directly. Named-step-ID
contract note: conditions use NAMED step ids (``$steps.step_1``), matching the
runtime ``ReferenceResolver`` (condition_evaluator.py); the numeric ``$steps.0``
form is not part of the DSL and is rejected — pinned below.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.orchestration.validator import (
    PlanValidator,
    ValidationResult,
)
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.tools.common import ToolErrorCode

pytestmark = pytest.mark.unit


@pytest.fixture
def validator() -> PlanValidator:
    return PlanValidator(AgentRegistry())


def _fresh() -> ValidationResult:
    return ValidationResult(is_valid=True, errors=[], warnings=[])


def _check_condition(validator: PlanValidator, condition: str) -> ValidationResult:
    result = _fresh()
    validator._validate_condition_safe(condition, "step_x", 0, result)
    return result


# ============================================================================
# _validate_condition_safe — the AST safety whitelist
# ============================================================================


class TestValidateConditionSafe:
    @pytest.mark.parametrize(
        "condition",
        [
            "len($steps.step_1.contacts) > 1",
            "$steps.step_1.count == 5 and $steps.step_2.count > 0",
            "$steps.step_1.count > 0 or $steps.step_2.count > 0",
            "not ($steps.step_1.done)",
            '$steps.step_1.status != "error"',
            "$steps.step_1.count >= 3",
            '"admin" in $steps.step_1.roles',
            '"admin" not in $steps.step_1.roles',
            "$steps.step_1.contacts[0] == 1",  # subscript + field access
        ],
    )
    def test_safe_conditions_pass(self, validator: PlanValidator, condition: str) -> None:
        result = _check_condition(validator, condition)
        assert result.is_valid, [e.message for e in result.errors]
        assert result.errors == []

    @pytest.mark.parametrize(
        "condition",
        [
            "$steps.step_1.x + 1 > 0",  # BinOp
            "$steps.step_1.x * 2 > 0",  # BinOp
            '$steps.step_1.x in ["a", "b"]',  # List literal
            "$steps.step_1.x in (1, 2)",  # Tuple literal
            "$steps.step_1.value if True else 0",  # IfExp
        ],
    )
    def test_unsafe_nodes_are_forbidden(self, validator: PlanValidator, condition: str) -> None:
        result = _check_condition(validator, condition)
        assert not result.is_valid
        assert result.errors[0].code == ToolErrorCode.FORBIDDEN
        assert "Unsafe node" in result.errors[0].message

    @pytest.mark.parametrize(
        "condition",
        [
            "min($steps.step_1.x, 1) > 0",
            "max($steps.step_1.x, 1) > 0",
            '__import__("os")',
            'open("/etc/passwd")',
        ],
    )
    def test_only_len_function_is_allowed(self, validator: PlanValidator, condition: str) -> None:
        result = _check_condition(validator, condition)
        assert not result.is_valid
        assert result.errors[0].code == ToolErrorCode.FORBIDDEN
        # Either the "only len()" guard (Name func) or the node whitelist fires,
        # but the call must never be accepted.
        assert result.errors[0].code == ToolErrorCode.FORBIDDEN

    def test_len_call_is_accepted(self, validator: PlanValidator) -> None:
        assert _check_condition(validator, "len($steps.step_1.items) == 0").is_valid

    @pytest.mark.parametrize(
        "condition",
        [
            "$steps.step_1.x >",  # dangling operator
            "len($steps.step_1.items",  # unbalanced paren
            "$steps.step_1.x ==== 1",  # bad operator
        ],
    )
    def test_syntax_errors_are_invalid_input(
        self, validator: PlanValidator, condition: str
    ) -> None:
        result = _check_condition(validator, condition)
        assert not result.is_valid
        assert result.errors[0].code == ToolErrorCode.INVALID_INPUT
        assert "Invalid condition syntax" in result.errors[0].message

    def test_numeric_step_reference_is_rejected(self, validator: PlanValidator) -> None:
        """Contract pin: step IDs are NAMED ($steps.step_1). The numeric
        $steps.0 form is not part of the DSL — the runtime ReferenceResolver
        rejects it too — so it is left unmasked and fails to parse. Accepting it
        here would let a plan validate that then crashes at evaluation."""
        result = _check_condition(validator, "len($steps.0.contacts) > 1")
        assert not result.is_valid
        assert result.errors[0].code == ToolErrorCode.INVALID_INPUT

    def test_named_reference_with_underscores_and_digits_is_masked(
        self, validator: PlanValidator
    ) -> None:
        """A realistic named id like ``search_contacts_2`` must be masked so the
        condition parses (regression guard for the masking regex)."""
        assert _check_condition(validator, "$steps.search_contacts_2.count > 0").is_valid


# ============================================================================
# _validate_dependencies — missing deps + cycle detection
# ============================================================================


def _step(step_id: str, depends_on: list[str] | None = None) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="contacts_agent",
        tool_name="search_contacts_tool",
        depends_on=depends_on or [],
    )


class TestValidateDependencies:
    def test_linear_dag_is_valid(self, validator: PlanValidator) -> None:
        steps = [_step("a"), _step("b", ["a"]), _step("c", ["b"])]
        result = _fresh()
        validator._validate_dependencies(steps, result)
        assert result.errors == []

    def test_diamond_dag_is_valid(self, validator: PlanValidator) -> None:
        """a → {b, c} → d is a DAG, not a cycle, even though d is reached twice."""
        steps = [_step("a"), _step("b", ["a"]), _step("c", ["a"]), _step("d", ["b", "c"])]
        result = _fresh()
        validator._validate_dependencies(steps, result)
        assert result.errors == []

    def test_no_dependencies_is_valid(self, validator: PlanValidator) -> None:
        steps = [_step("a"), _step("b"), _step("c")]
        result = _fresh()
        validator._validate_dependencies(steps, result)
        assert result.errors == []

    def test_missing_dependency_is_flagged(self, validator: PlanValidator) -> None:
        steps = [_step("a", ["ghost"])]
        result = _fresh()
        validator._validate_dependencies(steps, result)
        assert len(result.errors) == 1
        assert "non-existent step" in result.errors[0].message
        assert result.errors[0].context["missing_dependency"] == "ghost"

    def test_simple_cycle_is_detected(self, validator: PlanValidator) -> None:
        steps = [_step("a", ["b"]), _step("b", ["a"])]
        result = _fresh()
        validator._validate_dependencies(steps, result)
        assert any("Cyclic dependency" in e.message for e in result.errors)

    def test_self_cycle_is_detected(self, validator: PlanValidator) -> None:
        steps = [_step("a", ["a"])]
        result = _fresh()
        validator._validate_dependencies(steps, result)
        assert any("Cyclic dependency" in e.message for e in result.errors)

    def test_longer_cycle_is_detected(self, validator: PlanValidator) -> None:
        steps = [_step("a", ["c"]), _step("b", ["a"]), _step("c", ["b"])]
        result = _fresh()
        validator._validate_dependencies(steps, result)
        assert any("Cyclic dependency" in e.message for e in result.errors)
