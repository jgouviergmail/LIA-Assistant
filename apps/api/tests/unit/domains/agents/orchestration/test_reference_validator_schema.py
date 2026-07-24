"""Unit tests for the schema-validation path of ``ReferenceValidator``.

The runtime *array-bounds* path is already covered by
``tests/unit/domains/agents/test_planner_array_bounds.py``. This file pins the
other half — the ``$0``-cost, pre-execution gate that validates
``$steps.X.field.path`` references against tool JSON schemas and manifest
``reference_examples`` BEFORE a plan runs.

Why it matters: this gate decides whether a plan's cross-step references are
structurally sound. A false negative lets a malformed reference (e.g. a wrong
field name feeding a recipient address) flow into execution; a false positive
rejects a legitimate plan and forces a wasted LLM retry loop. Both are silent —
neither raises — so only behavioral tests catch a regression here.

The pure sub-units (``_traverse_schema_path``, ``_parse_field_path``,
``_path_matches_reference_examples`` …) are exercised directly with in-memory
schemas so no registry/LLM is needed.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.reference_validator import (
    ReferenceValidationError,
    ReferenceValidator,
)
from src.domains.agents.tools.common import ToolErrorCode

pytestmark = pytest.mark.unit


@pytest.fixture
def validator() -> ReferenceValidator:
    return ReferenceValidator()


# A representative Google-contacts-style response schema (object → array → object → array).
CONTACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "contacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "resource_name": {"type": "string"},
                    "displayName": {"type": "string"},
                    "emailAddresses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                        },
                    },
                },
            },
        },
        "total": {"type": "integer"},
    },
}


def _traverse(validator: ReferenceValidator, field_path: str) -> list[ReferenceValidationError]:
    """Run the schema traversal for a field path against CONTACT_SCHEMA."""
    segments = validator._parse_field_path(field_path)
    return validator._traverse_schema_path(
        schema=CONTACT_SCHEMA,
        segments=segments,
        tool_name="search_contacts_tool",
        field_path=field_path,
        full_reference=f"$steps.search.{field_path}",
        step_id="use_contact",
        step_index=1,
        parameter_name="to",
    )


# ============================================================================
# STEPS_REFERENCE_PATTERN — extraction of (step_id, field_path)
# ============================================================================


class TestStepsReferencePattern:
    def test_extracts_step_id_and_field_path(self, validator: ReferenceValidator) -> None:
        matches = validator.STEPS_REFERENCE_PATTERN.findall(
            "$steps.search.contacts[0].emailAddresses[0].value"
        )
        assert matches == [("search", "contacts[0].emailAddresses[0].value")]

    def test_extracts_multiple_references_in_one_string(
        self, validator: ReferenceValidator
    ) -> None:
        matches = validator.STEPS_REFERENCE_PATTERN.findall(
            "from:$steps.a.contacts[0].value OR to:$steps.b.contacts[1].value"
        )
        assert matches == [("a", "contacts[0].value"), ("b", "contacts[1].value")]

    def test_wildcard_index_is_captured(self, validator: ReferenceValidator) -> None:
        matches = validator.STEPS_REFERENCE_PATTERN.findall(
            "$steps.search.contacts[*].emailAddresses[*].value"
        )
        assert matches == [("search", "contacts[*].emailAddresses[*].value")]

    def test_non_reference_string_yields_no_match(self, validator: ReferenceValidator) -> None:
        assert validator.STEPS_REFERENCE_PATTERN.findall("just a plain subject line") == []

    def test_single_char_terminal_field_is_not_matched(self, validator: ReferenceValidator) -> None:
        """Documented gap: the field-path group needs >=2 chars, so a 1-char
        terminal field name (``$steps.s.x``) is NOT extracted. Pinned so a future
        regex change is a conscious decision, not an accident. Real tool fields
        are multi-character (``value``, ``resource_name``), so this never bites."""
        assert validator.STEPS_REFERENCE_PATTERN.findall("$steps.s.x") == []
        # Two chars already match:
        assert validator.STEPS_REFERENCE_PATTERN.findall("$steps.s.id") == [("s", "id")]


# ============================================================================
# _parse_field_path — segmentation
# ============================================================================


class TestParseFieldPath:
    def test_simple_dotted_path(self, validator: ReferenceValidator) -> None:
        assert validator._parse_field_path("start.dateTime") == ["start", "dateTime"]

    def test_array_index_is_split_out(self, validator: ReferenceValidator) -> None:
        assert validator._parse_field_path("contacts[0].value") == ["contacts", "[0]", "value"]

    def test_nested_arrays(self, validator: ReferenceValidator) -> None:
        assert validator._parse_field_path("contacts[0].emailAddresses[1].value") == [
            "contacts",
            "[0]",
            "emailAddresses",
            "[1]",
            "value",
        ]

    def test_wildcard_segment(self, validator: ReferenceValidator) -> None:
        assert validator._parse_field_path("contacts[*].value") == ["contacts", "[*]", "value"]

    def test_single_field_no_brackets(self, validator: ReferenceValidator) -> None:
        assert validator._parse_field_path("total") == ["total"]


# ============================================================================
# _normalize_path_for_matching / _extract_array_indices / _extract_step_id
# ============================================================================


class TestPureHelpers:
    def test_normalize_replaces_numeric_indices_with_wildcard(
        self, validator: ReferenceValidator
    ) -> None:
        assert (
            validator._normalize_path_for_matching("contacts[0].emailAddresses[12].value")
            == "contacts[*].emailAddresses[*].value"
        )

    def test_normalize_leaves_wildcards_untouched(self, validator: ReferenceValidator) -> None:
        assert validator._normalize_path_for_matching("contacts[*].value") == "contacts[*].value"

    def test_extract_array_indices(self, validator: ReferenceValidator) -> None:
        assert validator._extract_array_indices("contacts[0].emailAddresses[2].value") == [
            ("contacts", 0),
            ("emailAddresses", 2),
        ]

    def test_extract_array_indices_skips_wildcards(self, validator: ReferenceValidator) -> None:
        """Wildcards carry no concrete index, so bounds checking must ignore them."""
        assert validator._extract_array_indices("contacts[*].value") == []

    def test_extract_step_id(self, validator: ReferenceValidator) -> None:
        assert validator._extract_step_id("$steps.search_contacts.contacts[0].value") == (
            "search_contacts"
        )

    def test_extract_step_id_missing_returns_empty(self, validator: ReferenceValidator) -> None:
        assert validator._extract_step_id("no reference here") == ""


# ============================================================================
# _path_matches_reference_examples — the fast-path allow-list
# ============================================================================


class TestPathMatchesReferenceExamples:
    """Callers pass an already-normalized path; examples are normalized inside."""

    def test_exact_match_after_index_normalization(self, validator: ReferenceValidator) -> None:
        assert validator._path_matches_reference_examples(
            "contacts[*].emailAddresses[*].value", ["contacts[0].emailAddresses[0].value"]
        )

    def test_deeper_path_through_object_matches(self, validator: ReferenceValidator) -> None:
        """Branch 2, '.' separator: path deepens past an object-terminated example."""
        assert validator._path_matches_reference_examples(
            "contacts[*].name.givenName", ["contacts[*].name"]
        )

    def test_deeper_path_through_array_matches_regression(
        self, validator: ReferenceValidator
    ) -> None:
        """Regression: the documented 'more specific' case where the example
        terminates at an ARRAY field and the path deepens into it via '['.

        Before the fix, branch 2 only tested ``ref + '.'`` — but the next char is
        ``'['`` here — so this legitimate deeper path was WRONGLY rejected, and
        ``_validate_field_path`` returns that rejection fail-fast (never reaching
        schema validation). This is the exact example in the method's docstring.
        """
        assert validator._path_matches_reference_examples(
            "contacts[*].emailAddresses[*].value", ["contacts[*].emailAddresses"]
        )

    def test_path_is_prefix_of_example_matches(self, validator: ReferenceValidator) -> None:
        """Branch 3: path is a shorter prefix of a deeper documented example."""
        assert validator._path_matches_reference_examples(
            "contacts[*].emailAddresses", ["contacts[*].emailAddresses[*].value"]
        )

    def test_path_prefix_of_example_via_array_matches(self, validator: ReferenceValidator) -> None:
        assert validator._path_matches_reference_examples("contacts", ["contacts[*].resource_name"])

    def test_unrelated_path_does_not_match(self, validator: ReferenceValidator) -> None:
        assert not validator._path_matches_reference_examples(
            "contacts[*].phoneNumbers[*].value", ["contacts[*].emailAddresses[*].value"]
        )

    def test_sibling_field_is_not_a_false_prefix(self, validator: ReferenceValidator) -> None:
        """``emailAddressesExtra`` must not be treated as under ``emailAddresses``:
        the separator guard ('.'/'[') prevents a bare ``startswith`` false positive."""
        assert not validator._path_matches_reference_examples(
            "contacts[*].emailAddressesExtra", ["contacts[*].emailAddresses"]
        )


# ============================================================================
# _traverse_schema_path — the core JSON-schema walk
# ============================================================================


class TestTraverseSchemaPath:
    def test_valid_deep_path_returns_no_errors(self, validator: ReferenceValidator) -> None:
        assert _traverse(validator, "contacts[0].emailAddresses[0].value") == []

    def test_valid_scalar_field(self, validator: ReferenceValidator) -> None:
        assert _traverse(validator, "total") == []

    def test_wildcard_traverses_arrays(self, validator: ReferenceValidator) -> None:
        assert _traverse(validator, "contacts[*].emailAddresses[*].value") == []

    def test_unknown_field_is_rejected_with_available_fields(
        self, validator: ReferenceValidator
    ) -> None:
        errors = _traverse(validator, "contacts[0].emails[0].value")
        assert len(errors) == 1
        err = errors[0]
        assert err.code == ToolErrorCode.INVALID_INPUT
        assert err.invalid_field == "emails"
        # The real field is offered back to the LLM for a corrected retry.
        assert "emailAddresses" in (err.available_fields or [])
        assert "emailAddresses" in (err.suggestions or [])

    def test_array_index_on_non_array_is_rejected(self, validator: ReferenceValidator) -> None:
        errors = _traverse(validator, "total[0]")
        assert len(errors) == 1
        assert "not an array" in errors[0].message
        assert errors[0].context is not None
        assert errors[0].context["actual_type"] == "integer"

    def test_field_access_on_non_object_is_rejected(self, validator: ReferenceValidator) -> None:
        errors = _traverse(validator, "total.subfield")
        assert len(errors) == 1
        assert "not an object" in errors[0].message

    def test_array_without_items_schema_is_failsafe_allowed(
        self, validator: ReferenceValidator
    ) -> None:
        """A schema whose array omits ``items`` cannot be validated further — the
        gate is fail-SAFE (allow) rather than fail-closed, to avoid rejecting a
        plan on an under-specified schema."""
        schema = {"type": "object", "properties": {"rows": {"type": "array"}}}
        segments = validator._parse_field_path("rows[0].anything")
        errors = validator._traverse_schema_path(
            schema=schema,
            segments=segments,
            tool_name="t",
            field_path="rows[0].anything",
            full_reference="$steps.s.rows[0].anything",
            step_id="s2",
            step_index=1,
            parameter_name="p",
        )
        assert errors == []

    def test_first_unknown_field_short_circuits(self, validator: ReferenceValidator) -> None:
        """Only the first invalid segment is reported (fail-fast), not a cascade."""
        errors = _traverse(validator, "wrongRoot[0].deeper")
        assert len(errors) == 1
        assert errors[0].invalid_field == "wrongRoot"


# ============================================================================
# Field-name suggestions & type extraction
# ============================================================================


class TestSuggestionsAndTypes:
    def test_suggest_field_names_finds_close_match(self, validator: ReferenceValidator) -> None:
        suggestions = validator._suggest_field_names(
            "emailAdress", ["emailAddresses", "phoneNumbers", "resource_name"]
        )
        assert "emailAddresses" in suggestions

    def test_suggest_field_names_no_close_match(self, validator: ReferenceValidator) -> None:
        assert validator._suggest_field_names("xyz", ["emailAddresses", "phoneNumbers"]) == []

    def test_suggest_field_names_empty_available(self, validator: ReferenceValidator) -> None:
        assert validator._suggest_field_names("anything", []) == []

    def test_get_field_info_with_types_classifies_arrays(
        self, validator: ReferenceValidator
    ) -> None:
        schema = {
            "type": "object",
            "properties": {
                "resource_name": {"type": "string"},
                "count": {"type": "number"},
                "emailAddresses": {"type": "array", "items": {"type": "object"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "scores": {"type": "array", "items": {"type": "number"}},
                "raw": {"type": "array"},
            },
        }
        types = validator._get_field_info_with_types(schema)
        assert types == {
            "resource_name": "string",
            "count": "number",
            "emailAddresses": "array<object>",
            "tags": "array<string>",
            "scores": "array<number>",
            "raw": "array",
        }

    def test_get_field_info_non_object_returns_empty(self, validator: ReferenceValidator) -> None:
        assert validator._get_field_info_with_types({"type": "string"}) == {}

    def test_find_similar_reference_examples(self, validator: ReferenceValidator) -> None:
        similar = validator._find_similar_reference_examples(
            "contacts[*].emailAdress",
            ["contacts[*].emailAddresses[*].value", "contacts[*].phoneNumbers[*].value"],
        )
        assert similar and "emailAddresses" in similar[0]

    def test_find_similar_empty_examples(self, validator: ReferenceValidator) -> None:
        assert validator._find_similar_reference_examples("x", []) == []


# ============================================================================
# _build_enhanced_error_message — the LLM-facing retry hint
# ============================================================================


class TestEnhancedErrorMessage:
    def test_message_contains_invalid_field_suggestion_and_context(
        self, validator: ReferenceValidator
    ) -> None:
        msg = validator._build_enhanced_error_message(
            invalid_field="emails",
            available_fields=["emailAddresses", "phoneNumbers", "resource_name"],
            field_types={"emailAddresses": "array<object>"},
            suggestions=["emailAddresses"],
            full_reference="$steps.search.contacts[0].emails[0].value",
            tool_name="search_contacts_tool",
            step_id="send",
            parameter_name="to",
        )
        assert "emails" in msg
        assert "emailAddresses" in msg  # suggestion surfaced
        assert "search_contacts_tool" in msg
        assert "step 'send'" in msg
        assert "parameter 'to'" in msg

    def test_message_truncates_long_field_lists(self, validator: ReferenceValidator) -> None:
        available = [f"field_{i}" for i in range(20)]
        msg = validator._build_enhanced_error_message(
            invalid_field="nope",
            available_fields=available,
            field_types={},
            suggestions=[],
            full_reference="$steps.s.nope",
            tool_name="t",
            step_id="s",
            parameter_name="p",
        )
        assert "+12 more" in msg  # 20 - 8 shown = 12 hidden


# ============================================================================
# validate_references_in_step — public entry (no-registry paths)
# ============================================================================


class TestValidateReferencesInStep:
    def test_plain_parameters_without_references_are_valid(
        self, validator: ReferenceValidator
    ) -> None:
        errors = validator.validate_references_in_step(
            step_id="send",
            step_index=1,
            parameters={"subject": "Hello", "body": "No references here."},
            step_tools={},
        )
        assert errors == []

    def test_reference_to_unknown_step_is_skipped_not_errored(
        self, validator: ReferenceValidator
    ) -> None:
        """A reference to a step absent from ``step_tools`` is left for
        ``PlanValidator`` to catch (logged + continue), not double-reported here."""
        errors = validator.validate_references_in_step(
            step_id="send",
            step_index=1,
            parameters={"to": "$steps.ghost.contacts[0].value"},
            step_tools={},  # 'ghost' not present -> no tool_name -> skip
        )
        assert errors == []

    def test_non_string_parameter_values_are_ignored(self, validator: ReferenceValidator) -> None:
        errors = validator.validate_references_in_step(
            step_id="send",
            step_index=1,
            parameters={"count": 5, "flags": ["a", "b"], "meta": {"k": "v"}},
            step_tools={},
        )
        assert errors == []
