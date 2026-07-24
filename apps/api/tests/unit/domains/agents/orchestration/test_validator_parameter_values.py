"""Unit tests for the parameter type/constraint gate of ``PlanValidator``.

``_validate_parameter_value`` is the ``$0``-cost check that a step's arguments
match the tool's declared schema BEFORE the plan runs; ``_validate_constraint``
then enforces the declared bounds. When a value slips through here it reaches
the tool itself, where a type mismatch turns into a raw ``TypeError`` instead of
a clean, actionable validation error the planner could retry on.

The type gate is a lookup table. A declared type ABSENT from that table is not
"unknown, be careful" — it is skipped entirely, and the constraint checks that
follow are themselves type-guarded, so such a parameter ends up with **no
validation at all**.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.validator import (
    PlanValidator,
    ValidationResult,
)
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ParameterConstraint, ParameterSchema
from src.domains.agents.tools.common import ToolErrorCode

pytestmark = pytest.mark.unit


@pytest.fixture
def validator() -> PlanValidator:
    return PlanValidator(AgentRegistry())


def _schema(
    param_type: str,
    *,
    name: str = "p",
    constraints: list[ParameterConstraint] | None = None,
) -> ParameterSchema:
    return ParameterSchema(
        name=name,
        type=param_type,
        required=False,
        description="test parameter",
        constraints=constraints or [],
    )


def _check(validator: PlanValidator, value: Any, schema: ParameterSchema) -> ValidationResult:
    result = ValidationResult(is_valid=True, errors=[], warnings=[])
    validator._validate_parameter_value(schema.name, value, schema, 0, "some_tool", result)
    return result


# ============================================================================
# Type gate
# ============================================================================


class TestParameterTypeGate:
    @pytest.mark.parametrize(
        ("param_type", "value"),
        [
            ("string", "hello"),
            ("integer", 5),
            ("boolean", True),
            ("array", [1, 2]),
            ("object", {"a": 1}),
            ("number", 4.5),
            ("number", 4),  # an int is a valid number
        ],
    )
    def test_matching_type_passes(
        self, validator: PlanValidator, param_type: str, value: Any
    ) -> None:
        assert _check(validator, value, _schema(param_type)).errors == []

    @pytest.mark.parametrize(
        ("param_type", "value"),
        [
            ("string", 5),
            ("integer", "5"),
            ("array", "not a list"),
            ("object", ["not", "a", "dict"]),
            ("number", "4.5"),  # the LLM sent a string where a float is declared
            ("number", [4.5]),
        ],
    )
    def test_wrong_type_is_rejected(
        self, validator: PlanValidator, param_type: str, value: Any
    ) -> None:
        """Regression for the ``number`` rows: that type was missing from the
        lookup table, so a string rating passed this gate untouched, skipped the
        type-guarded constraint checks too, and only blew up inside
        ``get_places_tool`` as ``'<=' not supported between float and str``.
        """
        result = _check(validator, value, _schema(param_type))
        assert len(result.errors) == 1
        assert result.errors[0].code == ToolErrorCode.INVALID_PARAM_VALUE
        assert "wrong type" in result.errors[0].message

    def test_unknown_declared_type_is_skipped(self, validator: PlanValidator) -> None:
        """Semantic aliases (``datetime``, ``coordinate`` …) are not in the table
        and are deliberately not type-checked here — pinned so the behaviour is
        a documented choice rather than an accident."""
        assert _check(validator, "anything", _schema("datetime")).errors == []


class TestReferencesAndTemplatesAreDeferred:
    @pytest.mark.parametrize(
        "value",
        ["$steps.step_1.contacts[0].value", "$context.last_place.address"],
    )
    def test_references_skip_validation(self, validator: PlanValidator, value: str) -> None:
        """References are resolved at runtime — their static type is unknowable,
        so the reference validator owns them instead."""
        assert _check(validator, value, _schema("integer")).errors == []

    @pytest.mark.parametrize("value", ["{{ item.id }}", "{% for x in y %}{{ x }}{% endfor %}"])
    def test_jinja_templates_skip_validation(self, validator: PlanValidator, value: str) -> None:
        assert _check(validator, value, _schema("array")).errors == []


# ============================================================================
# Constraints (only reached once the type matches)
# ============================================================================


class TestConstraints:
    def test_min_length_violation(self, validator: PlanValidator) -> None:
        schema = _schema("string", constraints=[ParameterConstraint(kind="min_length", value=3)])
        result = _check(validator, "ab", schema)
        assert result.errors[0].code == ToolErrorCode.CONSTRAINT_VIOLATION

    def test_min_length_satisfied(self, validator: PlanValidator) -> None:
        schema = _schema("string", constraints=[ParameterConstraint(kind="min_length", value=3)])
        assert _check(validator, "abc", schema).errors == []

    def test_max_length_violation(self, validator: PlanValidator) -> None:
        schema = _schema("string", constraints=[ParameterConstraint(kind="max_length", value=3)])
        assert len(_check(validator, "abcd", schema).errors) == 1

    def test_minimum_violation(self, validator: PlanValidator) -> None:
        schema = _schema("integer", constraints=[ParameterConstraint(kind="minimum", value=1)])
        assert len(_check(validator, 0, schema).errors) == 1

    def test_maximum_violation(self, validator: PlanValidator) -> None:
        schema = _schema("integer", constraints=[ParameterConstraint(kind="maximum", value=10)])
        assert len(_check(validator, 11, schema).errors) == 1

    def test_bounds_are_inclusive(self, validator: PlanValidator) -> None:
        schema = _schema(
            "integer",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=10),
            ],
        )
        assert _check(validator, 1, schema).errors == []
        assert _check(validator, 10, schema).errors == []

    def test_number_bounds_are_enforced(self, validator: PlanValidator) -> None:
        """The whole point of typing ``min_rating`` as a number: its declared
        range must actually be checked."""
        schema = _schema(
            "number",
            constraints=[
                ParameterConstraint(kind="minimum", value=1.0),
                ParameterConstraint(kind="maximum", value=5.0),
            ],
        )
        assert _check(validator, 4.5, schema).errors == []
        assert len(_check(validator, 5.5, schema).errors) == 1

    def test_pattern_violation(self, validator: PlanValidator) -> None:
        schema = _schema(
            "string", constraints=[ParameterConstraint(kind="pattern", value=r"^people/c\d+$")]
        )
        assert len(_check(validator, "not-a-resource-name", schema).errors) == 1

    def test_pattern_satisfied(self, validator: PlanValidator) -> None:
        schema = _schema(
            "string", constraints=[ParameterConstraint(kind="pattern", value=r"^people/c\d+$")]
        )
        assert _check(validator, "people/c123", schema).errors == []

    def test_enum_violation(self, validator: PlanValidator) -> None:
        schema = _schema(
            "string", constraints=[ParameterConstraint(kind="enum", value=["ASC", "DESC"])]
        )
        assert len(_check(validator, "SIDEWAYS", schema).errors) == 1

    def test_enum_satisfied(self, validator: PlanValidator) -> None:
        schema = _schema(
            "string", constraints=[ParameterConstraint(kind="enum", value=["ASC", "DESC"])]
        )
        assert _check(validator, "ASC", schema).errors == []

    def test_wrong_type_short_circuits_before_constraints(self, validator: PlanValidator) -> None:
        """One clear error, not a cascade of constraint failures on a value whose
        type is already wrong."""
        schema = _schema("integer", constraints=[ParameterConstraint(kind="minimum", value=1)])
        result = _check(validator, "not an int", schema)
        assert len(result.errors) == 1
        assert result.errors[0].code == ToolErrorCode.INVALID_PARAM_VALUE

    def test_malformed_constraint_never_raises(self, validator: PlanValidator) -> None:
        """A bad pattern must degrade to a logged warning, not crash plan
        validation for every user."""
        schema = _schema("string", constraints=[ParameterConstraint(kind="pattern", value="[")])
        _check(validator, "abc", schema)  # must not raise
