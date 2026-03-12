"""
Type coercion utilities for tool arguments.

Issue #55: Robust string→list coercion for LLM-generated separator patterns.

This module provides shared type coercion functions used by:
- parallel_executor.py
- step_executor_node.py
- plan_executor.py

Following the DRY principle, these functions are centralized here
to avoid code duplication across executor modules.
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def coerce_string_to_list(value: str) -> list[str]:
    """
    Coerce string to list with robust separator handling.

    Issue #55 FIX: Handle LLM-generated separator patterns.

    The planner generates Jinja2 templates that produce strings like:
    - 'item1","item2' (quoted comma separator from LLM)
    - 'item1,item2' (simple comma)
    - 'item1' (single value)

    Follows Postel's Law: "Be liberal in what you accept"

    Args:
        value: String value to coerce to list

    Returns:
        List of cleaned string items

    Examples:
        >>> coerce_string_to_list('people/c123","people/c456')
        ['people/c123', 'people/c456']

        >>> coerce_string_to_list('item1,item2,item3')
        ['item1', 'item2', 'item3']

        >>> coerce_string_to_list('single_value')
        ['single_value']

        >>> coerce_string_to_list('')
        []
    """
    if not value or not value.strip():
        return []

    # Detect separator pattern and split accordingly
    if '","' in value:
        # Pattern: item1","item2 (LLM uses "," as separator thinking it's JSON-like)
        # Split by "," and strip surrounding quotes from each item
        items = value.split('","')
        pattern = "quoted_comma"
    elif "," in value:
        # Standard comma-separated: item1,item2
        items = value.split(",")
        pattern = "simple_comma"
    else:
        # Single value, wrap in list
        items = [value]
        pattern = "single_value"

    # Clean each item: strip whitespace and quotes (both " and ')
    cleaned = []
    for item in items:
        item = item.strip()
        # Strip leading/trailing quotes that may be left over
        item = item.strip('"').strip("'")
        if item:  # Only add non-empty items
            cleaned.append(item)

    logger.info(
        "coerced_string_to_list",
        original_value=value[:100] if len(value) > 100 else value,
        pattern=pattern,
        items_count=len(cleaned),
    )

    return cleaned


def is_list_type(type_hint: Any) -> bool:
    """
    Check if type hint is a list type (list, List, list[str], etc.).

    Handles:
    - Plain list type
    - Subscripted generics (list[str], list[dict])
    - Union types (list[str] | list[dict] | None)

    Args:
        type_hint: Type annotation to check

    Returns:
        True if the type hint represents a list type
    """
    import types
    import typing

    origin = typing.get_origin(type_hint)

    if origin is list:
        return True

    # Handle Union types:
    # - typing.Union for Optional[X] and Union[X, Y] (older syntax)
    # - types.UnionType for X | Y | Z (Python 3.10+ syntax)
    if origin is typing.Union or origin is types.UnionType:
        for arg in typing.get_args(type_hint):
            if typing.get_origin(arg) is list or arg is list:
                return True

    return False


__all__ = [
    "coerce_string_to_list",
    "is_list_type",
]
