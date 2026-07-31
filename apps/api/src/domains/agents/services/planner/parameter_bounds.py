"""Repairing the plan values the catalogue already declares out of bounds.

The planner writes parameter values from the prompt and the catalogue entry it
was given. When it writes one outside a manifest bound, three layers each did
something different and none of them agreed:

- the validator recorded ``CONSTRAINT_VIOLATION`` and marked the plan invalid;
- the router ignored that verdict and executed the plan anyway;
- the tool silently capped the value and returned a correct result.

The measurable outcome was a plan flagged invalid for a defect that no longer
existed by the time anyone could observe it — and, since v1.27.3, a response
that told the user their request had been blocked while its data sat in the
registry (production 2026-07-31, requests 2f6c6366 / 52e54297 / 83c98053:
``max_results=20`` against a manifest capped at 10).

Clamping here makes the plan state what the tool will do regardless, so the
verdict only ever carries defects that are still real. It is the deliberate
counterpart of ``validator._validate_constraint``: every ``minimum`` /
``maximum`` that method would reject, this one repairs first. Constraints that
cannot be repaired without inventing intent (``pattern``, ``enum``, type
mismatches) are left untouched — the validator must still see them.

Same doctrine as the ``for_each_max`` auto-correction already applied in
``SmartPlannerService._build_plan``: correct what is mechanically correctable,
log it, and never fail a turn over it.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.domains.agents.registry.catalogue import ParameterSchema, ToolManifest
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    planner_parameter_bounds_corrections,
)

logger = get_logger(__name__)

# The two constraint kinds that carry a repairable numeric bound. `pattern`,
# `enum`, `min_length` and `max_length` are excluded on purpose: truncating a
# string or picking an enum member would invent an intent the user never
# expressed, and the validator has to keep reporting them.
_MINIMUM: str = "minimum"
_MAXIMUM: str = "maximum"


class _ManifestSource(Protocol):
    """The one registry capability this module needs.

    Declared structurally so the planner can inject its own registry and the
    tests a two-line stub, without either importing ``AgentRegistry``.
    """

    def get_tool_manifest(self, name: str) -> ToolManifest: ...


def _numeric_bounds(parameter: ParameterSchema) -> tuple[float | None, float | None]:
    """Extract the repairable numeric bounds declared on a parameter.

    Args:
        parameter: Catalogue schema of a single tool parameter.

    Returns:
        ``(minimum, maximum)``, each None when not declared or not numeric.
    """
    minimum: float | None = None
    maximum: float | None = None
    for constraint in parameter.constraints or []:
        value = constraint.value
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        if constraint.kind == _MINIMUM:
            minimum = value
        elif constraint.kind == _MAXIMUM:
            maximum = value
    return minimum, maximum


def _clamp_value(value: Any, minimum: float | None, maximum: float | None) -> Any:
    """Bring one value inside its bounds, or return it untouched.

    Args:
        value: Raw value written by the planner.
        minimum: Lower bound, or None.
        maximum: Upper bound, or None.

    Returns:
        The clamped value, or ``value`` itself when it must not be repaired:
        booleans (``isinstance(True, int)`` is True in Python), non-numerics
        such as ``$steps`` references and Jinja templates, and incoherent
        bounds (``minimum > maximum`` is a seeding defect — clamping either way
        would invent an intent).
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return value
    if minimum is not None and maximum is not None and minimum > maximum:
        return value
    if maximum is not None and value > maximum:
        return maximum
    if minimum is not None and value < minimum:
        return minimum
    return value


def clamp_to_parameter_schema(schema: ParameterSchema | None, value: Any) -> Any:
    """Bring one value inside the bounds declared by its catalogue schema.

    Exposed for the callers that already hold the schema and write a value
    themselves — the semantic-leak autocorrect in ``PlanValidator`` being the
    one that would otherwise author the very violation it reports.

    Args:
        schema: Catalogue schema of the parameter, or None when undeclared.
        value: Value about to be written into the plan.

    Returns:
        The clamped value, or ``value`` untouched when there is no schema, no
        numeric bound, or nothing to repair.
    """
    if schema is None:
        return value
    minimum, maximum = _numeric_bounds(schema)
    if minimum is None and maximum is None:
        return value
    return _clamp_value(value, minimum, maximum)


def clamp_parameters_to_manifest(
    tool_name: str,
    parameters: dict[str, Any],
    registry: _ManifestSource,
) -> dict[str, Any]:
    """Return the step parameters brought inside their manifest bounds.

    Args:
        tool_name: Normalized tool name of the step being built.
        parameters: Raw parameters emitted by the planner LLM.
        registry: Manifest source (the agent registry, or any object exposing
            ``get_tool_manifest``).

    Returns:
        A new mapping — the caller keeps the raw LLM output untouched. Values
        are returned unchanged whenever the tool has no catalogue manifest
        (MCP tools), the parameter is undeclared, or the value is not a
        repairable number.
    """
    clamped = dict(parameters)
    if not clamped:
        return clamped

    try:
        manifest = registry.get_tool_manifest(tool_name)
        schemas: dict[str, ParameterSchema] = {p.name: p for p in manifest.parameters}
    except Exception as exc:
        # An unknown tool is the nominal MCP case, and no registry failure is
        # worth losing a turn over: the plan simply goes to the validator as
        # the model wrote it.
        logger.debug(
            "planner_parameter_bounds_skipped",
            tool_name=tool_name,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return clamped

    for name, value in parameters.items():
        schema = schemas.get(name)
        if schema is None:
            continue
        minimum, maximum = _numeric_bounds(schema)
        if minimum is None and maximum is None:
            continue
        corrected = _clamp_value(value, minimum, maximum)
        if corrected == value and type(corrected) is type(value):
            continue
        clamped[name] = corrected
        bound = _MAXIMUM if maximum is not None and corrected == maximum else _MINIMUM
        logger.warning(
            "planner_parameter_bound_corrected",
            tool_name=tool_name,
            parameter=name,
            requested_value=value,
            corrected_value=corrected,
            bound=bound,
            msg=(
                f"{tool_name}.{name}={value} is outside the catalogue bound "
                f"(min={minimum}, max={maximum}); clamped to {corrected}"
            ),
        )
        planner_parameter_bounds_corrections.labels(bound=bound).inc()

    return clamped
