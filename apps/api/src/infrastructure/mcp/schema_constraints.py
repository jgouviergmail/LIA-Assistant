"""Combine conjunctive MCP declarations without discarding later constraints.

The original allOf branches remain published as the authority. These summaries
allow catalogue readers to find required fields and ordinary scalar bounds.
"""

from __future__ import annotations

_LOWER_BOUNDS = {"minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties"}
_UPPER_BOUNDS = {"maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties"}


def _merge_numeric(key: str, previous: object, value: object) -> object:
    if not isinstance(previous, int | float) or not isinstance(value, int | float):
        return value
    if isinstance(previous, bool) or isinstance(value, bool):
        return value
    if key in _LOWER_BOUNDS:
        return max(previous, value)
    if key in _UPPER_BOUNDS:
        return min(previous, value)
    return value


def _merge_properties(left: object, right: dict[str, object]) -> dict[str, object]:
    merged = dict(left) if isinstance(left, dict) else {}
    for name, declaration in right.items():
        merged[name] = {"allOf": [merged[name], declaration]} if name in merged else declaration
    return merged


def _merge_keyword(key: str, previous: object, value: object) -> object:
    if key == "properties" and isinstance(value, dict):
        return _merge_properties(previous, value)
    if key == "required" and isinstance(value, list):
        old = previous if isinstance(previous, list) else []
        return list(dict.fromkeys(name for name in old + value if isinstance(name, str)))
    if key == "enum" and isinstance(previous, list) and isinstance(value, list):
        return [member for member in previous if member in value]
    return _merge_numeric(key, previous, value)


def merge_conjuncts(declarations: list[dict[str, object]]) -> dict[str, object]:
    """Summarize intersecting fields; callers also keep the original branches."""
    merged: dict[str, object] = {}
    for declaration in declarations:
        for key, value in declaration.items():
            if (
                key in ("format", "x-semantic-type", "semantic_type")
                and key in merged
                and merged[key] != value
            ):
                merged[key] = None
            elif key != "allOf":
                merged[key] = _merge_keyword(key, merged.get(key), value)
    return merged
