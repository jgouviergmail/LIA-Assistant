"""An item the person designated is the one the plan acts on (ADR-367 amendment).

« Draft a reply to the second email »: the router resolved « the second » on the
list the person SAW, and the planner was handed that item, its id included. A
planner may still look the domain up again and apply the position to the NEW
list (``$steps.lookup.emails[1].id``) — measured on Docker dev 2026-10-31: the
draft answered another message than the one the answer then named. The words
designated an item; nothing about the new list says it holds it, at that
position or at all.

When the plan never names the designated item and its acts read a position of
exactly ONE fresh lookup of the item's domain, the reads are bound to the
designated item itself and the lookup, read by nothing else, is dropped. A plan
that names the item somewhere, reads two lookups of the domain, or iterates over
one is left as written: its intent is no longer a single designation.

Pure functions over the plan and the resolved items; no I/O.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any, Final

from src.domains.agents.orchestration.for_each_utils import extract_step_references
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.tools.runtime_helpers import extract_value_by_path

__all__ = ["bind_designated_item"]

#: ``steps.<step>.<list>[<n>].<field>`` — groups: step, list path, position, fields.
_CORE: Final = r"steps\.(\w+)\.([A-Za-z_][\w.]*?)\[(\d+)\]((?:\.[A-Za-z_]\w*)*)"
#: A positional read in either form, as the plan's acts are scanned for one.
_POSITION_READ: Final = re.compile(r"(?<![\w.])\$?" + _CORE)
#: The DSL form, ``$steps.…``.
_DOLLAR_READ: Final = re.compile(r"(?<![\w.$])\$" + _CORE)
#: A template expression that is only the read, ``{{ steps.… }}`` — replaced whole.
_TEMPLATE_READ: Final = re.compile(r"\{\{\s*" + _CORE + r"\s*\}\}")


def _reads(step: ExecutionStep) -> str:
    return json.dumps(step.parameters or {}) + (step.condition or "") + (step.for_each or "")


def _read_sources(plan: ExecutionPlan, domain: str, acts: Callable[[str], bool]) -> set[str]:
    """The steps whose list of the domain the plan's acts read a position of."""
    acting = [
        step
        for step in plan.steps
        if step.step_type == StepType.TOOL and acts(step.tool_name or "")
    ]
    return {
        match.group(1)
        for step in acting
        for match in _POSITION_READ.finditer(_reads(step))
        if match.group(2).rsplit(".", 1)[-1] == domain
    }


def _lookup_read(plan: ExecutionPlan, domain: str, acts: Callable[[str], bool]) -> str | None:
    """The one fresh lookup of the domain the plan's acts read a position of, else None."""
    sources = _read_sources(plan, domain, acts)
    if len(sources) != 1:
        return None
    source = next(iter(sources))
    lookup = next((step for step in plan.steps if step.step_id == source), None)
    iterated = any(source in extract_step_references(s.for_each or "") for s in plan.steps)
    if lookup is None or lookup.for_each or iterated or acts(lookup.tool_name or ""):
        return None
    return source


def _names_the_item(plan: ExecutionPlan, item: Mapping[str, Any]) -> bool:
    """Whether the plan already carries the designated item's id somewhere."""
    identifier = item.get("id")
    return isinstance(identifier, str) and bool(identifier) and identifier in plan.model_dump_json()


def _without(steps: list[ExecutionStep], source: str) -> list[ExecutionStep] | None:
    """The steps once the lookup is gone — None when one still reads it."""
    if any(source in extract_step_references(_reads(step)) for step in steps):
        return None
    return [
        step.model_copy(update={"depends_on": [d for d in step.depends_on if d != source]})
        for step in steps
    ]


def _bound(value: Any, source: str, item: Mapping[str, Any]) -> Any:
    """A parameter value with every positional read of ``source`` bound to the item."""
    if isinstance(value, dict):
        return {key: _bound(nested, source, item) for key, nested in value.items()}
    if isinstance(value, list):
        return [_bound(nested, source, item) for nested in value]
    if not isinstance(value, str):
        return value

    def field_of(match: re.Match[str]) -> str:
        if match.group(1) != source:
            return match.group(0)
        found = extract_value_by_path(item, match.group(4).lstrip(".")) if match.group(4) else None
        if found is None or isinstance(found, dict | list):
            raise LookupError(match.group(0))
        return str(found)

    whole = _DOLLAR_READ.fullmatch(value) or _TEMPLATE_READ.fullmatch(value)
    if whole is not None and whole.group(1) == source:
        return field_of(whole)
    return _DOLLAR_READ.sub(field_of, _TEMPLATE_READ.sub(field_of, value))


def bind_designated_item(
    plan: ExecutionPlan,
    items: list[Mapping[str, Any]],
    domain: str,
    acts: Callable[[str], bool],
) -> ExecutionPlan | None:
    """The plan acting on the item the person designated, when it looked it up again.

    Args:
        plan: The plan as the planner wrote it.
        items: The items the turn resolved (one designation: exactly one).
        domain: Their context domain (a result key, ``emails``).
        acts: Whether a tool, by name, acts (its declared mutation policy).

    Returns:
        The repaired plan, or None when there is nothing to repair — or a read
        names a field the designated item does not carry.
    """
    if len(items) != 1 or not isinstance(items[0], Mapping) or _names_the_item(plan, items[0]):
        return None  # several items, or a plan naming the item: nothing to bind
    item = items[0]
    source = _lookup_read(plan, domain, acts)
    if source is None:
        return None
    try:
        bound = [
            step.model_copy(update={"parameters": _bound(step.parameters or {}, source, item)})
            for step in plan.steps
            if step.step_id != source
        ]
    except LookupError:
        return None
    steps = _without(bound, source)  # a lookup something else reads stays, and so does the plan
    return plan.model_copy(update={"steps": steps}) if steps is not None else None
