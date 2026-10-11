"""JSON Schema interpretation for MCP tool declarations.

The MCP specification (2026-07-28) defines a tool's ``inputSchema`` as a JSON
Schema 2020-12 object whose root is ``type: "object"``, and states that **any**
JSON Schema keyword may appear beyond that. Two independent consumers read that
same declaration — the LangChain adapter (which builds a Pydantic model) and the
planner catalogue (which builds ``ParameterSchema`` entries) — and each used to
carry its own idea of what a declaration meant.

They diverged, and the divergence was expensive: both keyed a lookup on the raw
``type`` value, which JSON Schema allows to be a **list** of names
(``["string", "null"]`` — how servers spell "optional string"). A list is
unhashable, so both raised ``TypeError``; the callers caught it per tool and
dropped the tool. Production, 2026-09-01: 30 of one server's 40 tools vanished,
including the only one able to list the user's bank accounts, and nothing but a
warning said so.

This module is therefore the single authority on what a JSON Schema declaration
means in this codebase. Every function here is total: it returns a usable answer
for any input a server can send, because the alternative — raising — costs a
tool. Deciding to DROP information stays the caller's job; deciding what a
declaration SAYS is this module's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import WithJsonSchema

from src.infrastructure.mcp.schema_constraints import merge_conjuncts
from src.infrastructure.mcp.schema_projection import binding_schema

#: JSON Schema type name → Python type used for Pydantic field annotations.
#: The keys are also the vocabulary of type names this codebase recognises,
#: so the planner catalogue narrows to the same set rather than keeping a
#: second copy that could drift.
JSON_SCHEMA_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}

#: The JSON Schema name for the null type. It is a nullability marker, never a
#: type this codebase maps to a Python annotation on its own.
NULL_TYPE = "null"

#: What an undecidable declaration degrades to. A string annotation is the most
#: permissive one that still gives providers a concrete type (Gemini rejects an
#: untyped declaration outright).
DEFAULT_TYPE = "string"


def as_property_spec(raw: Any) -> dict[str, Any]:
    """Return a property declaration as a dict, whatever the server sent.

    A property whose declaration is not an object carries nothing usable, but
    its NAME still does — the model needs to know the parameter exists. Degrade
    the declaration rather than dropping the property, the same doctrine
    :func:`sanitize_array_items` already applies to unusable ``items``.

    Args:
        raw: The value found under ``properties[<name>]``.

    Returns:
        ``raw`` when it is a dict, an empty dict otherwise.
    """
    return raw if isinstance(raw, dict) else {}


def description_of(spec: dict[str, Any]) -> str:
    """Return a property's description, guaranteed to be a string.

    ``description`` reaches provider function-declaration payloads verbatim, and
    a non-string value there is rejected by the provider — which would cost the
    whole bind, not just this field.

    Args:
        spec: A property declaration.

    Returns:
        The declared description, or an empty string when absent or not a string.
    """
    description = spec.get("description", "")
    return description if isinstance(description, str) else ""


def properties_of(input_schema: Any) -> dict[str, Any]:
    """Return a tool schema's ``properties`` map, whatever the server sent.

    Args:
        input_schema: A tool's ``inputSchema``, of any shape.

    Returns:
        The declared properties, or an empty dict when absent or not an object.
    """
    if not isinstance(input_schema, dict):
        return {}
    properties = resolve_property(input_schema, input_schema).spec.get("properties")
    return properties if isinstance(properties, dict) else {}


def required_of(input_schema: Any) -> set[str]:
    """Return the parameter names a tool schema marks required.

    Non-string entries are dropped rather than trusted: ``set("abc")`` on a
    stringly-typed ``required`` would silently mark three phantom parameters
    mandatory, and a non-iterable one would raise.

    Args:
        input_schema: A tool's ``inputSchema``, of any shape.

    Returns:
        The set of required parameter names, empty when the declaration is
        absent or unusable.
    """
    if not isinstance(input_schema, dict):
        return set()
    required = resolve_property(input_schema, input_schema).spec.get("required")
    if not isinstance(required, list):
        return set()
    return {name for name in required if isinstance(name, str)}


def normalize_schema_type(declared: Any) -> str:
    """Reduce a JSON Schema ``type`` declaration to ONE hashable type name.

    ``type`` may be a single name or, since draft-04, a **list** of names.
    Servers use the list form to express nullability (``["string", "null"]``),
    which is by far its dominant use in the wild.

    Nullability is carried separately — by the field's own annotation, and by
    :func:`declares_null` for callers that need to know — so the ``"null"``
    member adds nothing to the type decision. An unmappable single name is
    returned **unchanged** so callers keep applying their own historical
    fallback to it; only an undecidable declaration is resolved here.

    Args:
        declared: The raw value of a ``type`` keyword, of any shape.

    Returns:
        A single type name, always hashable and therefore always safe as a
        dict key.
    """
    if isinstance(declared, str):
        return declared
    if isinstance(declared, list):
        for member in declared:
            if isinstance(member, str) and member != NULL_TYPE and member in JSON_SCHEMA_TYPE_MAP:
                return member
    return DEFAULT_TYPE


def declares_null(declared: Any) -> bool:
    """Whether a ``type`` declaration says the server accepts ``null``.

    Read by the field builder so a REQUIRED parameter the server declared
    nullable stays nullable: refusing a value the server accepts would make
    this client stricter than the contract it implements.

    Args:
        declared: The raw value of a ``type`` keyword, of any shape.

    Returns:
        ``True`` when ``declared`` is a list containing ``"null"``.
    """
    return isinstance(declared, list) and NULL_TYPE in declared


def sanitize_array_items(field_spec: dict[str, Any]) -> dict[str, Any]:
    """Return a safe, always-typed ``items`` schema for an array property.

    Gemini's function-declaration converter maps an absent/empty ``items`` to an
    untyped proto that the API rejects with 400 INVALID_ARGUMENT
    ("parameters.properties[x].items: missing field") — and ONE such tool
    poisons the entire bind (every ReAct iteration on a Gemini model failed in
    prod, 2026-08-14). Preserve the server-declared item type when it is simple
    (type/enum/description; nested arrays recursively), and degrade anything
    unreliable ($ref, non-dict, tuple form) to string items rather than dropping
    the whole tool schema.

    Args:
        field_spec: The array property's declaration.

    Returns:
        An ``items`` schema that always carries a concrete ``type``.
    """
    items = field_spec.get("items")
    if isinstance(items, dict):
        declared = items.get("type")
        item_type = normalize_schema_type(declared) if declared is not None else None
        if item_type in JSON_SCHEMA_TYPE_MAP:
            sanitized = declaration_for(item_type, items)
            if isinstance(items.get("description"), str):
                sanitized["description"] = items["description"]
            return sanitized
        compacted = compact_schema(items)
        if compacted and any(key in compacted for key in ("anyOf", "oneOf")):
            return compacted
    return {"type": DEFAULT_TYPE}


def array_python_type(field_spec: dict[str, Any]) -> Any:
    """Schema-only items annotation: validation stays a permissive ``list``.

    ``WithJsonSchema`` replaces the emitted field schema without touching
    validation, so servers keep receiving exactly what they received before —
    only the declaration shown to providers gains its mandatory ``items``.

    Args:
        field_spec: The array property's declaration.

    Returns:
        An annotated ``list`` type carrying the sanitised ``items`` schema.
    """
    return Annotated[list, WithJsonSchema(declaration_for("array", field_spec))]


# --------------------------------------------------------------------------
# Full 2020-12 reduction
# --------------------------------------------------------------------------

#: How far a ``$ref`` chain or a nest of composition keywords is followed. Deep
#: enough for the shapes Pydantic and zod generators emit, shallow enough that a
#: hostile schema cannot make registration expensive.
MAX_RESOLUTION_DEPTH = 8

#: Python type to JSON Schema type name, for inferring from ``const``/``enum``
#: values. ``bool`` MUST precede ``int``: it subclasses it, so the reverse order
#: reports every boolean constant as an integer.
_PYTHON_TO_JSON_TYPE: tuple[tuple[type, str], ...] = (
    (bool, "boolean"),
    (int, "integer"),
    (float, "number"),
    (str, "string"),
    (list, "array"),
    (dict, "object"),
)

#: Composition keywords, in the order they are consulted.
_COMPOSITION_KEYWORDS: tuple[str, ...] = ("anyOf", "oneOf", "allOf")


@dataclass(frozen=True, slots=True)
class ResolvedType:
    """What a property declaration amounts to once every keyword is read.

    Attributes:
        name: A :data:`JSON_SCHEMA_TYPE_MAP` key, or ``None`` when the
            declaration carries no type this codebase can act on. ``None`` is
            an honest answer, not a failure: the caller keeps the property and
            types it permissively rather than inventing a type for it.
        nullable: Whether the declaration admits null, however it says so — a
            ``type`` list, an ``anyOf`` null member, a null ``const``, a null
            ``enum`` value.
        spec: The EFFECTIVE declaration: the ``$ref`` target, or the chosen
            composition member, so a caller reading ``items`` or ``properties``
            reads the ones that actually apply.
    """

    name: str | None
    nullable: bool
    spec: dict[str, Any] = field(default_factory=dict)


def _json_type_of_value(value: Any) -> str | None:
    """Infer a JSON Schema type name from a literal value.

    Args:
        value: A ``const`` or ``enum`` member.

    Returns:
        The JSON Schema type name, or None for a value with no mapping (null).
    """
    for python_type, name in _PYTHON_TO_JSON_TYPE:
        if isinstance(value, python_type):
            return name
    return None


def _is_null_schema(member: Any) -> bool:
    """Whether a composition member exists only to admit null.

    Args:
        member: One member of an ``anyOf`` / ``oneOf`` / ``allOf`` list.

    Returns:
        True when the member declares the null type and nothing else usable.
    """
    if not isinstance(member, dict):
        return False
    declared = member.get("type")
    if declared == NULL_TYPE:
        return True
    return isinstance(declared, list) and bool(declared) and set(declared) == {NULL_TYPE}


def _dereference(pointer: Any, root: Any, seen: frozenset[str]) -> dict[str, Any] | None:
    """Follow a same-document ``$ref`` against the tool own schema.

    Only local pointers are followed. A remote one would mean fetching a URL
    while registering a third-party tool, which this codebase will not do.

    Args:
        pointer: The raw ``$ref`` value.
        root: The whole ``inputSchema``, which owns ``$defs``/``definitions``.
        seen: Pointers already followed on this branch, so a cycle terminates.

    Returns:
        The referenced schema object, or None when it cannot be reached.
    """
    if not isinstance(pointer, str) or not pointer.startswith("#/") or pointer in seen:
        return None
    if not isinstance(root, dict):
        return None
    target: Any = root
    for raw_token in pointer[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or token not in target:
            return None
        target = target[token]
    return target if isinstance(target, dict) else None


def referenced_schema(pointer: object, root: object) -> dict[str, Any] | None:
    """Read a local reference without reducing away its union alternatives."""
    return _dereference(pointer, root, frozenset())


def _resolve(spec: Any, root: Any, depth: int, seen: frozenset[str]) -> ResolvedType:
    """Recursive core of :func:`resolve_property`.

    Args:
        spec: The declaration being reduced.
        root: The whole ``inputSchema``.
        depth: Current resolution depth.
        seen: Pointers already followed on this branch.

    Returns:
        The declaration effective type, nullability and spec.
    """
    if depth > MAX_RESOLUTION_DEPTH or not isinstance(spec, dict):
        return ResolvedType(None, False, {})

    pointer = spec.get("$ref")
    if pointer is not None:
        return _resolve_reference(spec, root, depth, seen)

    if isinstance(spec.get("allOf"), list) and spec["allOf"]:
        return _resolve_allof(spec, root, depth, seen)

    declared = spec.get("type")
    if declared is not None:
        return _resolve_declared(spec)

    if "const" in spec:
        value = spec["const"]
        return ResolvedType(_json_type_of_value(value), value is None, spec)

    for keyword in _COMPOSITION_KEYWORDS:
        members = spec.get(keyword)
        if isinstance(members, list) and members:
            return _resolve_composition(members, root, depth, seen, spec)

    values = spec.get("enum")
    if isinstance(values, list) and values:
        return _resolve_enum(values, spec)

    return ResolvedType(None, False, spec)


def _resolve_enum(values: list[object], spec: dict[str, object]) -> ResolvedType:
    inferred_name = next(
        (inferred for value in values if (inferred := _json_type_of_value(value)) is not None),
        None,
    )
    return ResolvedType(inferred_name, any(value is None for value in values), spec)


def _resolve_declared(spec: dict[str, object]) -> ResolvedType:
    declared = spec["type"]
    name = normalize_schema_type(declared)
    return ResolvedType(
        name if name in JSON_SCHEMA_TYPE_MAP else DEFAULT_TYPE,
        declares_null(declared),
        spec,
    )


def _resolve_reference(
    spec: dict[str, object], root: object, depth: int, seen: frozenset[str]
) -> ResolvedType:
    pointer = spec["$ref"]
    target = _dereference(pointer, root, seen)
    if target is None or not isinstance(pointer, str):
        return ResolvedType(None, False, {})
    siblings = {key: value for key, value in spec.items() if key != "$ref"}
    if not siblings:
        return _resolve(target, root, depth + 1, seen | {pointer})
    return _resolve({"allOf": [target, siblings]}, root, depth + 1, seen | {pointer})


def _resolve_allof(
    spec: dict[str, object], root: object, depth: int, seen: frozenset[str]
) -> ResolvedType:
    members = spec["allOf"]
    if not isinstance(members, list):
        return ResolvedType(None, False, spec)
    base = {key: value for key, value in spec.items() if key != "allOf"}
    resolved = [_resolve(member, root, depth + 1, seen) for member in [base, *members]]
    effective = merge_conjuncts([member.spec for member in resolved])
    summary = _resolve(effective, root, depth + 1, seen)
    typed = [member for member in resolved if member.name is not None]
    nullable = all(member.nullable for member in typed) if typed else summary.nullable
    return ResolvedType(summary.name, nullable, {**effective, "allOf": members})


def _resolve_composition(
    members: list[Any],
    root: Any,
    depth: int,
    seen: frozenset[str],
    parent: dict[str, Any],
) -> ResolvedType:
    """Reduce ``anyOf`` / ``oneOf`` / ``allOf`` to one usable type.

    ``{"anyOf": [{"type": "X"}, {"type": "null"}]}`` is how a generator spells
    the very same thing ``{"type": ["X", "null"]}`` spells; treating the two
    differently would be arbitrary. Members that exist only to admit null set
    nullability and are never candidates; the first member carrying a decidable
    type wins, and its spec becomes the effective one.

    Args:
        members: The composition list.
        root: The whole ``inputSchema``, for nested references.
        depth: Current resolution depth.
        seen: Pointers already followed on this branch.
        parent: The declaration carrying the composition, returned as the
            effective spec when no member is decidable.

    Returns:
        The reduced type.
    """
    nullable = False
    chosen: ResolvedType | None = None
    for member in members:
        if _is_null_schema(member):
            nullable = True
            continue
        resolved = _resolve(member, root, depth + 1, seen)
        nullable = nullable or resolved.nullable
        if chosen is None and resolved.name is not None:
            chosen = resolved
    if chosen is None:
        return ResolvedType(None, nullable, parent)
    return ResolvedType(
        chosen.name, nullable or chosen.nullable, _composition_spec(members, parent, chosen)
    )


def _composition_spec(
    members: list[object], parent: dict[str, object], chosen: ResolvedType
) -> dict[str, object]:
    non_null = [member for member in members if not _is_null_schema(member)]
    return parent if len(non_null) > 1 else chosen.spec


def resolve_property(spec: Any, root: Any) -> ResolvedType:
    """Reduce ANY JSON Schema 2020-12 property declaration to one usable type.

    The MCP specification (2026-07-28) says a tool ``inputSchema`` may carry any
    2020-12 keyword: "composition keywords (``oneOf``, ``anyOf``, ``allOf``,
    ``not``), conditional keywords (``if``/``then``/``else``), reference
    keywords (``$ref``, ``$defs``, ``$anchor``)". A client that reads only
    ``type`` is not conformant, and this one used to answer a whole tool schema
    with an opaque ``kwargs`` object the moment ONE property used any of them.
    Measured: the model was then shown no field names, no descriptions and no
    required list, so it could not call the tool at all.

    Resolution order follows what actually decides the type: ``$ref`` (local
    pointers only), then ``type``, then ``const``, then composition, then
    ``enum`` inference. Anything left over — ``not``, a bare ``if``/``then``,
    an unresolvable reference — resolves to ``name=None``, which callers keep as
    a permissively typed property rather than a lost one.

    Conjunctions and reference siblings retain their original branches and
    summarize their fields, required names and tighter ordinary scalar bounds.
    Conditional and remote declarations remain undecidable; no URL is fetched.

    Args:
        spec: The property declaration, of any shape.
        root: The tool whole ``inputSchema``, so ``$ref`` can reach ``$defs``.

    Returns:
        The declaration effective type, nullability and spec.
    """
    return _resolve(spec, root, depth=0, seen=frozenset())


def compact_schema(spec: Any, depth: int = 0) -> dict[str, Any] | None:
    """Compact a JSON Schema down to what a model needs to fill it.

    Recursively strips verbose fields (title, $schema, additionalProperties,
    default) while preserving the structural information that decides whether a
    generated call is correct: type, items, properties, required, enum, format.

    Recursion stops at 5 levels — deep enough for complex MCP schemas
    (Excalidraw elements: array -> object -> properties -> object -> properties)
    while bounding worst-case expansion.

    Used by BOTH the planner manifest and the tool signature, so a nested object
    cannot be described one way to the planner and another to the ReAct agent.
    It had been described to the planner only: the signature published a bare
    ``{"type": "object"}``, and a model reading it could not know the parameter
    needs a latitude, a longitude and a radius.

    Args:
        spec: Raw JSON Schema for one parameter, of any shape.
        depth: Current recursion depth (stops at 5).

    Returns:
        Compacted schema dict, or None if the spec carries nothing usable.
    """
    if depth > 5 or not isinstance(spec, dict):
        return None

    result: dict[str, Any] = {}
    declared_type = spec.get("type")
    # A union ("type": ["array", "null"]) must not make the branches below
    # false: they carry `items` and `properties`, and dropping those leaves the
    # reader an array of unknown element type.
    param_type = normalize_schema_type(declared_type) if declared_type is not None else None
    if isinstance(declared_type, list):
        _compact_type_union(declared_type, result)
    elif param_type:
        result["type"] = param_type

    # Enums are critical for the LLM (e.g., element type: rectangle, ellipse, ...)
    # A non-list one is not a closed set; forwarding it would put nonsense in
    # front of the model as if it were a contract.
    if isinstance(spec.get("enum"), list):
        result["enum"] = spec["enum"]
    if "format" in spec:
        result["format"] = spec["format"]
    if isinstance(spec.get("x-semantic-type"), str):
        result["x-semantic-type"] = spec["x-semantic-type"]
    _compact_constraints(spec, result)

    _compact_structure(spec, result, depth)
    _compact_compositions(spec, result, depth)

    return result if result else None


def _compact_structure(spec: dict[str, object], result: dict[str, object], depth: int) -> None:
    if "items" in spec:
        items = compact_schema(spec["items"], depth + 1)
        if items:
            result["items"] = items
    properties = spec.get("properties")
    if isinstance(properties, dict):
        result["properties"] = {
            name: compact_schema(child, depth + 1)
            or {"type": normalize_schema_type(as_property_spec(child).get("type", DEFAULT_TYPE))}
            for name, child in properties.items()
        }
    if isinstance(spec.get("required"), list):
        result["required"] = spec["required"]


def _compact_compositions(spec: dict[str, object], result: dict[str, object], depth: int) -> None:
    for key in _COMPOSITION_KEYWORDS:
        members = spec.get(key)
        if isinstance(members, list):
            compacted = [compact_schema(member, depth + 1) for member in members]
            if kept := [member for member in compacted if member]:
                result[key] = kept


def _compact_type_union(declared: list[object], result: dict[str, object]) -> None:
    names = [name for name in declared if name in (*JSON_SCHEMA_TYPE_MAP, NULL_TYPE)]
    if names and names != [NULL_TYPE]:
        result["anyOf"] = [{"type": name} for name in names]
    else:
        result["type"] = DEFAULT_TYPE


def _compact_constraints(spec: dict[str, object], result: dict[str, object]) -> None:
    for keyword in _NUMERIC_PUBLISHED:
        if _is_number(spec.get(keyword)):
            result[keyword] = spec[keyword]
    for keyword in (*_TEXT_PUBLISHED, "description"):
        if isinstance(spec.get(keyword), str):
            result[keyword] = spec[keyword]
    if isinstance(spec.get("additionalProperties"), bool):
        result["additionalProperties"] = spec["additionalProperties"]
    if "const" in spec:
        result["const"] = spec["const"]


# --------------------------------------------------------------------------
# Constraint publication (ADR-184)
# --------------------------------------------------------------------------

#: The subset of the catalogue's constraint kinds this module emits. Declared
#: as a Literal so the catalogue's own Literal accepts it without a cast: an
#: ignore here would hide the day the two vocabularies stop overlapping.
ConstraintKind = Literal["enum", "minimum", "maximum", "min_length", "max_length"]

#: JSON Schema keyword -> the constraint kind the agent catalogue already uses.
#: Mapping onto the EXISTING vocabulary is what plugs MCP parameters into the
#: planner rendering, the plan validator and the numeric clamping that native
#: tools have always had, without a second mechanism.
#:
#: ``pattern`` is deliberately absent, and that is a security decision rather
#: than an oversight: the plan validator compiles a constraint pattern with
#: ``re.match`` on an async path. A regex written by a third-party server is two
#: hazards there — an ECMA-262 pattern Python cannot compile, and a
#: catastrophic backtracker no ``except`` can interrupt, which would freeze the
#: event loop and every SSE stream with it. It is still PUBLISHED to providers
#: below, which only read it.
_CONSTRAINT_KINDS: tuple[tuple[str, ConstraintKind], ...] = (
    ("enum", "enum"),
    ("minimum", "minimum"),
    ("maximum", "maximum"),
    ("minLength", "min_length"),
    ("maxLength", "max_length"),
)

#: Keywords forwarded verbatim into the declaration shown to providers, each
#: with the shape it must have to be forwarded at all.
_NUMERIC_PUBLISHED: tuple[str, ...] = (
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
)
_TEXT_PUBLISHED: tuple[str, ...] = ("pattern", "format")


def _is_number(value: Any) -> bool:
    """Whether a value is a real number.

    ``isinstance(True, int)`` is True in Python, so a boolean would otherwise
    become ``minimum: 1`` and silently clamp every value of the parameter.

    Args:
        value: The declared keyword value.

    Returns:
        True for an int or float that is not a bool.
    """
    return isinstance(value, int | float) and not isinstance(value, bool)


def constraint_enum(spec: dict[str, Any]) -> list[Any] | None:
    """The closed set a declaration names, exactly as the server stated it.

    This is the set the PLAN VALIDATOR checks against, and its check is
    ``value not in expected``. The null member of a nullable enum therefore has
    to stay: strip it and an explicit ``direction: null`` becomes a
    CONSTRAINT_VIOLATION, which sets ``is_valid=False``, which makes
    ``route_from_semantic_validator`` return "planner" — an auto-replan for a
    value the server accepts.

    A set whose only member is null is refused: it would reject every real
    value, and a plan the validator can never satisfy replans until it runs out
    of iterations.

    Args:
        spec: A property declaration.

    Returns:
        The declared enum, or None when there is no usable one.
    """
    values = [spec["const"]] if "const" in spec else spec.get("enum")
    if not isinstance(values, list) or not values:
        return None
    if all(value is None for value in values):
        return None
    return values


def publishable_enum(spec: dict[str, Any]) -> list[Any] | None:
    """The closed set as a PROVIDER should see it, without its null member.

    Nullability reaches a provider through the field annotation, not through an
    enum member: Gemini types its enum members as strings, so a null inside one
    is a malformed closed set rather than extra information. This is the only
    place the two audiences differ — see :func:`constraint_enum` for why the
    validator keeps it.

    Args:
        spec: A property declaration.

    Returns:
        The non-null enum members, or None when there is no usable enum.
    """
    values = constraint_enum(spec)
    return [value for value in values if value is not None] if values else None


def constraints_of(spec: dict[str, Any]) -> dict[ConstraintKind, Any]:
    """The constraints a server enforces, keyed by the catalogue's vocabulary.

    A constraint the system enforces must be published to whoever produces the
    value (ADR-184): an MCP tool published none at all, so the planner guessed
    the members of a closed enum and the validator rejected the plan for
    guessing wrong.

    Args:
        spec: A property declaration (the EFFECTIVE one — after ``$ref`` and
            composition have been resolved).

    Returns:
        Mapping of ``ParameterConstraint`` kind to value, empty when the
        declaration constrains nothing this codebase can safely act on.
    """
    constraints: dict[ConstraintKind, Any] = {}
    for keyword, kind in _CONSTRAINT_KINDS:
        if keyword == "enum":
            # The VALIDATOR's set, null member included: see constraint_enum.
            values = constraint_enum(spec)
            if values is not None:
                constraints[kind] = values
            continue
        value = spec.get(keyword)
        if _is_number(value):
            constraints[kind] = value
    return constraints


def _publish_composition(declaration: dict[str, object], spec: dict[str, object]) -> None:
    """Keep the declared alternatives on the model-facing schema."""
    compacted = compact_schema(spec) or {}
    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword in compacted:
            declaration[keyword] = compacted[keyword]


def declaration_for(type_name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """The JSON Schema declaration shown to providers for a resolved property.

    Carries the type AND what the server enforces. A bound the model cannot see
    is a trap rather than a contract, and measured here: publishing the enum
    makes it reach Gemini's function declaration as a real closed set instead of
    a sentence buried in a description.

    Args:
        type_name: A :data:`JSON_SCHEMA_TYPE_MAP` key.
        spec: The effective property declaration.

    Returns:
        A declaration carrying the type, ``items`` for an array, and every
        constraint keyword that has the shape its dialect requires.
    """
    declaration: dict[str, Any] = {"type": type_name}
    if isinstance(spec.get("x-semantic-type"), str):
        declaration["x-semantic-type"] = spec["x-semantic-type"]
    _publish_structure(type_name, spec, declaration)
    if "const" in spec:
        declaration["const"] = spec["const"]
    _publish_composition(declaration, spec)
    if isinstance(spec.get("type"), list) and "anyOf" in declaration:
        declaration.pop("type", None)
    if isinstance(spec.get("additionalProperties"), bool):
        declaration["additionalProperties"] = spec["additionalProperties"]

    values = publishable_enum(spec)
    if values is not None:
        declaration["enum"] = values
    for keyword in _NUMERIC_PUBLISHED:
        # draft-04 spells exclusiveMinimum/Maximum as BOOLEANS; forwarding one
        # as a 2020-12 numeric bound would invent a bound the server never set.
        if _is_number(spec.get(keyword)):
            declaration[keyword] = spec[keyword]
    for keyword in _TEXT_PUBLISHED:
        if isinstance(spec.get(keyword), str):
            declaration[keyword] = spec[keyword]
    return binding_schema(declaration)


def _publish_structure(
    type_name: str, spec: dict[str, object], declaration: dict[str, object]
) -> None:
    if type_name == "array":
        declaration["items"] = sanitize_array_items(spec)
    if type_name == "object":
        compacted = compact_schema(spec) or {}
        for key in ("properties", "required"):
            if key in compacted:
                declaration[key] = compacted[key]


def annotation_for(type_name: str, spec: dict[str, Any]) -> Any:
    """The Python annotation for a resolved property.

    Constraints are SCHEMA-ONLY, the same contract :func:`array_python_type`
    already had: the declaration shown to the model gains them, validation does
    not. A server may accept more than it advertises, and it — not this client —
    is the authority on its own input; rejecting locally would turn a working
    call into an error we invented.

    An unconstrained scalar keeps its plain Python type, so a declaration that
    carries nothing extra emits exactly what it emitted before.

    Args:
        type_name: A :data:`JSON_SCHEMA_TYPE_MAP` key.
        spec: The effective property declaration.

    Returns:
        A Python type, or an annotated one carrying the published declaration.
    """
    if len(schema_type_names(spec) - {NULL_TYPE}) > 1:
        return Annotated[object, WithJsonSchema(binding_schema(compact_schema(spec) or {}))]
    if isinstance(spec.get("type"), list):
        # Nullability of this FIELD is carried by Pydantic's outer annotation.
        # Item schemas retain their own null branch through declaration_for.
        spec = {**spec, "type": type_name}
    if type_name == "array":
        return array_python_type(spec)
    declaration = declaration_for(type_name, spec)
    if set(declaration) == {"type"}:
        return JSON_SCHEMA_TYPE_MAP[type_name]
    return Annotated[JSON_SCHEMA_TYPE_MAP[type_name], WithJsonSchema(declaration)]


def schema_type_names(spec: object, depth: int = 0) -> set[str]:
    """Read all explicitly admitted primitive types, without choosing a branch."""
    if depth > MAX_RESOLUTION_DEPTH or not isinstance(spec, dict):
        return set()
    declared = spec.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return {name for name in declared if isinstance(name, str)}
    for keyword in ("anyOf", "oneOf"):
        members = spec.get(keyword)
        if isinstance(members, list):
            return set().union(*(schema_type_names(member, depth + 1) for member in members))
    values = spec.get("enum")
    if isinstance(values, list):
        return {_json_type_of_value(value) or NULL_TYPE for value in values}
    return set()
