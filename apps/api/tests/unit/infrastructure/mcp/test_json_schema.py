"""Unit tests for JSON Schema interpretation primitives.

The MCP specification (2026-07-28) states that a tool's ``inputSchema`` may
carry ANY JSON Schema 2020-12 keyword. These primitives are the single place
where this codebase decides what a declaration means, so every dialect quirk
a real server emits is pinned here rather than in each consumer.
"""

from __future__ import annotations

import pytest

from src.infrastructure.mcp.json_schema import (
    JSON_SCHEMA_TYPE_MAP,
    annotation_for,
    array_python_type,
    compact_schema,
    constraint_enum,
    constraints_of,
    declaration_for,
    declares_null,
    normalize_schema_type,
    properties_of,
    publishable_enum,
    required_of,
    resolve_property,
    sanitize_array_items,
)


class TestNormalizeSchemaType:
    """``type`` may be a name OR a list of names (draft-04 onward).

    A list is unhashable, so every lookup keyed on it raised TypeError and the
    tool was dropped whole (prod 2026-09-01: 30 of one server's 40 tools).
    """

    @pytest.mark.parametrize("name", sorted(JSON_SCHEMA_TYPE_MAP))
    def test_a_plain_name_is_returned_unchanged(self, name: str):
        assert normalize_schema_type(name) == name

    def test_an_unmappable_name_is_returned_unchanged(self):
        """Callers keep their own historical fallback for unknown names."""
        assert normalize_schema_type("custom_type") == "custom_type"

    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            (["string", "null"], "string"),
            (["boolean", "null"], "boolean"),
            (["integer", "null"], "integer"),
            (["number", "null"], "number"),
            (["array", "null"], "array"),
            (["object", "null"], "object"),
            (["null", "string"], "string"),
            (["number", "string"], "number"),
        ],
    )
    def test_a_union_keeps_its_first_mappable_concrete_member(self, declared, expected):
        assert normalize_schema_type(declared) == expected

    @pytest.mark.parametrize("declared", [["null"], [], ["date", "null"], [None, 3], None, 42, {}])
    def test_anything_undecidable_falls_back_to_string(self, declared):
        assert normalize_schema_type(declared) == "string"

    def test_the_result_is_always_hashable(self):
        """The whole point: the return value is safe as a dict key."""
        assert {normalize_schema_type(["string", "null"]): 1} == {"string": 1}


class TestDeclaresNull:
    """A union that lists ``null`` says the server accepts null."""

    @pytest.mark.parametrize("declared", [["string", "null"], ["null"], ["null", "integer"]])
    def test_true_when_null_is_a_member(self, declared):
        assert declares_null(declared) is True

    @pytest.mark.parametrize("declared", ["string", ["string"], [], None, {}, "null"])
    def test_false_otherwise(self, declared):
        assert declares_null(declared) is False


class TestSanitizeArrayItems:
    """``items`` must always emit a typed schema (Gemini rejects an untyped one)."""

    def test_union_item_type_is_normalized(self):
        assert sanitize_array_items({"type": "array", "items": {"type": ["string", "null"]}}) == {
            "type": "string"
        }

    def test_union_nested_array_items_stay_typed(self):
        out = sanitize_array_items(
            {"type": "array", "items": {"type": ["array", "null"], "items": {"type": "integer"}}}
        )
        assert out == {"type": "array", "items": {"type": "integer"}}

    @pytest.mark.parametrize(
        "field_spec",
        [
            {"type": "array"},
            {"type": "array", "items": {"$ref": "#/x"}},
            {"type": "array", "items": True},
            {"type": "array", "items": None},
            {"type": "array", "items": [{"type": "integer"}]},
            {"type": "array", "items": {"type": "weird"}},
        ],
    )
    def test_undecidable_items_degrade_to_string(self, field_spec):
        assert sanitize_array_items(field_spec) == {"type": "string"}

    def test_enum_and_description_survive_a_union(self):
        out = sanitize_array_items(
            {
                "type": "array",
                "items": {"type": ["string", "null"], "enum": ["a", "b"], "description": "d"},
            }
        )
        assert out == {"type": "string", "enum": ["a", "b"], "description": "d"}


class TestArrayPythonType:
    """The annotation is schema-only: validation stays a permissive list."""

    def test_union_array_still_declares_typed_items(self):
        from pydantic import BaseModel, create_model

        model: type[BaseModel] = create_model(
            "M",
            v=(array_python_type({"type": ["array", "null"], "items": {"type": "string"}}), ...),
        )
        assert model.model_json_schema()["properties"]["v"]["items"] == {"type": "string"}
        assert model(v=["a", 1]).v == ["a", 1]


class TestTotalAccessors:
    """A tool schema comes from a third-party server: every accessor is total.

    Raising here costs a tool on the user paths, and the ENTIRE admin MCP
    registration at boot, where the loop has no per-tool guard.
    """

    @pytest.mark.parametrize(
        ("input_schema", "expected"),
        [
            ({"properties": {"a": {"type": "string"}}}, {"a": {"type": "string"}}),
            ({}, {}),
            ({"properties": None}, {}),
            ({"properties": "junk"}, {}),
            ({"properties": ["a"]}, {}),
            ({"properties": {}}, {}),
        ],
    )
    def test_properties_of_always_returns_a_mapping(self, input_schema, expected):
        assert properties_of(input_schema) == expected

    @pytest.mark.parametrize(
        ("input_schema", "expected"),
        [
            ({"required": ["a", "b"]}, {"a", "b"}),
            ({}, set()),
            ({"required": None}, set()),
            ({"required": "abc"}, set()),
            ({"required": 42}, set()),
            ({"required": ["a", 3, None]}, {"a"}),
        ],
    )
    def test_required_of_always_returns_a_set_of_names(self, input_schema, expected):
        assert required_of(input_schema) == expected

    @pytest.mark.parametrize("raw", [None, "junk", 42, []])
    def test_neither_accessor_raises_on_a_non_mapping(self, raw):
        assert properties_of(raw) == {}
        assert required_of(raw) == set()


class TestResolveProperty:
    """The MCP spec (2026-07-28) is explicit about a tool's ``inputSchema``:

        "any JSON Schema 2020-12 keyword may appear alongside `type` —
        including composition keywords (`oneOf`, `anyOf`, `allOf`, `not`),
        conditional keywords (`if`/`then`/`else`), reference keywords
        (`$ref`, `$defs`, `$anchor`)"

    A client that cannot read them is not conformant. This reduction is total:
    it answers for every declaration, and says so honestly (``name is None``)
    when the declaration carries no type it can act on.
    """

    def test_a_plain_type_resolves_to_itself(self):
        r = resolve_property({"type": "integer"}, {})
        assert (r.name, r.nullable) == ("integer", False)

    def test_a_union_resolves_and_reports_nullability(self):
        r = resolve_property({"type": ["string", "null"]}, {})
        assert (r.name, r.nullable) == ("string", True)

    # --- composition ------------------------------------------------------
    def test_anyof_optional_idiom_is_the_union_spelled_differently(self):
        r = resolve_property({"anyOf": [{"type": "boolean"}, {"type": "null"}]}, {})
        assert (r.name, r.nullable) == ("boolean", True)

    def test_oneof_keeps_its_first_concrete_member(self):
        r = resolve_property({"oneOf": [{"type": "string"}, {"type": "integer"}]}, {})
        assert (r.name, r.nullable) == ("string", False)

    def test_anyof_carries_the_effective_spec_of_the_chosen_member(self):
        r = resolve_property(
            {"anyOf": [{"type": "array", "items": {"type": "integer"}}, {"type": "null"}]}, {}
        )
        assert r.name == "array"
        assert r.nullable is True
        assert sanitize_array_items(r.spec) == {"type": "integer"}

    def test_allof_takes_its_first_typed_member(self):
        r = resolve_property({"allOf": [{"type": "string"}, {"minLength": 1}]}, {})
        assert r.name == "string"

    def test_anyof_of_only_null_is_undecidable_but_nullable(self):
        r = resolve_property({"anyOf": [{"type": "null"}]}, {})
        assert (r.name, r.nullable) == (None, True)

    # --- references -------------------------------------------------------
    def test_ref_into_defs_is_resolved(self):
        root = {"$defs": {"Point": {"type": "object", "properties": {"x": {"type": "number"}}}}}
        r = resolve_property({"$ref": "#/$defs/Point"}, root)
        assert r.name == "object"
        assert r.spec["properties"]["x"] == {"type": "number"}

    def test_ref_into_legacy_definitions_is_resolved(self):
        root = {"definitions": {"Tag": {"type": "string"}}}
        assert resolve_property({"$ref": "#/definitions/Tag"}, root).name == "string"

    def test_ref_inside_anyof_is_resolved(self):
        root = {"$defs": {"Tag": {"type": "string"}}}
        r = resolve_property({"anyOf": [{"$ref": "#/$defs/Tag"}, {"type": "null"}]}, root)
        assert (r.name, r.nullable) == ("string", True)

    def test_an_unresolvable_ref_is_undecidable_not_fatal(self):
        assert resolve_property({"$ref": "#/$defs/Missing"}, {}).name is None
        assert resolve_property({"$ref": "https://elsewhere/x"}, {}).name is None

    def test_a_reference_cycle_terminates(self):
        root = {"$defs": {"A": {"$ref": "#/$defs/B"}, "B": {"$ref": "#/$defs/A"}}}
        assert resolve_property({"$ref": "#/$defs/A"}, root).name is None

    def test_a_deep_ref_chain_terminates(self):
        root = {"$defs": {f"N{i}": {"$ref": f"#/$defs/N{i + 1}"} for i in range(30)}}
        root["$defs"]["N30"] = {"type": "string"}
        assert resolve_property({"$ref": "#/$defs/N0"}, root).name is None

    # --- const & enum -----------------------------------------------------
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("x", "string"),
            (3, "integer"),
            (2.5, "number"),
            (True, "boolean"),
            ([1], "array"),
            ({}, "object"),
        ],
    )
    def test_const_infers_the_type_of_its_value(self, value, expected):
        assert resolve_property({"const": value}, {}).name == expected

    def test_const_null_is_nullable_and_untyped(self):
        r = resolve_property({"const": None}, {})
        assert (r.name, r.nullable) == (None, True)

    @pytest.mark.parametrize(
        ("values", "expected"), [(["a", "b"], "string"), ([1, 2], "integer"), ([True], "boolean")]
    )
    def test_enum_without_a_type_infers_from_its_values(self, values, expected):
        assert resolve_property({"enum": values}, {}).name == expected

    def test_enum_containing_null_is_nullable(self):
        """Era declares ``direction`` exactly this way: enum with a null member."""
        r = resolve_property({"enum": ["all", "debit", None], "default": "all"}, {})
        assert (r.name, r.nullable) == ("string", True)

    def test_a_declared_type_wins_over_enum_inference(self):
        assert resolve_property({"type": "string", "enum": [1, 2]}, {}).name == "string"

    # --- genuinely undecidable -------------------------------------------
    @pytest.mark.parametrize(
        "spec",
        [
            {"not": {"type": "string"}},
            {"if": {"type": "string"}, "then": {"minLength": 1}},
            {"description": "no type at all"},
            {},
            "junk",
            None,
        ],
    )
    def test_undecidable_declarations_say_so(self, spec):
        assert resolve_property(spec, {}).name is None

    def test_a_bool_enum_is_not_mistaken_for_an_integer(self):
        """``bool`` subclasses ``int`` — checking int first would mistype it."""
        assert resolve_property({"const": False}, {}).name == "boolean"


class TestConstraintsOf:
    """What a server enforces must reach whoever produces the value (ADR-184).

    An MCP tool used to publish no constraint at all: the planner guessed the
    allowed values of a closed enum and the validator rejected it for guessing
    wrong. These map onto the catalogue's OWN constraint vocabulary, so MCP
    parameters get the clamping, the validation and the catalogue rendering
    that native tools already had.
    """

    def test_enum_and_bounds_use_the_catalogue_vocabulary(self):
        assert constraints_of({"type": "integer", "minimum": 1, "maximum": 50, "enum": [1, 2]}) == {
            "minimum": 1,
            "maximum": 50,
            "enum": [1, 2],
        }

    def test_string_lengths_are_renamed_to_the_catalogue_kinds(self):
        assert constraints_of({"type": "string", "minLength": 2, "maxLength": 9}) == {
            "min_length": 2,
            "max_length": 9,
        }

    def test_the_null_member_is_KEPT_for_the_validator(self):
        """Measured, and the reason the two enums differ.

        Era spells an optional enum ``["all", "debit", null]``. This constraint
        reaches the PLAN VALIDATOR, whose check is ``value not in expected`` —
        so stripping the null makes an explicit ``direction: null`` a
        CONSTRAINT_VIOLATION, ``is_valid=False``, and
        ``route_from_semantic_validator`` sends the plan back for an auto-replan
        it never needed. The validator gets the set the SERVER stated;
        :func:`declaration_for` is where the null comes off, because a provider
        types enum members and nullability travels in the annotation instead.
        """
        assert constraints_of({"enum": ["all", "debit", None]}) == {"enum": ["all", "debit", None]}
        assert declaration_for("string", {"enum": ["all", "debit", None]}) == {
            "type": "string",
            "enum": ["all", "debit"],
        }

    def test_an_enum_of_only_null_publishes_nothing(self):
        """A closed set of just null would reject every real value, and a plan
        the validator can never satisfy replans until it runs out of iterations.
        A declaration that pathological buys no constraint at all."""
        assert constraints_of({"enum": [None]}) == {}
        assert "enum" not in declaration_for("string", {"enum": [None]})

    @pytest.mark.parametrize("value", [True, False, "3", None, [1]])
    def test_a_non_numeric_bound_is_ignored(self, value):
        """``isinstance(True, int)`` is True in Python — a boolean bound would
        become ``minimum: 1`` and silently clamp every value."""
        assert constraints_of({"minimum": value}) == {}

    def test_pattern_is_deliberately_not_a_constraint(self):
        """The plan validator compiles constraint patterns with ``re.match`` on
        an async path. A third-party regex there is two risks at once: an ECMA
        pattern Python cannot compile, and a catastrophic backtracker that no
        ``except`` can interrupt — it would freeze the event loop, SSE included.
        It is still published to providers, which only read it.
        """
        assert constraints_of({"type": "string", "pattern": "^(a+)+$"}) == {}
        assert declaration_for("string", {"pattern": "^(a+)+$"})["pattern"] == "^(a+)+$"

    def test_nothing_declared_yields_nothing(self):
        assert constraints_of({"type": "string"}) == {}
        assert constraints_of({}) == {}


class TestDeclarationFor:
    """The declaration shown to providers: type plus what the server enforces."""

    def test_a_scalar_carries_its_type_and_constraints(self):
        assert declaration_for("integer", {"minimum": 1, "maximum": 50}) == {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
        }

    def test_an_enum_is_published_without_its_null_member(self):
        assert declaration_for("string", {"enum": ["a", None]}) == {
            "type": "string",
            "enum": ["a"],
        }

    def test_an_array_keeps_its_items_and_its_size_bounds(self):
        assert declaration_for(
            "array", {"items": {"type": "string"}, "minItems": 1, "maxItems": 50}
        ) == {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 50}

    def test_format_travels_but_draft4_exclusive_bounds_do_not(self):
        """draft-04 spells ``exclusiveMinimum`` as a BOOLEAN; forwarding that as
        a 2020-12 numeric bound would invent ``exclusiveMinimum: 1``."""
        out = declaration_for("string", {"format": "date", "exclusiveMinimum": True})
        assert out == {"type": "string", "format": "date"}

    def test_a_numeric_exclusive_bound_does_travel(self):
        assert declaration_for("number", {"exclusiveMinimum": 0}) == {
            "type": "number",
            "exclusiveMinimum": 0,
        }


class TestAnnotationFor:
    """Constraints are SCHEMA-ONLY: the MCP server stays the authority."""

    def test_an_unconstrained_scalar_keeps_its_plain_python_type(self):
        assert annotation_for("string", {"type": "string"}) is str

    def test_a_constrained_scalar_publishes_but_does_not_enforce(self):
        from pydantic import Field, create_model

        model = create_model(
            "M",
            v=(annotation_for("string", {"enum": ["a", "b"]}) | None, Field(default=None)),
        )
        emitted = model.model_json_schema()["properties"]["v"]["anyOf"][0]
        assert emitted == {"type": "string", "enum": ["a", "b"]}
        # A server may accept more than it advertises; we never reject for it.
        assert model(v="something-else").v == "something-else"

    def test_an_array_annotation_still_carries_typed_items(self):
        from pydantic import Field, create_model

        model = create_model(
            "M",
            v=(annotation_for("array", {"items": {"type": "string"}, "maxItems": 3}), Field()),
        )
        emitted = model.model_json_schema()["properties"]["v"]
        assert emitted["items"] == {"type": "string"}
        assert emitted["maxItems"] == 3
        assert model(v=["a", 1, {}]).v == ["a", 1, {}]


class TestObjectStructureIsPublished:
    """A structured object parameter must not reach the model as an opaque type.

    The planner catalogue has always compacted nested ``properties`` into the
    manifest, but the tool SIGNATURE published ``{"type": "object"}`` and
    nothing else — so a ReAct agent calling the same tool could not know the
    object needs ``latitude``, ``longitude`` and ``radius``.

    Measured on Booking's ``coordinates`` parameter: the emitted field grows
    from 190 to 320 characters, roughly 35 tokens. That is the whole cost, and
    it buys a parameter the model could otherwise not fill at all — the same
    trade ``_compact_json_schema`` already made for the planner.
    """

    BOOKING_COORDINATES = {
        "type": "object",
        "description": "Geographic coordinates.",
        "additionalProperties": False,
        "properties": {
            "latitude": {"maximum": 90, "minimum": -90, "type": "number"},
            "longitude": {"maximum": 180, "minimum": -180, "type": "number"},
            "radius": {"exclusiveMinimum": 0, "maximum": 200, "type": "number"},
        },
        "required": ["latitude", "longitude", "radius"],
    }

    def test_nested_properties_and_required_are_declared(self):
        assert declaration_for("object", self.BOOKING_COORDINATES) == {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "radius": {"type": "number"},
            },
            "required": ["latitude", "longitude", "radius"],
        }

    def test_an_object_without_structure_keeps_its_plain_python_type(self):
        """No structure to publish means no churn on the emitted declaration."""
        assert annotation_for("object", {"type": "object", "description": "Metadata"}) is dict

    def test_the_declaration_reaches_the_emitted_field_schema(self):
        from pydantic import Field, create_model

        model = create_model(
            "M", where=(annotation_for("object", self.BOOKING_COORDINATES), Field())
        )
        emitted = model.model_json_schema()["properties"]["where"]
        assert emitted["required"] == ["latitude", "longitude", "radius"]
        assert set(emitted["properties"]) == {"latitude", "longitude", "radius"}
        # Validation stays a permissive dict: the server is the authority.
        assert model(where={"anything": 1}).where == {"anything": 1}

    def test_compaction_is_shared_with_the_planner_manifest(self):
        """One compaction, so the signature and the catalogue cannot disagree."""
        from src.infrastructure.mcp.registration import _compact_json_schema

        assert _compact_json_schema is compact_schema


class TestArraySizeBoundsSurviveCompaction:
    """Era declares ``maxItems: 50`` on ``rule_ids`` and rejects the call above
    it. The compaction stripped it, so the planner produced a list of any length
    and the server answered with an error nobody could have predicted — the very
    shape ADR-184 exists to prevent.
    """

    def test_array_bounds_reach_the_compacted_schema(self):
        assert compact_schema(
            {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 50}
        ) == {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 50,
        }

    def test_an_unbounded_array_gains_nothing(self):
        assert compact_schema({"type": "array", "items": {"type": "string"}}) == {
            "type": "array",
            "items": {"type": "string"},
        }

    def test_a_boolean_bound_is_not_forwarded(self):
        assert compact_schema({"type": "array", "maxItems": True}) == {"type": "array"}


class TestDocumentedReductionLimits:
    """Two reductions are partial ON PURPOSE. Pinned so they stay decisions.

    Neither shape appears in any of the seven live MCP servers this was measured
    against; widening them would be speculation, and an undocumented limit is a
    trap for whoever meets it first.
    """

    def test_a_ref_resolves_to_its_target_not_to_its_siblings(self):
        root = {"$defs": {"T": {"type": "string", "enum": ["a"]}}}
        resolved = resolve_property({"$ref": "#/$defs/T", "enum": ["z"]}, root)
        assert resolved.name == "string"
        # The TARGET's enum, not the sibling's.
        assert constraints_of(resolved.spec) == {"enum": ["a"]}

    def test_the_description_and_default_of_a_ref_site_are_recovered_downstream(self):
        """The field builder reads both specs, which is why these two survive."""
        from src.infrastructure.mcp.tool_adapter import build_args_schema

        model = build_args_schema(
            {
                "$defs": {"T": {"type": "string"}},
                "properties": {
                    "p": {"$ref": "#/$defs/T", "description": "At the site", "default": "d"}
                },
            }
        )
        assert model is not None
        field = model.model_json_schema()["properties"]["p"]
        assert field["description"] == "At the site"
        assert field["default"] == "d"

    def test_allof_keeps_the_type_of_its_first_member_not_the_union_of_bounds(self):
        resolved = resolve_property({"allOf": [{"type": "string"}, {"maxLength": 10}]}, {})
        assert resolved.name == "string"
        # The later member's bound is not published — the stated limit.
        assert constraints_of(resolved.spec) == {}


class TestHostileCompositionAndReferences:
    """The two branches a well-formed server never reaches.

    They exist because the module promises to be total for any payload a
    third-party server can send, and an untested promise is just a comment.
    """

    def test_a_non_dict_composition_member_is_not_a_null_member(self):
        resolved = resolve_property({"anyOf": ["junk", 42, None, {"type": "integer"}]}, {})
        assert (resolved.name, resolved.nullable) == ("integer", False)

    def test_a_composition_of_only_junk_is_undecidable(self):
        resolved = resolve_property({"oneOf": ["junk", 42]}, {})
        assert (resolved.name, resolved.nullable) == (None, False)

    @pytest.mark.parametrize("root", [None, "junk", 42, ["a"]])
    def test_a_ref_against_a_non_object_root_resolves_to_nothing(self, root):
        assert resolve_property({"$ref": "#/$defs/T"}, root).name is None

    def test_a_ref_with_escaped_pointer_tokens_is_followed(self):
        """RFC 6901 escapes: ``~1`` is ``/`` and ``~0`` is ``~``."""
        root = {"$defs": {"a/b~c": {"type": "integer"}}}
        assert resolve_property({"$ref": "#/$defs/a~1b~0c"}, root).name == "integer"

    def test_a_ref_pointing_at_a_non_object_resolves_to_nothing(self):
        root = {"$defs": {"T": "not a schema"}}
        assert resolve_property({"$ref": "#/$defs/T"}, root).name is None


class TestNullableEnumSurvivesThePlanValidator:
    """End-to-end oracle for the split: the constraint must not reject a value
    the server accepts, because a rejection here is not inert — it sets
    ``is_valid=False`` and ``route_from_semantic_validator`` returns "planner".
    """

    ERA_DIRECTION = {"default": "all", "enum": ["all", "debit", "credit", None]}

    @staticmethod
    def _violates(value, allowed) -> bool:
        from src.domains.agents.orchestration.validator import PlanValidator, ValidationResult
        from src.domains.agents.registry.catalogue import ParameterConstraint

        result = ValidationResult(is_valid=True)
        PlanValidator.__new__(PlanValidator)._validate_constraint(
            "direction",
            value,
            ParameterConstraint(kind="enum", value=allowed),
            0,
            "mcp_user_x_search_transactions",
            result,
        )
        return bool(result.errors)

    @pytest.mark.parametrize("value", ["all", "debit", "credit", None])
    def test_every_value_the_server_accepts_passes_validation(self, value):
        allowed = constraints_of(self.ERA_DIRECTION)["enum"]
        assert self._violates(value, allowed) is False

    def test_a_value_the_server_never_declared_is_still_caught(self):
        allowed = constraints_of(self.ERA_DIRECTION)["enum"]
        assert self._violates("outgoing", allowed) is True


class TestConstraintEnum:
    """The two audiences for one closed set, kept apart on purpose."""

    def test_the_declared_set_is_returned_verbatim(self):
        assert constraint_enum({"enum": ["a", "b", None]}) == ["a", "b", None]

    @pytest.mark.parametrize(
        "spec", [{}, {"enum": []}, {"enum": [None]}, {"enum": "junk"}, {"enum": None}]
    )
    def test_nothing_usable_returns_none(self, spec):
        assert constraint_enum(spec) is None

    def test_the_provider_form_is_the_same_set_minus_null(self):
        spec = {"enum": ["a", None, "b"]}
        assert constraint_enum(spec) == ["a", None, "b"]
        assert publishable_enum(spec) == ["a", "b"]

    def test_both_agree_when_no_null_is_declared(self):
        spec = {"enum": ["a", "b"]}
        assert constraint_enum(spec) == publishable_enum(spec) == ["a", "b"]


class TestCompactionRefusesMalformedKeywords:
    """The compacted schema is injected verbatim into the planner prompt.

    ``enum`` and ``required`` are copied straight through, so a server sending
    something that is not a list would put that value in front of the model as
    if it were a closed set or a list of mandatory fields. This module promises
    to be total for any payload a server can send; a keyword it cannot use is
    dropped, not forwarded.
    """

    @pytest.mark.parametrize("value", ["junk", 42, {"a": 1}, None])
    def test_a_non_list_enum_is_dropped(self, value):
        assert compact_schema({"type": "string", "enum": value}) == {"type": "string"}

    @pytest.mark.parametrize("value", ["junk", 42, {"a": 1}])
    def test_a_non_list_required_is_dropped(self, value):
        out = compact_schema(
            {"type": "object", "properties": {"a": {"type": "string"}}, "required": value}
        )
        assert out == {"type": "object", "properties": {"a": {"type": "string"}}}

    def test_a_well_formed_enum_and_required_still_travel(self):
        out = compact_schema(
            {
                "type": "object",
                "properties": {"a": {"type": "string", "enum": ["x", "y"]}},
                "required": ["a"],
            }
        )
        assert out == {
            "type": "object",
            "properties": {"a": {"type": "string", "enum": ["x", "y"]}},
            "required": ["a"],
        }
