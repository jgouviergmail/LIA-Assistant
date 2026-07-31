"""A plan may not carry a value the catalogue already declares out of bounds.

Production 2026-07-31 (requests 2f6c6366, 52e54297, 83c98053): the planner
emitted ``max_results=20`` on ``get_emails_tool`` whose manifest caps it at 10.
The validator flagged CONSTRAINT_VIOLATION, the plan ran anyway, the tool
capped the value itself — and the only lasting effect was a plan marked
invalid, which the response layer then reported to the user as a failure.

The planner was obeying its own prompt while the bound stayed invisible to it.
Clamping here makes the plan say what the tool will do anyway, so the verdict
stops carrying a defect that no longer exists.

The mirror of ``validator._validate_constraint``: whatever that method would
reject on a ``minimum``/``maximum`` constraint, this one repairs first.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.registry.catalogue import (
    CostProfile,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
    ToolManifestNotFound,
)
from src.domains.agents.services.planner.parameter_bounds import (
    clamp_parameters_to_manifest,
)


def _manifest(*parameters: ParameterSchema) -> ToolManifest:
    return ToolManifest(
        name="get_emails_tool",
        agent="emails_agent",
        description="Read emails.",
        parameters=list(parameters),
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(),
    )


def _bounded(name: str = "max_results", *, minimum: int | None = None, maximum: int | None = None):
    constraints = []
    if minimum is not None:
        constraints.append(ParameterConstraint(kind="minimum", value=minimum))
    if maximum is not None:
        constraints.append(ParameterConstraint(kind="maximum", value=maximum))
    return ParameterSchema(
        name=name, type="integer", required=False, description="", constraints=constraints
    )


class _Registry:
    """Minimal stand-in for AgentRegistry.get_tool_manifest."""

    def __init__(self, manifest: ToolManifest | None) -> None:
        self._manifest = manifest

    def get_tool_manifest(self, name: str) -> ToolManifest:
        if self._manifest is None or self._manifest.name != name:
            raise ToolManifestNotFound(name)
        return self._manifest


def _clamp(parameters: dict[str, Any], manifest: ToolManifest | None) -> dict[str, Any]:
    return clamp_parameters_to_manifest("get_emails_tool", parameters, _Registry(manifest))


# =========================================================================
# The production defect
# =========================================================================


def test_value_above_maximum_is_lowered_to_the_bound():
    """The verbatim case of request 83c98053."""
    assert _clamp({"max_results": 20}, _manifest(_bounded(maximum=10))) == {"max_results": 10}


def test_value_below_minimum_is_raised_to_the_bound():
    assert _clamp({"max_results": 0}, _manifest(_bounded(minimum=1))) == {"max_results": 1}


def test_value_inside_the_bounds_is_untouched():
    manifest = _manifest(_bounded(minimum=1, maximum=10))

    assert _clamp({"max_results": 5}, manifest) == {"max_results": 5}


def test_value_exactly_on_the_bound_is_untouched():
    """`> maximum` is the violation, not `== maximum` — mirror the validator."""
    assert _clamp({"max_results": 10}, _manifest(_bounded(maximum=10))) == {"max_results": 10}


def test_the_input_mapping_is_never_mutated():
    """The caller keeps the raw LLM output; a copy is returned."""
    original = {"max_results": 20}

    clamped = _clamp(original, _manifest(_bounded(maximum=10)))

    assert original == {"max_results": 20}
    assert clamped is not original


# =========================================================================
# Values the clamp must not touch
# =========================================================================


def test_step_references_are_left_alone():
    """`$steps.x.y` resolves at runtime — its type is unknown here."""
    manifest = _manifest(_bounded(maximum=10))

    assert _clamp({"max_results": "$steps.step_1.count"}, manifest) == {
        "max_results": "$steps.step_1.count"
    }


def test_jinja_templates_are_left_alone():
    manifest = _manifest(_bounded(maximum=10))
    template = "{{ items | length }}"

    assert _clamp({"max_results": template}, manifest) == {"max_results": template}


def test_booleans_are_not_treated_as_numbers():
    """`isinstance(True, int)` is True in Python — the guard must be explicit."""
    manifest = _manifest(
        ParameterSchema(
            name="use_cache",
            type="boolean",
            required=False,
            description="",
            constraints=[ParameterConstraint(kind="maximum", value=0)],
        )
    )

    assert _clamp({"use_cache": True}, manifest) == {"use_cache": True}


def test_non_numeric_values_are_left_to_the_validator():
    """A wrong type is a real defect: repairing it would hide it."""
    manifest = _manifest(_bounded(maximum=10))

    assert _clamp({"max_results": "twenty"}, manifest) == {"max_results": "twenty"}


def test_none_is_left_alone():
    assert _clamp({"max_results": None}, _manifest(_bounded(maximum=10))) == {"max_results": None}


def test_parameter_absent_from_the_manifest_is_left_alone():
    manifest = _manifest(_bounded("other_param", maximum=10))

    assert _clamp({"max_results": 999}, manifest) == {"max_results": 999}


def test_constraints_other_than_bounds_are_ignored():
    """Only `minimum`/`maximum` are repairable; a pattern or enum is not."""
    manifest = _manifest(
        ParameterSchema(
            name="query",
            type="string",
            required=False,
            description="",
            constraints=[ParameterConstraint(kind="pattern", value="^people/")],
        )
    )

    assert _clamp({"query": "Jane Smith"}, manifest) == {"query": "Jane Smith"}


# =========================================================================
# Degradation — never cost a turn
# =========================================================================


def test_unknown_tool_returns_the_parameters_unchanged():
    """MCP tools carry no catalogue manifest."""
    assert _clamp({"max_results": 999}, None) == {"max_results": 999}


def test_empty_parameters_stay_empty():
    assert _clamp({}, _manifest(_bounded(maximum=10))) == {}


def test_a_registry_failure_never_raises():
    """A planner crash costs the whole turn — degrade to the raw plan."""

    class _Exploding:
        def get_tool_manifest(self, name: str) -> ToolManifest:
            raise RuntimeError("registry is down")

    assert clamp_parameters_to_manifest("get_emails_tool", {"max_results": 20}, _Exploding()) == {
        "max_results": 20
    }


def test_incoherent_bounds_are_skipped_rather_than_guessed():
    """minimum > maximum is a seeding defect: clamping either way invents intent."""
    manifest = _manifest(_bounded(minimum=10, maximum=5))

    assert _clamp({"max_results": 20}, manifest) == {"max_results": 20}


# =========================================================================
# Float and multi-parameter handling
# =========================================================================


def test_float_bounds_are_clamped_without_changing_the_declared_type():
    manifest = _manifest(
        ParameterSchema(
            name="min_rating",
            type="number",
            required=False,
            description="",
            constraints=[ParameterConstraint(kind="maximum", value=5)],
        )
    )

    assert _clamp({"min_rating": 7.5}, manifest) == {"min_rating": 5}


def test_every_bounded_parameter_of_the_step_is_repaired():
    manifest = _manifest(_bounded("max_results", maximum=10), _bounded("offset", minimum=0))

    assert _clamp({"max_results": 50, "offset": -3, "query": "x"}, manifest) == {
        "max_results": 10,
        "offset": 0,
        "query": "x",
    }


# =========================================================================
# The contract with the validator: what is clamped is no longer an error
# =========================================================================


@pytest.mark.parametrize("raw_value", [11, 20, 50, 10_000])
def test_a_clamped_plan_no_longer_violates_the_manifest(raw_value: int):
    """The whole point: after clamping, the validator has nothing left to say."""
    from src.domains.agents.orchestration.validator import PlanValidator, ValidationResult

    manifest = _manifest(_bounded(maximum=10))
    clamped = _clamp({"max_results": raw_value}, manifest)

    result = ValidationResult(is_valid=True)
    validator = PlanValidator(_Registry(manifest))
    validator._validate_parameters(clamped, manifest, 0, result)

    assert result.is_valid, [issue.message for issue in result.errors]


# =========================================================================
# clamp_to_parameter_schema — the entry point the validator uses
# =========================================================================


def test_an_undeclared_schema_leaves_the_value_alone():
    """The validator resolves the schema by name; a miss must not raise."""
    from src.domains.agents.services.planner.parameter_bounds import clamp_to_parameter_schema

    assert clamp_to_parameter_schema(None, 25) == 25


def test_an_unbounded_schema_leaves_the_value_alone():
    from src.domains.agents.services.planner.parameter_bounds import clamp_to_parameter_schema

    schema = ParameterSchema(name="max_results", type="integer", required=False, description="")

    assert clamp_to_parameter_schema(schema, 25) == 25


def test_a_bounded_schema_caps_the_value():
    from src.domains.agents.services.planner.parameter_bounds import clamp_to_parameter_schema

    assert clamp_to_parameter_schema(_bounded(maximum=10), 25) == 10
