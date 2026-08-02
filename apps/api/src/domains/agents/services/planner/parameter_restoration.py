"""Keep a replan from losing what the previous pass already had right.

Both halves of one rule live here, because they answer the same question — "what
does the previous plan still speak for?" — and were computing it twice:

* :func:`preserved_parameters_for_prompt` builds the "PRESERVED PARAMETERS"
  section that ASKS the planner to keep those values;
* :func:`restore_and_report` puts a value back when the planner ignored the ask
  and produced a fabrication instead.

The second exists because the first is a request, not a guarantee: production
2026-08-02 showed a user-supplied address replaced by ``jerome@example.com`` on
the very next turn. Sibling of :mod:`parameter_bounds`, same doctrine (ADR-184):
what is mechanically repairable is repaired BEFORE validation, so the planner is
not sent looping over a defect it already had right one pass earlier.

The repair itself lives with its detector in ``plan_predicates``; this module is
the seam that reports it, because a silent repair is a repair nobody can
measure. A steady rate on the counter means the replan prompt is losing
parameters while fixing an unrelated issue, which this repair only hides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.constants import (
    PLANNER_FIELD_TO_PARAM_NAMES,
    PLANNER_PRESERVABLE_PARAM_NAMES,
)
from src.domains.agents.orchestration.plan_predicates import restore_fabricated_parameters
from src.domains.agents.utils.shape_agnostic import read_field
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    planner_fabricated_parameters_restored,
)

if TYPE_CHECKING:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

logger = get_logger(__name__)


def _parameters_the_clarification_supersedes(clarification_field: str | None) -> frozenset[str]:
    """Names the previous plan no longer speaks for, after a clarification.

    A logical field ("body") can be carried by a differently named parameter
    ("content_instruction"), so the field name alone would not cover it —
    ``PLANNER_FIELD_TO_PARAM_NAMES`` is what bridges the two, and the field
    itself is added for the direct-match case it does not list.

    Args:
        clarification_field: The field the user was just asked about, if any.

    Returns:
        The parameter names to leave alone; empty when no clarification is in play.
    """
    if not clarification_field:
        return frozenset()
    return PLANNER_FIELD_TO_PARAM_NAMES.get(clarification_field, frozenset()) | {
        clarification_field
    }


def preserved_parameters_for_prompt(
    existing_plan: Any,
    clarification_field: str,
) -> dict[str, Any]:
    """Parameters a replan after a clarification must carry over unchanged.

    When the user clarifies one field, everything ELSE they already provided
    (possibly in an earlier clarification) has to survive the regeneration —
    without this the planner rebuilds from the query alone and drops it.

    Reads its steps through ``read_field``. A valid resumed plan comes back with
    typed steps, so this is not the common path — but a step that no longer
    passes its own validation degrades to a mapping, and the caller swallows
    ``AttributeError`` into a warning. The preservation would then vanish in
    silence, in the exact case it exists for, on a turn where the user has just
    typed the value being lost. Cheap insurance against an expensive silence.

    Args:
        existing_plan: The plan being replaced, in object or checkpoint-restored
            mapping form.
        clarification_field: The field being clarified, excluded from the result
            along with every parameter name that carries it.

    Returns:
        ``parameter_name -> value`` for the prompt to restate. Values that are
        empty, non-preservable (ids, flags) or unresolved references are left
        out — restating those would teach the planner nothing.
    """
    preserved: dict[str, Any] = {}
    steps = read_field(existing_plan, "steps") or []
    if not steps:
        return preserved

    params_to_skip = _parameters_the_clarification_supersedes(clarification_field)

    for step in steps:
        for param_name, param_value in (read_field(step, "parameters") or {}).items():
            if param_name in params_to_skip:
                continue
            if param_name not in PLANNER_PRESERVABLE_PARAM_NAMES:
                continue
            if param_value is None or param_value == "":
                continue
            if isinstance(param_value, str) and param_value.startswith(("$steps.", "{{")):
                continue
            preserved[param_name] = param_value

    return preserved


def restore_and_report(
    plan: ExecutionPlan,
    existing_plan: Any,
    clarification_field: str | None = None,
) -> list[str]:
    """Repair fabricated parameters in place, and make the repair visible.

    Args:
        plan: The freshly generated plan, repaired in place.
        existing_plan: The plan of the same turn before the replan, or None.
        clarification_field: The field the user was just asked about. Its
            parameters are left untouched: the user's fresh answer outranks
            anything the previous plan carried for them.

    Returns:
        The repaired locations as ``"step_id.parameter"``; empty when nothing
        was repairable, in which case the plan reaches the guard unchanged.
    """
    restored = restore_fabricated_parameters(
        plan,
        existing_plan,
        _parameters_the_clarification_supersedes(clarification_field),
    )
    if not restored:
        return []

    # WARNING, like `planner_parameter_bound_corrected` next door: a repair that
    # had to happen means the replan lost something it already had right, and
    # that deserves to be visible without turning on debug. Only field NAMES are
    # logged — the values are contact details.
    logger.warning(
        "planner_fabricated_parameters_restored",
        plan_id=plan.plan_id,
        restored=restored,
        msg="Re-used the previous plan's values where this one invented placeholders",
    )
    planner_fabricated_parameters_restored.inc(len(restored))
    return restored
