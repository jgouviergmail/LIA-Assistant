"""
OpenAI strict-mode schema analysis.

Extracted from ``structured_output.py`` (file-size ratchet): deciding whether a
Pydantic schema can go through OpenAI's ``json_schema`` strict path is a
self-contained, purely static analysis with no LLM involvement.

Re-exported by ``structured_output`` so callers keep one import surface.

OpenAI's strict mode guarantees 100% schema conformance but has limitations:
- No additionalProperties (rejects dict[str, Any])
- Max 100 properties total
- Max 5 nesting levels
- All properties must be explicitly typed

See: https://platform.openai.com/docs/guides/structured-outputs#supported-schemas
"""

from typing import Any

from pydantic import BaseModel

# =============================================================================
# STRICT MODE SCHEMA ANALYSIS (OpenAI json_schema strict=True)
# =============================================================================
# OpenAI's strict mode guarantees 100% schema conformance but has limitations:
# - No additionalProperties (rejects dict[str, Any])
# - Max 100 properties total
# - Max 5 nesting levels
# - All properties must be explicitly typed
#
# See: https://platform.openai.com/docs/guides/structured-outputs#supported-schemas


def _analyze_schema_strict_compatibility(schema: type[BaseModel]) -> tuple[bool, str]:
    """
    Analyze if a Pydantic schema is compatible with OpenAI strict mode.

    OpenAI's json_schema strict=True mode guarantees 100% schema conformance
    but rejects certain patterns. This function analyzes the schema to determine
    if it can use strict mode.

    Args:
        schema: Pydantic BaseModel class to analyze

    Returns:
        Tuple of (is_compatible, reason)
        - is_compatible: True if schema can use strict mode
        - reason: Human-readable reason (for logging/metrics)

    Incompatible patterns:
        - dict[str, Any] → additionalProperties in JSON schema
        - >100 properties → exceeds OpenAI limit
        - >5 nesting levels → exceeds OpenAI limit
        - Open-ended unions (Union[T, Any])
    """
    try:
        json_schema = schema.model_json_schema()
    except Exception as e:
        return False, f"schema_generation_error: {e}"

    # Check 1: additionalProperties in root or nested definitions
    if _schema_has_additional_properties(json_schema):
        return False, "contains_additional_properties"

    # Check 2: Total property count
    property_count = _count_total_properties(json_schema)
    if property_count > 100:
        return False, f"exceeds_property_limit: {property_count} > 100"

    # Check 3: Nesting depth
    max_depth = _get_max_nesting_depth(json_schema)
    if max_depth > 5:
        return False, f"exceeds_nesting_limit: {max_depth} > 5"

    return True, "compatible"


def _has_type_indicator(schema: dict[str, Any]) -> bool:
    """Return True if a JSON-schema fragment declares a concrete type.

    An ``Any`` / bare ``dict`` field is emitted by Pydantic as ``{}`` (or
    metadata-only, e.g. ``{"description": ...}``) — no type-bearing key. OpenAI
    strict mode rejects such open-ended fields, so the absence of every
    type-indicating keyword marks the fragment as strict-incompatible.

    Args:
        schema: A JSON-schema fragment for a single property.

    Returns:
        True if any type-indicating keyword is present.
    """
    return any(
        key in schema for key in ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")
    )


def _schema_has_additional_properties(
    schema: dict[str, Any], visited: set[str] | None = None
) -> bool:
    """
    Recursively check if schema contains additionalProperties or open-ended objects.

    This pattern appears when Pydantic models contain dict[str, Any] fields.
    OpenAI strict mode rejects such schemas.

    IMPORTANT: OpenAI strict mode requires:
    - All object types must have "properties" defined
    - "additionalProperties": false must be set (no extra fields allowed)
    - All properties must be in "required" array

    A schema is incompatible if:
    - It has "additionalProperties": true (explicit)
    - It has "additionalProperties": {} (allows any type)
    - It has "type": "object" WITHOUT "properties" (implicit additionalProperties)
      This is how dict[str, Any] is represented in JSON schema

    Args:
        schema: JSON schema dict
        visited: Set of visited $ref definitions (cycle prevention)

    Returns:
        True if additionalProperties found or schema is open-ended, False otherwise
    """
    if visited is None:
        visited = set()

    # Check root level explicit additionalProperties
    if schema.get("additionalProperties") is True:
        return True

    # Check explicit additionalProperties: {} (allows any)
    additional_props = schema.get("additionalProperties")
    if isinstance(additional_props, dict) and not additional_props.get("type"):
        # additionalProperties: {} or additionalProperties with no constraints
        # This is typical for dict[str, Any]
        return True

    # CRITICAL FIX: Check for "type": "object" without "properties"
    # This is how dict[str, Any] is represented: {"type": "object"}
    # Without properties, it implicitly allows any properties (incompatible with strict mode)
    if schema.get("type") == "object" and "properties" not in schema:
        # This is an open-ended object (like dict[str, Any])
        # Skip if this is a $ref container (those are fine)
        if "$ref" not in schema:
            return True

    # Check properties recursively
    properties = schema.get("properties", {})
    for prop_schema in properties.values():
        if isinstance(prop_schema, dict):
            # An untyped property ({} or metadata-only) is how ``Any`` / bare
            # ``dict`` fields are emitted by Pydantic. It allows arbitrary content
            # and is incompatible with OpenAI strict mode (every field must be
            # explicitly typed). Caught here so such schemas route to
            # function_calling instead of the strict json_schema path.
            if not _has_type_indicator(prop_schema):
                return True
            if _schema_has_additional_properties(prop_schema, visited):
                return True

    # Check $defs (Pydantic v2 nested schemas)
    defs = schema.get("$defs", schema.get("definitions", {}))
    for def_name, def_schema in defs.items():
        if def_name in visited:
            continue
        visited.add(def_name)
        if isinstance(def_schema, dict):
            if _schema_has_additional_properties(def_schema, visited):
                return True

    # Check items (for arrays)
    items = schema.get("items")
    if isinstance(items, dict):
        if _schema_has_additional_properties(items, visited):
            return True

    # Check allOf, anyOf, oneOf
    for keyword in ("allOf", "anyOf", "oneOf"):
        sub_schemas = schema.get(keyword, [])
        for sub_schema in sub_schemas:
            if isinstance(sub_schema, dict):
                if _schema_has_additional_properties(sub_schema, visited):
                    return True

    return False


def _count_total_properties(schema: dict[str, Any], visited: set[str] | None = None) -> int:
    """
    Count total number of properties across all nested schemas.

    OpenAI strict mode limits total properties to 100.

    Args:
        schema: JSON schema dict
        visited: Set of visited $ref definitions (cycle prevention)

    Returns:
        Total property count
    """
    if visited is None:
        visited = set()

    count = 0

    # Count root properties
    properties = schema.get("properties", {})
    count += len(properties)

    # Count nested properties
    for prop_schema in properties.values():
        if isinstance(prop_schema, dict):
            count += _count_total_properties(prop_schema, visited)

    # Count $defs properties
    defs = schema.get("$defs", schema.get("definitions", {}))
    for def_name, def_schema in defs.items():
        if def_name in visited:
            continue
        visited.add(def_name)
        if isinstance(def_schema, dict):
            count += _count_total_properties(def_schema, visited)

    return count


def _get_max_nesting_depth(
    schema: dict[str, Any],
    current_depth: int = 0,
    *,
    defs: dict[str, Any] | None = None,
    visited: frozenset[str] | None = None,
) -> int:
    """
    Calculate maximum nesting depth of schema.

    OpenAI strict mode limits nesting to 5 levels.

    ``$ref`` is followed on purpose: Pydantic v2 never inlines a nested model,
    it emits it under ``$defs`` and references it. A walker that only descends
    ``properties``/``items`` therefore sees a FLAT schema and reported depth 1
    for a model nested seven levels deep — the limit check passed, strict mode
    was requested, and OpenAI rejected the call at runtime.

    Args:
        schema: JSON schema dict (or fragment).
        current_depth: Current depth in recursion.
        defs: Definition table of the ROOT schema, threaded through the
            recursion so a fragment can resolve its ``$ref``.
        visited: Definition names already expanded on the current branch —
            recursive models (``child: Self | None``) would otherwise loop.

    Returns:
        Maximum nesting depth
    """
    if defs is None:
        defs = schema.get("$defs") or schema.get("definitions") or {}
    if visited is None:
        visited = frozenset()

    # Resolve a reference to its definition, at the SAME depth: the $ref node
    # and the object it names are one level, not two.
    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = ref.rsplit("/", 1)[-1]
        target = defs.get(name)
        if not isinstance(target, dict) or name in visited:
            # Unresolvable reference, or a cycle: stop descending this branch.
            return current_depth
        return _get_max_nesting_depth(target, current_depth, defs=defs, visited=visited | {name})

    max_depth = current_depth

    # Check properties
    properties = schema.get("properties", {})
    for prop_schema in properties.values():
        if isinstance(prop_schema, dict):
            depth = _get_max_nesting_depth(
                prop_schema, current_depth + 1, defs=defs, visited=visited
            )
            max_depth = max(max_depth, depth)

    # Check items (arrays add depth)
    items = schema.get("items")
    if isinstance(items, dict):
        depth = _get_max_nesting_depth(items, current_depth + 1, defs=defs, visited=visited)
        max_depth = max(max_depth, depth)

    # Check unions (a branch may nest deeper than its siblings)
    for keyword in ("anyOf", "oneOf", "allOf"):
        for sub_schema in schema.get(keyword, []):
            if isinstance(sub_schema, dict):
                depth = _get_max_nesting_depth(
                    sub_schema, current_depth, defs=defs, visited=visited
                )
                max_depth = max(max_depth, depth)

    return max_depth
