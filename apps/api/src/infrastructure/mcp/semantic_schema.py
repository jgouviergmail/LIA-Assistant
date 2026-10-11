"""Project declared MCP schemas into the native semantic catalogue.

Only an explicit, registered semantic hint or an unambiguous JSON Schema
format establishes a bridge. Names such as ``id``, ``address`` and ``query``
say nothing about an unknown server's ontology. Local references are resolved
under a depth bound; remote references are never fetched.
"""

from __future__ import annotations

from src.domains.agents.registry.catalogue import OutputFieldSchema
from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.domains.agents.semantic.type_registry import TypeRegistry, get_registry
from src.infrastructure.mcp.json_schema import (
    MAX_RESOLUTION_DEPTH,
    ResolvedType,
    as_property_spec,
    description_of,
    properties_of,
    referenced_schema,
    required_of,
    resolve_property,
)

_FORMAT_TYPES = {
    "email": "email_address",
    "idn-email": "email_address",
    "uri": "URL",
    "iri": "URL",
    "date-time": "datetime",
    "date": "Date",
}
_HINT_KEYS = ("x-semantic-type", "semantic_type")
_SCALAR_STRING_TYPES = frozenset(_FORMAT_TYPES.values()) | {
    "physical_address",
    "formatted_address",
    "person_name",
    "phone_number",
    "locality",
    "country_code",
    "postal_code",
    "file_name",
}


def _non_null_branches(spec: object) -> list[dict[str, object]] | None:
    """Read declared union alternatives, excluding the nullable branch."""
    if not isinstance(spec, dict):
        return None
    for key in ("anyOf", "oneOf"):
        members = spec.get(key)
        if isinstance(members, list):
            return [
                member
                for member in members
                if isinstance(member, dict) and member.get("type") != "null"
            ]
    return None


def _scalar_string_matches(resolved: ResolvedType) -> bool:
    declared_types = resolved.spec.get("type")
    if isinstance(declared_types, list) and any(
        t not in ("string", "null") for t in declared_types
    ):
        return False
    return resolved.name == "string"


def _matches_hint_value(hint: str, resolved: ResolvedType, semantic_type: SemanticType) -> bool:
    if hint in _SCALAR_STRING_TYPES:
        return _scalar_string_matches(resolved)
    if semantic_type.category == TypeCategory.RESOURCE_ID:
        return resolved.name in ("string", "integer")
    if semantic_type.properties:
        return resolved.name == "object"
    return True


def _hint_declaration_matches(
    hint: str, spec: object, root: object, depth: int, semantic_type: SemanticType
) -> bool:
    if isinstance(spec, dict) and "$ref" in spec:
        return _hint_shape_matches(hint, referenced_schema(spec["$ref"], root), root, depth + 1)
    branches = _non_null_branches(spec)
    if branches is not None:
        return bool(branches) and all(
            _hint_shape_matches(hint, branch, root, depth + 1) for branch in branches
        )
    resolved = resolve_property(spec, root)
    if resolved.name == "array":
        if resolve_property(resolved.spec.get("items"), root).name == "array":
            return False
        return _hint_shape_matches(hint, resolved.spec.get("items"), root, depth + 1)
    return _matches_hint_value(hint, resolved, semantic_type)


def _hint_shape_matches(hint: str, spec: object, root: object, depth: int = 0) -> bool:
    """Reject a known scalar hint attached to an incompatible JSON object."""
    if depth > MAX_RESOLUTION_DEPTH:
        return False
    semantic_type = get_registry().get(hint)
    if semantic_type is None:
        return False
    return _hint_declaration_matches(hint, spec, root, depth, semantic_type)


def _explicit_hint(
    spec: dict[str, object], root: object, registry: TypeRegistry
) -> tuple[bool, str | None]:
    hints = [spec[key] for key in _HINT_KEYS if key in spec]
    if len(hints) > 1 and any(hint != hints[0] for hint in hints):
        return True, None
    for key in _HINT_KEYS:
        if key in spec:
            declared = spec[key]
            if (
                isinstance(declared, str)
                and declared in registry
                and _hint_shape_matches(declared, spec, root)
            ):
                return True, declared
            return True, None
    return False, None


def _common_semantic_type(
    branches: list[dict[str, object]], root: object, depth: int
) -> str | None:
    candidates = [semantic_type_of(member, root, depth + 1) for member in branches]
    return candidates[0] if candidates and all(t == candidates[0] for t in candidates) else None


def _array_semantic_type(resolved: ResolvedType, root: object, depth: int) -> str | None:
    if resolve_property(resolved.spec.get("items"), root).name == "array":
        return None
    return semantic_type_of(resolved.spec.get("items"), root, depth + 1)


def _formatted_semantic_type(
    spec: dict[str, object], resolved: ResolvedType, registry: TypeRegistry
) -> str | None:
    if resolved.name != "string":
        return None
    declared_types = spec.get("type")
    if isinstance(declared_types, list) and any(
        t not in ("string", "null") for t in declared_types
    ):
        return None
    declared_format = resolved.spec.get("format")
    mapped = _FORMAT_TYPES.get(declared_format) if isinstance(declared_format, str) else None
    return mapped if mapped is not None and mapped in registry else None


def semantic_type_of(spec: object, root: object, depth: int = 0) -> str | None:
    """Read a registered hint or format, never infer from a field's name."""
    if depth > MAX_RESOLUTION_DEPTH or not isinstance(spec, dict):
        return None
    resolved = resolve_property(spec, root)
    registry = get_registry()
    if not len(registry):
        load_core_types(registry)
    has_hint, hint = _explicit_hint(spec, root, registry)
    if not has_hint:
        has_hint, hint = _explicit_hint(resolved.spec, root, registry)
    if has_hint:
        return hint
    if "$ref" in spec:
        target = referenced_schema(spec["$ref"], root)
        if len(spec) == 1:
            return semantic_type_of(target, root, depth + 1)
        siblings = {key: value for key, value in spec.items() if key != "$ref"}
        return semantic_type_of({"allOf": [target, siblings]}, root, depth + 1)
    branches = _non_null_branches(spec)
    if branches is not None:
        return _common_semantic_type(branches, root, depth)
    if resolved.name == "array":
        return _array_semantic_type(resolved, root, depth)
    return _formatted_semantic_type(spec, resolved, registry)


def _schema_base(spec: dict[str, object], root: object, depth: int) -> dict[str, object]:
    if "$ref" in spec:
        target = referenced_schema(spec["$ref"], root)
        siblings = {key: value for key, value in spec.items() if key != "$ref"}
        if not siblings:
            return normalized_schema(target, root, depth + 1)
        return normalized_schema({"allOf": [target, siblings]}, root, depth + 1)
    if not any(isinstance(spec.get(key), list) for key in ("anyOf", "oneOf", "allOf")):
        return dict(resolve_property(spec, root).spec)
    effective = (
        dict(resolve_property(spec, root).spec)
        if isinstance(spec.get("allOf"), list)
        else dict(spec)
    )
    for key in ("anyOf", "oneOf", "allOf"):
        members = spec.get(key)
        if isinstance(members, list):
            effective[key] = [normalized_schema(member, root, depth + 1) for member in members]
    return effective


def normalized_schema(spec: object, root: object, depth: int = 0) -> dict[str, object]:
    """Resolve local references for the shared planner and ReAct declaration."""
    if depth > MAX_RESOLUTION_DEPTH or not isinstance(spec, dict):
        return {}
    effective = _schema_base(spec, root, depth)
    for key in ("description", "default"):
        if key in spec:
            effective[key] = spec[key]
    declared_properties = effective.get("properties")
    if isinstance(declared_properties, dict):
        effective["properties"] = {
            name: normalized_schema(child, root, depth + 1)
            for name, child in declared_properties.items()
        }
    if isinstance(effective.get("items"), dict):
        effective["items"] = normalized_schema(effective["items"], root, depth + 1)
    hint = semantic_type_of(spec, root)
    for key in _HINT_KEYS:
        effective.pop(key, None)
    if hint is not None:
        effective["x-semantic-type"] = hint
    return effective


def _reference_shape(spec: dict[str, object], root: object) -> dict[str, object]:
    shape = spec
    for _ in range(MAX_RESOLUTION_DEPTH):
        target = referenced_schema(shape.get("$ref"), root)
        if target is None:
            break
        shape = target
    return shape


def _has_mixed_types(shape: dict[str, object]) -> bool:
    declared_types = shape.get("type")
    return (
        isinstance(declared_types, list)
        and len({t for t in declared_types if isinstance(t, str) and t != "null"}) > 1
    )


def _output_shape_type(
    spec: dict[str, object], root: object, resolved: ResolvedType
) -> tuple[str, list[dict[str, object]]]:
    shape = _reference_shape(spec, root)
    alternatives = _non_null_branches(shape) or []
    possible_names = {resolve_property(member, root).name for member in alternatives}
    type_name = resolved.name or "any"
    if len(possible_names) > 1 or _has_mixed_types(shape):
        type_name = "any"
    return type_name, alternatives


def _visit_object_fields(
    resolved: ResolvedType,
    path: str,
    depth: int,
    nullable: bool,
    root: object,
    fields: list[OutputFieldSchema],
) -> None:
    declared_required = resolved.spec.get("required", [])
    required = declared_required if isinstance(declared_required, list) else []
    for name, child in properties_of(resolved.spec).items():
        if isinstance(name, str) and name.isascii() and name.isidentifier():
            _visit_output_fields(
                as_property_spec(child),
                f"{path}.{name}",
                depth + 1,
                nullable or name not in required,
                root,
                fields,
            )


def _visit_common_object_fields(
    members: list[ResolvedType],
    path: str,
    depth: int,
    nullable: bool,
    root: object,
    fields: list[OutputFieldSchema],
) -> None:
    property_maps = [properties_of(member.spec) for member in members]
    shared_names = set(property_maps[0]).intersection(*property_maps[1:])
    for name in property_maps[0]:
        if name not in shared_names or not (name.isascii() and name.isidentifier()):
            continue
        required = all(name in required_of(member.spec) for member in members)
        child = {"anyOf": [properties[name] for properties in property_maps]}
        _visit_output_fields(
            child, f"{path}.{name}", depth + 1, nullable or not required, root, fields
        )


def _visit_union_fields(
    alternatives: list[dict[str, object]],
    path: str,
    depth: int,
    nullable: bool,
    root: object,
    fields: list[OutputFieldSchema],
) -> None:
    members = [resolve_property(branch, root) for branch in alternatives]
    names = {member.name for member in members}
    if names == {"object"}:
        _visit_common_object_fields(members, path, depth, nullable, root, fields)
    elif names == {"array"}:
        items = [member.spec.get("items") for member in members]
        if all(isinstance(item, dict) for item in items):
            _visit_output_fields({"anyOf": items}, f"{path}[]", depth + 1, nullable, root, fields)


def _visit_output_fields(
    spec: object,
    path: str,
    depth: int,
    nullable_parent: bool,
    root: object,
    fields: list[OutputFieldSchema],
) -> None:
    if depth > MAX_RESOLUTION_DEPTH or not isinstance(spec, dict):
        return
    resolved = resolve_property(spec, root)
    type_name, alternatives = _output_shape_type(spec, root, resolved)
    nullable = nullable_parent or resolved.nullable
    fields.append(
        OutputFieldSchema(
            path=path,
            type=type_name,
            description=description_of(spec) or description_of(resolved.spec),
            nullable=nullable,
            semantic_type=semantic_type_of(spec, root),
        )
    )
    # Only fields available in every alternative are advertised as bridges.
    if len(alternatives) > 1:
        _visit_union_fields(alternatives, path, depth, nullable, root, fields)
        return
    if resolved.name == "object":
        _visit_object_fields(resolved, path, depth, nullable, root, fields)
    elif resolved.name == "array":
        _visit_output_fields(
            resolved.spec.get("items"), f"{path}[]", depth + 1, nullable, root, fields
        )


def output_fields_from_schema(output_schema: object) -> list[OutputFieldSchema]:
    """Declare the exact ``result`` paths the adapters expose, containers included."""
    if not isinstance(output_schema, dict) or not output_schema:
        return [OutputFieldSchema(path="result", type="any", description="MCP tool response")]
    fields: list[OutputFieldSchema] = []
    _visit_output_fields(output_schema, "result", 0, False, output_schema, fields)
    return fields
