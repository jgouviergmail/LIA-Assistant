"""Unit tests for the OpenAI strict-mode schema analysis.

``_analyze_schema_strict_compatibility`` decides, per schema, whether the router
/ planner / classifier calls go through OpenAI's ``json_schema`` strict path
(100 % conformance) or fall back to ``function_calling``. The decision is made
from the JSON schema alone, before any network call, and NOTHING re-checks it:
a wrong "compatible" verdict surfaces later as an OpenAI rejection on a hot
path, a wrong "incompatible" one silently gives up schema conformance.

The depth walker is the subtle one. Pydantic v2 does not inline nested models —
it emits them under ``$defs`` and references them with ``$ref``, so a walker
that only descends ``properties`` and ``items`` sees a FLAT schema and reports
depth 1 for a model nested seven levels deep.
"""

from typing import Any

import pytest
from pydantic import BaseModel, Field

from src.infrastructure.llm.structured_output import (
    _analyze_schema_strict_compatibility,
    _count_total_properties,
    _get_max_nesting_depth,
    _has_type_indicator,
    _schema_has_additional_properties,
)

pytestmark = pytest.mark.unit


# OpenAI strict-mode limits, mirrored from the analyzer's own thresholds.
MAX_PROPERTIES = 100
MAX_NESTING = 5


# ============================================================================
# FIXTURE MODELS
# ============================================================================


class Flat(BaseModel):
    """The nominal strict-compatible shape."""

    reasoning: str
    next_node: str


class WithOpenDict(BaseModel):
    """``dict[str, Any]`` becomes an open-ended object in JSON schema."""

    metadata: dict[str, Any]


class WithAnyField(BaseModel):
    """A bare ``Any`` field is emitted without any type indicator."""

    payload: Any = Field(default=None)


class Leaf(BaseModel):
    value: str


class Level3(BaseModel):
    leaf: Leaf


class Level2(BaseModel):
    child: Level3


class Nested(BaseModel):
    """Nested models are ``$ref``-ed, never inlined."""

    child: Level2


class SelfReferential(BaseModel):
    """A recursive model — the walker must not loop forever."""

    name: str
    child: "SelfReferential | None" = None


SelfReferential.model_rebuild()


def _deep_model(levels: int) -> type[BaseModel]:
    """Build a chain of ``levels`` nested models (leaf carries one scalar)."""
    current: type[BaseModel] = type("Leaf0", (BaseModel,), {"__annotations__": {"value": str}})
    for index in range(levels):
        current = type(
            f"Level{index + 1}",
            (BaseModel,),
            {"__annotations__": {"child": current}},
        )
    return current


# ============================================================================
# TYPE INDICATOR
# ============================================================================


class TestHasTypeIndicator:
    """An untyped fragment is how ``Any`` reaches the schema."""

    @pytest.mark.parametrize(
        "fragment",
        [
            {"type": "string"},
            {"$ref": "#/$defs/X"},
            {"anyOf": []},
            {"oneOf": []},
            {"allOf": []},
            {"enum": ["a"]},
            {"const": "a"},
        ],
    )
    def test_typed_fragments_are_recognised(self, fragment: dict[str, Any]) -> None:
        assert _has_type_indicator(fragment) is True

    @pytest.mark.parametrize("fragment", [{}, {"description": "free text"}, {"title": "X"}])
    def test_untyped_fragments_are_rejected(self, fragment: dict[str, Any]) -> None:
        assert _has_type_indicator(fragment) is False


# ============================================================================
# OPEN-ENDED OBJECTS
# ============================================================================


class TestAdditionalProperties:
    """Strict mode rejects anything that accepts arbitrary keys."""

    def test_flat_typed_schema_is_clean(self) -> None:
        assert _schema_has_additional_properties(Flat.model_json_schema()) is False

    def test_explicit_additional_properties_true(self) -> None:
        assert _schema_has_additional_properties({"additionalProperties": True}) is True

    def test_unconstrained_additional_properties(self) -> None:
        assert _schema_has_additional_properties({"additionalProperties": {}}) is True

    def test_object_without_properties_is_open_ended(self) -> None:
        assert _schema_has_additional_properties({"type": "object"}) is True

    def test_dict_any_field_is_detected(self) -> None:
        assert _schema_has_additional_properties(WithOpenDict.model_json_schema()) is True

    def test_untyped_field_is_detected(self) -> None:
        assert _schema_has_additional_properties(WithAnyField.model_json_schema()) is True

    def test_detects_an_open_object_inside_defs(self) -> None:
        schema = {
            "properties": {"child": {"$ref": "#/$defs/Inner"}},
            "$defs": {"Inner": {"type": "object"}},
        }
        assert _schema_has_additional_properties(schema) is True

    def test_detects_an_open_object_inside_array_items(self) -> None:
        schema = {"properties": {"rows": {"type": "array", "items": {"type": "object"}}}}
        assert _schema_has_additional_properties(schema) is True

    @pytest.mark.parametrize("keyword", ["anyOf", "oneOf", "allOf"])
    def test_detects_an_open_object_inside_a_union(self, keyword: str) -> None:
        schema = {"properties": {"x": {keyword: [{"type": "object"}]}}}
        assert _schema_has_additional_properties(schema) is True

    def test_recursive_definitions_terminate(self) -> None:
        assert isinstance(
            _schema_has_additional_properties(SelfReferential.model_json_schema()), bool
        )


# ============================================================================
# PROPERTY COUNT
# ============================================================================


class TestCountTotalProperties:
    def test_counts_root_properties(self) -> None:
        assert _count_total_properties(Flat.model_json_schema()) == 2

    def test_counts_properties_declared_in_defs(self) -> None:
        """Nested models live in ``$defs``; their fields still count."""
        # Nested.child + Level2.child + Level3.leaf + Leaf.value
        assert _count_total_properties(Nested.model_json_schema()) == 4

    def test_empty_schema_counts_zero(self) -> None:
        assert _count_total_properties({}) == 0

    def test_a_definition_is_counted_once(self) -> None:
        schema = {
            "properties": {"a": {"$ref": "#/$defs/X"}, "b": {"$ref": "#/$defs/X"}},
            "$defs": {"X": {"properties": {"v": {"type": "string"}}}},
        }
        assert _count_total_properties(schema) == 3

    def test_recursive_model_terminates(self) -> None:
        assert _count_total_properties(SelfReferential.model_json_schema()) > 0


# ============================================================================
# NESTING DEPTH
# ============================================================================


class TestGetMaxNestingDepth:
    """The walker must follow ``$ref``, which is how Pydantic emits nesting."""

    def test_flat_schema_has_depth_one(self) -> None:
        assert _get_max_nesting_depth(Flat.model_json_schema()) == 1

    def test_inline_nesting_is_measured(self) -> None:
        schema = {"properties": {"a": {"properties": {"b": {"type": "string"}}}}}
        assert _get_max_nesting_depth(schema) == 2

    def test_array_items_add_a_level(self) -> None:
        schema = {"properties": {"rows": {"type": "array", "items": {"type": "string"}}}}
        assert _get_max_nesting_depth(schema) == 2

    def test_ref_nesting_is_followed(self) -> None:
        """Regression: a ``$ref`` chain used to measure as depth 1."""
        assert _get_max_nesting_depth(Nested.model_json_schema()) == 4

    def test_deeply_nested_model_exceeds_the_openai_limit(self) -> None:
        schema = _deep_model(7).model_json_schema()

        assert _get_max_nesting_depth(schema) > MAX_NESTING

    def test_recursive_model_does_not_loop_forever(self) -> None:
        depth = _get_max_nesting_depth(SelfReferential.model_json_schema())

        assert isinstance(depth, int)
        assert depth >= 1

    def test_unresolvable_ref_is_ignored(self) -> None:
        schema = {"properties": {"a": {"$ref": "#/$defs/Missing"}}}

        assert _get_max_nesting_depth(schema) == 1


# ============================================================================
# VERDICT
# ============================================================================


class TestStrictCompatibilityVerdict:
    """The single decision the rest of the helper acts on."""

    def test_flat_schema_is_compatible(self) -> None:
        compatible, reason = _analyze_schema_strict_compatibility(Flat)
        assert compatible is True
        assert reason == "compatible"

    def test_dict_any_schema_is_rejected(self) -> None:
        compatible, reason = _analyze_schema_strict_compatibility(WithOpenDict)
        assert compatible is False
        assert reason == "contains_additional_properties"

    def test_deeply_nested_schema_is_rejected(self) -> None:
        """Regression: a 7-level model was declared compatible and OpenAI
        rejected the request at call time."""
        compatible, reason = _analyze_schema_strict_compatibility(_deep_model(7))

        assert compatible is False
        assert "nesting" in reason

    def test_shallow_nested_schema_stays_compatible(self) -> None:
        compatible, reason = _analyze_schema_strict_compatibility(Nested)

        assert compatible is True, reason

    def test_property_explosion_is_rejected(self) -> None:
        wide = type(
            "Wide",
            (BaseModel,),
            {"__annotations__": {f"field_{i}": str for i in range(MAX_PROPERTIES + 1)}},
        )

        compatible, reason = _analyze_schema_strict_compatibility(wide)

        assert compatible is False
        assert "property_limit" in reason

    def test_schema_generation_failure_degrades_to_incompatible(self) -> None:
        class Broken:
            @staticmethod
            def model_json_schema() -> dict[str, Any]:
                raise RuntimeError("boom")

        compatible, reason = _analyze_schema_strict_compatibility(Broken)  # type: ignore[arg-type]

        assert compatible is False
        assert "schema_generation_error" in reason
