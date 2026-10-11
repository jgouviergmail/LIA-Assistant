"""Read semantic annotations without confusing object leaves with whole values."""

import json
from collections.abc import Iterator

from src.core.context import (
    get_request_tool_manifests,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents import registry as registry_module
from src.domains.agents.registry.catalogue import (
    OutputFieldSchema,
    ParameterSchema,
    ToolManifest,
    ToolManifestNotFound,
)
from src.domains.agents.registry.request_tool_identity import offered_manifest_named


def available_manifests() -> list[ToolManifest]:
    """The request owns availability; only diagnostics may use the global fallback."""
    if request_tool_manifests_ctx.get() is not None:
        manifests: list[ToolManifest] = get_request_tool_manifests()
    else:
        manifests = registry_module.get_global_registry().list_tool_manifests()
    return manifests


def available_manifest(tool_name: str) -> ToolManifest | None:
    """Find an available native or account MCP contract, never resurrect a disabled tool."""
    if request_tool_manifests_ctx.get() is not None:
        manifest: ToolManifest | None
        manifest, _ = offered_manifest_named(
            tool_name, available_manifests(), user_mcp_tools_ctx.get()
        )
        return manifest
    try:
        return registry_module.get_global_registry().get_tool_manifest(tool_name)
    except ToolManifestNotFound:
        return None


def iter_schema_semantic_types(schema: object) -> Iterator[str]:
    """Read explicit annotations from resolved JSON Schema, without inference.

    MCP normalizes its declared formats and extensions to ``x-semantic-type``.
    Walking only schema keywords avoids treating a default/example as a schema.
    Leaves inform dependency discovery, but do not authorize substituting a
    scalar output for an entire object parameter.
    """
    if not isinstance(schema, dict):
        return
    annotation = schema.get("x-semantic-type")
    if isinstance(annotation, str):
        yield annotation
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for child in properties.values():
            yield from iter_schema_semantic_types(child)
    yield from iter_schema_semantic_types(schema.get("items"))
    for keyword in ("anyOf", "oneOf"):
        alternatives = schema.get(keyword)
        if isinstance(alternatives, list):
            branches = [
                set(iter_schema_semantic_types(child))
                for child in alternatives
                if isinstance(child, dict) and child.get("type") != "null"
            ]
            if branches:
                yield from sorted(set.intersection(*branches))
    for keyword in ("allOf", "prefixItems"):
        members = schema.get(keyword)
        if isinstance(members, list):
            for child in members:
                yield from iter_schema_semantic_types(child)


def parameter_semantic_types(parameter: ParameterSchema) -> set[str]:
    """Types consumed by a parameter and its explicitly annotated leaves."""
    types = set(iter_schema_semantic_types(parameter.schema))
    if parameter.semantic_type:
        types.add(parameter.semantic_type)
    role = getattr(parameter, "semantic_role", None)
    if role is not None:
        types.update(role.accepted_types)
    return types


def _required_property_names(schema: dict[str, object]) -> set[str]:
    """Required object fields, including constraints split across allOf members."""
    declared = schema.get("required")
    names = (
        {name for name in declared if isinstance(name, str)}
        if isinstance(declared, list)
        else set()
    )
    members = schema.get("allOf")
    if isinstance(members, list):
        for member in members:
            if isinstance(member, dict):
                names.update(_required_property_names(member))
    return names


def _required_composed_types(schema: dict[str, object], required_names: set[str]) -> set[str]:
    """Only semantics guaranteed by every union branch are prerequisites."""
    types: set[str] = set()
    members = schema.get("allOf")
    if isinstance(members, list):
        for member in members:
            types.update(_required_schema_semantic_types(member, required_names))
    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list) and branches:
            possibilities = [
                _required_schema_semantic_types(branch, required_names) for branch in branches
            ]
            types.update(set.intersection(*possibilities))
    return types


def _required_array_types(schema: dict[str, object]) -> set[str]:
    """Only positions guaranteed to exist carry required array prerequisites."""
    minimum = schema.get("minItems")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum <= 0:
        return set()
    prefixes = schema.get("prefixItems")
    members = prefixes if isinstance(prefixes, list) else []
    types: set[str] = set()
    for member in members[:minimum]:
        types.update(_required_schema_semantic_types(member))
    if minimum > len(members):
        types.update(_required_schema_semantic_types(schema.get("items")))
    return types


def _required_schema_semantic_types(
    schema: object, inherited_required: set[str] | None = None
) -> set[str]:
    """Read required leaves without promoting an optional field to a prerequisite."""
    if not isinstance(schema, dict):
        return set()
    annotation = schema.get("x-semantic-type")
    types = {annotation} if isinstance(annotation, str) else set()
    required_names = _required_property_names(schema) | (inherited_required or set())
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name in required_names:
            types.update(_required_schema_semantic_types(properties.get(name)))
    # A required array may still be empty. Its item type becomes a prerequisite
    # only when the contract requires at least one element.
    types.update(_required_array_types(schema))
    types.update(_required_composed_types(schema, required_names))
    return types


def required_parameter_semantic_types(parameter: ParameterSchema) -> set[str]:
    """Guaranteed semantic prerequisites of a required parameter and its leaves."""
    if not getattr(parameter, "required", False):
        return set()
    types = _required_schema_semantic_types(getattr(parameter, "schema", None))
    annotation = getattr(parameter, "semantic_type", None)
    if annotation:
        types.add(annotation)
    return types


def required_parameter_type_options(parameter: ParameterSchema) -> tuple[frozenset[str], ...]:
    """Each required leaf needs one admitted type, never every alternative at once."""
    types = required_parameter_semantic_types(parameter)
    annotation = getattr(parameter, "semantic_type", None)
    role = getattr(parameter, "semantic_role", None)
    options = [frozenset({type_name}) for type_name in sorted(types - {annotation})]
    if annotation in types:
        accepted = role.accepted_types if role is not None else ()
        options.append(frozenset({annotation, *accepted}))
    return tuple(options)


def _compatible_reference_shape(source: str, target: str | None) -> bool:
    """Reject container substitutions; array targets require actual arrays."""
    if not target or "any" in {source, target}:
        return True
    if target == "array":
        return source == "array"
    if "object" in {source, target}:
        return source == target
    if target in {"integer", "number"}:
        return source in {"integer", "number"}
    return True


def output_reference_path(
    output: OutputFieldSchema, parameter: ParameterSchema | None = None
) -> str | None:
    """Build a scalar sample or a shape-compatible parameter reference.

    Array annotations name the semantics of their elements. An array of email
    addresses is not itself an email address; selecting an element is explicit.
    Schema coercion cannot turn a JSON object into a valid address or handle.
    """
    target_type = parameter.type if parameter is not None else None
    if not _compatible_reference_shape(output.type, target_type):
        return None
    path: str = output.path.replace("[]", "[0]")
    if output.type == "array" and target_type != "array":
        path += "[0]"
    return path


def parameter_reference(
    step_id: str, output: OutputFieldSchema, parameter: ParameterSchema
) -> str | None:
    """A reference proposal with explicit singleton construction for array inputs.

    A sender address remains a useful source for an attendee list. Publishing
    the JSON array tells the planner to wrap that reference, without relying
    on a native coercion that an account MCP may not implement.
    """
    wrap = parameter.type == "array" and output.type in {"string", "integer", "number", "boolean"}
    path = output_reference_path(output, None if wrap else parameter)
    if path is None:
        return None
    reference = f"$steps.{step_id}.{path}"
    return json.dumps([reference]) if wrap else reference
