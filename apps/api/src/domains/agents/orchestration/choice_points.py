"""Where a plan acts on the FIRST item a lookup finds (ADR-367 amendment).

The incident of 2026-10-29 in its other shape: nothing was shown, so « reply to
Marc's email » is planned as a lookup and an act on its first result
(``$steps.lookup.emails[0].id``). When the lookup finds several, « the first »
is a guess the person never made. This module finds those places in a plan,
without running anything: the orchestrator runs the lookup first and, when it
found several, the person is asked which one before any act runs.

A lookup qualifies only when the plan reads nothing of it but its first item:
a list the plan iterates over (``for_each``), passes on whole, or reads at
another position is the person's subject, not a means — narrowing it to the
chosen item would change what those steps do.

Pure functions; whether a tool acts is the caller's (the manifest's declared
``mutation_policy``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from src.domains.agents.orchestration.dependency_graph import DependencyGraph
from src.domains.agents.orchestration.for_each_utils import extract_step_references
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType

__all__ = ["ChoicePoint", "choice_points"]

#: ``$steps.<step>.<list path>[0]`` — or the template form ``steps.<step>.<path>[0]``.
_FIRST_ITEM: Final = re.compile(r"(?<![\w.$])\$?steps\.(\w+)\.([A-Za-z_][\w.]*?)\[0\]")
#: Any read of a step's result, the first item's included.
_ANY_READ: Final = re.compile(r"(?<![\w.$])\$?steps\.(\w+)\b(?P<rest>[\w.\[\]]*)")


@dataclass(frozen=True, slots=True)
class ChoicePoint:
    """An act that would run on the first item of a lookup's list."""

    act_step_id: str
    source_step_id: str
    #: The list's path in the lookup's result (``emails``).
    list_path: str


def _text(step: ExecutionStep) -> str:
    """Everything of a step that can read another step's result."""
    return json.dumps(step.parameters or {}) + (step.condition or "") + (step.for_each or "")


def _reads_beyond_the_first(plan: ExecutionPlan, source: str, list_path: str) -> bool:
    """Whether any step reads the source otherwise than through its first item."""
    first = f"{list_path}[0]"
    for step in plan.steps:
        if step.for_each and source in extract_step_references(step.for_each):
            return True
        for match in _ANY_READ.finditer(_text(step)):
            if match.group(1) == source and not match.group("rest").startswith(f".{first}"):
                return True
    return False


def choice_points(plan: ExecutionPlan, acts: Callable[[str], bool]) -> list[ChoicePoint]:
    """The acts of a plan that would run on the first item a lookup finds.

    Args:
        plan: The plan, as the planner wrote it.
        acts: Whether a tool, by name, acts (its declared mutation policy).

    Returns:
        One point per (act, lookup list), in plan order. A lookup qualifies when
        it is a read step of this plan, reaches no act through its own
        dependencies, and is read by the plan through its first item alone.
    """
    acting = [
        step
        for step in plan.steps
        if step.step_type == StepType.TOOL and not step.for_each and acts(step.tool_name or "")
    ]
    return [
        ChoicePoint(step.step_id, source, list_path)
        for step in acting
        for source, list_path in dict.fromkeys(_FIRST_ITEM.findall(_text(step)))
        if _is_a_lookup(plan, source, list_path, acts)
    ]


def _is_a_lookup(
    plan: ExecutionPlan, source: str, list_path: str, acts: Callable[[str], bool]
) -> bool:
    """Whether a step an act reads the first item of can run first, and be narrowed.

    It is a plain tool step of the plan, nothing upstream of it acts, and the
    plan reads nothing of its list but the first item.
    """
    steps = {step.step_id: step for step in plan.steps}
    lookup = steps.get(source)
    if lookup is None or lookup.step_type != StepType.TOOL or lookup.for_each:
        return False
    upstream = {source, *DependencyGraph(plan).get_all_dependencies(source)}
    if any(acts(steps[step_id].tool_name or "") for step_id in upstream if step_id in steps):
        return False
    return not _reads_beyond_the_first(plan, source, list_path)
