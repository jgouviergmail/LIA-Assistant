"""Keep an exact conjunction and a redundant summary visible to limited converters.

Google's installed converter reads allOf[0]. The first branch therefore carries
the constraints already summarized on the declaration; original branches remain
authoritative, so unsupported combinations are never weakened silently.
"""

from __future__ import annotations

import json

_ASSERTION_KEYS = frozenset(
    {
        "enum",
        "const",
        "format",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "additionalProperties",
        "required",
        "minProperties",
        "maxProperties",
        "uniqueItems",
        "contains",
    }
)


def _needs_contract(schema: dict[str, object], depth: int = 0) -> bool:
    if _ASSERTION_KEYS & schema.keys() or isinstance(schema.get("properties"), dict):
        return True
    if depth >= 8:
        return False
    if any(isinstance(schema.get(key), list) for key in ("anyOf", "oneOf")):
        return True
    children = schema.get("allOf", [])
    if isinstance(children, list):
        return any(
            _needs_contract(child, depth + 1) for child in children if isinstance(child, dict)
        )
    return False


def binding_description(description: str, schema: dict[str, object]) -> str:
    """A limited converter still publishes the original contract to its producer."""
    if not _needs_contract(schema):
        return description
    contract = {
        key: value
        for key, value in schema.items()
        if key not in ("description", "title", "default", "x-semantic-type")
    }
    encoded = json.dumps(contract, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f"{description}\nDeclared JSON Schema constraints (preserve these when supplying values): {encoded}".strip()


def _structure(projected: dict[str, object], depth: int) -> None:
    properties = projected.get("properties")
    if isinstance(properties, dict):
        projected["properties"] = {
            name: binding_schema(child, depth + 1) for name, child in properties.items()
        }
    for key in ("items", "additionalProperties"):
        if isinstance(projected.get(key), dict):
            projected[key] = binding_schema(projected[key], depth + 1)


def _compositions(projected: dict[str, object], depth: int) -> None:
    for key in ("allOf", "anyOf", "oneOf"):
        members = projected.get(key)
        if isinstance(members, list):
            projected[key] = [binding_schema(member, depth + 1) for member in members]
    branches = projected.get("allOf")
    if isinstance(branches, list) and branches:
        summary = {key: value for key, value in projected.items() if key != "allOf"}
        if summary:
            projected["allOf"] = [summary, *branches]


def binding_schema(spec: object, depth: int = 0) -> dict[str, object]:
    if not isinstance(spec, dict):
        return {}
    projected = dict(spec)
    if depth < 8:
        _structure(projected, depth)
        _compositions(projected, depth)
    return projected
