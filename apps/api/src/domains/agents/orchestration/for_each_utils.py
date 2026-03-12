"""
FOR_EACH Iteration Pattern Utilities.

Shared utilities for FOR_EACH pattern support across orchestration modules.
Centralizes regex patterns and helper functions to avoid DRY violations.

Used by:
    - dependency_graph.py: FOR_EACH expansion, $item substitution
    - parallel_executor.py: FOR_EACH readiness detection, wave execution

References:
    - plan_planner.md Section 6.2: FOR_EACH Expansion
    - plan_schemas.py: ExecutionStep.for_each fields

Created: 2026-01-19
"""

import re
from typing import TYPE_CHECKING, Any

from src.core.constants import FOR_EACH_ITEM_REF

if TYPE_CHECKING:
    from src.domains.agents.orchestration.plan_schemas import ExecutionStep

# ============================================================================
# PRE-COMPILED REGEX PATTERNS (Performance optimization)
# ============================================================================
# Compile regex patterns at module load time to avoid recompilation overhead
# during hot paths (execute_plan_parallel calls these multiple times per request)

# Pattern for extracting step_id and field_path from for_each reference
# Matches: $steps.step_1.places → captures ("step_1", "places")
# Matches: $steps.step_1.data.items → captures ("step_1", "data.items")
# Matches: $steps.step_1.contacts[*] → captures ("step_1", "contacts")
# The [*] suffix is optional and stripped for backward compatibility
PATTERN_FOR_EACH_REF = re.compile(r"\$steps\.(\w+)\.(.+?)(?:\[\*\])?$")

# Pattern for extracting only provider step_id from for_each reference
# Matches: $steps.step_1.places → captures "step_1"
# Lighter pattern when only step_id is needed (no field_path extraction)
PATTERN_FOR_EACH_PROVIDER = re.compile(r"\$steps\.(\w+)\.")

# Pattern for $steps.STEP_ID references in parameters/conditions
# Used for dependency detection in _extract_step_references
# Matches: $steps.search_contacts.contacts[0].email → captures "search_contacts"
PATTERN_DOLLAR_STEPS = re.compile(r"\$steps\.(\w+)(?:\.|\[)")

# Pattern for Jinja template references (used in _extract_step_references)
# Matches: {% for g in steps.group.groups %} → captures "group"
# Negative lookbehind ensures we don't match $steps (that's Pattern 1)
PATTERN_JINJA_STEPS = re.compile(r"(?<!\$)(?:{{|{%)[^}]*steps\.(\w+)(?:\.|\[)")

# Pattern for $item references in for_each step parameters
# Matches: $item, $item.field, $item.field.subfield, $item[0], $item.field[0].sub
PATTERN_ITEM_REF = re.compile(rf"{re.escape(FOR_EACH_ITEM_REF)}(?:\.[\w\[\]]+)*")

# Pattern for splitting path segments in $item.field.subfield references
# Splits on: . (dot), [ (open bracket), ] (close bracket)
PATTERN_PATH_SPLIT = re.compile(r"\.|\[|\]")


# ============================================================================
# FOR_EACH REFERENCE PARSING
# ============================================================================


def parse_for_each_reference(for_each_ref: str) -> tuple[str | None, str | None]:
    """
    Parse for_each reference to extract step_id and field_path.

    Args:
        for_each_ref: Reference string like "$steps.step_1.places" or "$steps.step_1.contacts[*]"

    Returns:
        Tuple of (step_id, field_path) or (None, None) if invalid

    Examples:
        >>> parse_for_each_reference("$steps.step_1.places")
        ("step_1", "places")

        >>> parse_for_each_reference("$steps.get_events.events")
        ("get_events", "events")

        >>> parse_for_each_reference("invalid")
        (None, None)
    """
    match = PATTERN_FOR_EACH_REF.match(for_each_ref)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def get_for_each_provider_step_id(for_each_ref: str) -> str | None:
    """
    Extract provider step_id from for_each reference.

    Lighter alternative to parse_for_each_reference() when only
    step_id is needed (no field_path extraction).

    Args:
        for_each_ref: Reference like "$steps.step_1.places"

    Returns:
        Provider step_id (e.g., "step_1") or None if invalid

    Examples:
        >>> get_for_each_provider_step_id("$steps.step_1.places")
        "step_1"

        >>> get_for_each_provider_step_id("invalid")
        None
    """
    match = PATTERN_FOR_EACH_PROVIDER.match(for_each_ref)
    return match.group(1) if match else None


# ============================================================================
# FOR_EACH READINESS DETECTION
# ============================================================================


def is_for_each_ready_for_expansion(
    step: "ExecutionStep",
    completed_steps: dict[str, dict[str, Any]],
) -> bool:
    """
    Check if a for_each step is ready to be expanded.

    A for_each step is ready when its provider step has completed
    and results are available for iteration.

    Args:
        step: The for_each step to check
        completed_steps: Steps completed so far (step_id -> result dict)

    Returns:
        True if provider step has completed, False otherwise

    Example:
        >>> step = ExecutionStep(for_each="$steps.get_contacts.contacts", ...)
        >>> completed_steps = {"get_contacts": {"contacts": [...]}}
        >>> is_for_each_ready_for_expansion(step, completed_steps)
        True
    """
    if not step.for_each:
        return False

    provider_id = get_for_each_provider_step_id(step.for_each)
    return provider_id is not None and provider_id in completed_steps


# ============================================================================
# STEP REFERENCE EXTRACTION
# ============================================================================


def extract_step_references(expression: str) -> set[str]:
    """
    Extract step_ids referenced in an expression.

    Detects both DSL-style ($steps.X.field) and Jinja-style (steps.X.field)
    references. Used for implicit dependency detection.

    Args:
        expression: Python expression, Jinja template, or JSON string

    Returns:
        Set of referenced step_ids

    Examples:
        >>> extract_step_references("$steps.search.contacts[0].email")
        {"search"}

        >>> extract_step_references("$steps.a.x > $steps.b.y")
        {"a", "b"}

        >>> extract_step_references("{% for g in steps.group.groups %}")
        {"group"}
    """
    # Pattern 1: $steps.STEP_ID.field or $steps.STEP_ID[index]
    matches = set(PATTERN_DOLLAR_STEPS.findall(expression))

    # Pattern 2: Jinja templates - steps.STEP_ID.field (without $)
    matches.update(PATTERN_JINJA_STEPS.findall(expression))

    return matches


# ============================================================================
# ITEM COUNT EXTRACTION (FOR_EACH HITL Pre-Execution)
# ============================================================================


def count_items_at_path(data: dict[str, Any], field_path: str) -> int:
    """
    Count items at a nested path in a dictionary.

    Used by FOR_EACH HITL pre-execution to count real items in API results.
    Navigates to the field_path and returns the count of items.

    Args:
        data: Dictionary containing the data (e.g., step result)
        field_path: Dot-separated path (e.g., "events" or "data.items")

    Returns:
        Number of items at the path:
        - len(list) if the value is a list
        - 1 if the value is a non-empty dict or scalar
        - 0 if the path doesn't exist or value is empty/None

    Examples:
        >>> count_items_at_path({"events": [1, 2, 3]}, "events")
        3

        >>> count_items_at_path({"data": {"items": [1, 2]}}, "data.items")
        2

        >>> count_items_at_path({"other": []}, "events")
        0

    Reference:
        - task_orchestrator_node._pre_execute_for_each_providers()
        - plan_planner.md Section 12 (FOR_EACH HITL)
    """
    try:
        result = data
        for part in field_path.split("."):
            if isinstance(result, dict):
                result = result.get(part)
                if result is None:
                    return 0
            else:
                return 0

        if isinstance(result, list):
            return len(result)
        elif result:
            return 1
        return 0

    except Exception:
        return 0


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Patterns
    "PATTERN_FOR_EACH_REF",
    "PATTERN_FOR_EACH_PROVIDER",
    "PATTERN_DOLLAR_STEPS",
    "PATTERN_JINJA_STEPS",
    "PATTERN_ITEM_REF",
    "PATTERN_PATH_SPLIT",
    # Functions
    "parse_for_each_reference",
    "get_for_each_provider_step_id",
    "is_for_each_ready_for_expansion",
    "extract_step_references",
    "count_items_at_path",
]
