"""
Unit tests for reference resolver service.

Phase: Session 9 - Tests Services (Reference Resolution)
Created: 2025-11-20

Focus: Linguistic reference extraction and resolution (ordinals, demonstratives, comparatives)
"""

import pytest

from src.domains.agents.services.reference_resolver import (
    ExtractedReference,
    ExtractedReferences,
    ReferenceResolver,
    ResolvedContext,
    get_reference_resolver,
    reset_reference_resolver,
)


class TestExtractedReference:
    def test_create_ordinal_reference(self):
        """Test creating an ordinal reference."""
        ref = ExtractedReference(
            type="ordinal",
            text="le deuxième",
            index=1,
            pattern=r"(?:le|la)\s*(?:2[eè]me|deuxième)",
        )
        assert ref.type == "ordinal"
        assert ref.text == "le deuxième"
        assert ref.index == 1
        assert ref.pattern == r"(?:le|la)\s*(?:2[eè]me|deuxième)"

    def test_create_demonstrative_reference(self):
        """Test creating a demonstrative reference."""
        ref = ExtractedReference(
            type="demonstrative",
            text="celui-ci",
            index=0,
            pattern=r"\bcelui-ci\b",
        )
        assert ref.type == "demonstrative"
        assert ref.text == "celui-ci"
        assert ref.index == 0

    def test_create_comparative_reference(self):
        """Test creating a comparative reference."""
        ref = ExtractedReference(
            type="comparative",
            text="le suivant",
            index=None,
            pattern=r"\ble\s+suivant\b",
        )
        assert ref.type == "comparative"
        assert ref.text == "le suivant"
        assert ref.index is None


class TestExtractedReferences:
    def test_empty_references(self):
        """Test empty references collection."""
        refs = ExtractedReferences(references=[])
        assert refs.has_explicit() is False
        assert refs.get_ordinals() == []
        assert refs.get_demonstratives() == []

    def test_has_explicit_with_references(self):
        """Test has_explicit() returns True when references exist."""
        ref = ExtractedReference(type="ordinal", text="first", index=0, pattern="")
        refs = ExtractedReferences(references=[ref])
        assert refs.has_explicit() is True

    def test_get_ordinals_filters_correctly(self):
        """Test get_ordinals() returns only ordinal references."""
        ordinal1 = ExtractedReference(type="ordinal", text="first", index=0, pattern="")
        ordinal2 = ExtractedReference(type="ordinal", text="second", index=1, pattern="")
        demonstrative = ExtractedReference(type="demonstrative", text="this", index=0, pattern="")

        refs = ExtractedReferences(references=[ordinal1, demonstrative, ordinal2])
        ordinals = refs.get_ordinals()

        assert len(ordinals) == 2
        assert all(r.type == "ordinal" for r in ordinals)

    def test_get_demonstratives_filters_correctly(self):
        """Test get_demonstratives() returns only demonstrative references."""
        ordinal = ExtractedReference(type="ordinal", text="first", index=0, pattern="")
        demo1 = ExtractedReference(type="demonstrative", text="this", index=0, pattern="")
        demo2 = ExtractedReference(type="demonstrative", text="that", index=0, pattern="")

        refs = ExtractedReferences(references=[ordinal, demo1, demo2])
        demonstratives = refs.get_demonstratives()

        assert len(demonstratives) == 2
        assert all(r.type == "demonstrative" for r in demonstratives)


class TestResolvedContext:
    def test_create_resolved_context_explicit(self):
        """Test creating resolved context with explicit method."""
        items = [{"id": 1}, {"id": 2}]
        context = ResolvedContext(
            items=items,
            confidence=1.0,
            method="explicit",
            source_turn_id=5,
        )
        assert context.items == items
        assert context.confidence == 1.0
        assert context.method == "explicit"
        assert context.source_turn_id == 5

    def test_create_resolved_context_lifecycle(self):
        """Test creating resolved context with lifecycle method."""
        context = ResolvedContext(
            items=[],
            confidence=0.5,
            method="lifecycle",
            source_turn_id=None,
        )
        assert context.method == "lifecycle"
        assert context.confidence == 0.5
        assert context.source_turn_id is None

    def test_create_resolved_context_error(self):
        """Test creating resolved context for error case."""
        context = ResolvedContext(
            items=[],
            confidence=0.0,
            method="error",
            source_turn_id=None,
        )
        assert context.method == "error"
        assert context.confidence == 0.0


class TestReferenceResolverInit:
    def test_init_with_no_settings(self):
        """Test initialization without settings uses global settings."""
        resolver = ReferenceResolver()
        assert resolver.settings is not None

    def test_init_with_custom_settings(self):
        """Test initialization with custom settings."""
        from unittest.mock import Mock

        custom_settings = Mock()
        resolver = ReferenceResolver(settings=custom_settings)
        assert resolver.settings is custom_settings


class TestExtractReferences:
    """Tests for extract_references().

    Note: All patterns are now English-only by design (after Semantic Pivot refactoring).
    Multi-language tests have been removed as queries are translated to English
    before reference extraction.
    """

    @pytest.fixture
    def resolver(self):
        """Provide ReferenceResolver instance."""
        return ReferenceResolver()

    # English ordinal tests
    def test_extract_english_first(self, resolver):
        """Test extraction of English 'the first'."""
        refs = resolver.extract_references("show me the first")
        assert len(refs.references) > 0
        assert refs.references[0].type == "ordinal"
        assert refs.references[0].index == 0

    def test_extract_english_second(self, resolver):
        """Test extraction of English 'the second'."""
        refs = resolver.extract_references("send the 2nd email")
        assert len(refs.references) > 0
        assert refs.references[0].index == 1

    def test_extract_english_third(self, resolver):
        """Test extraction of English 'the third'."""
        refs = resolver.extract_references("delete the 3rd item")
        assert len(refs.references) > 0
        assert refs.references[0].index == 2

    def test_extract_english_last(self, resolver):
        """Test extraction of English 'the last'."""
        refs = resolver.extract_references("archive the last one")
        assert len(refs.references) > 0
        assert refs.references[0].index == -1

    def test_extract_english_dynamic_number(self, resolver):
        """Test extraction of English dynamic number 'the 10th'."""
        refs = resolver.extract_references("select the 10th item")
        assert len(refs.references) > 0
        assert refs.references[0].index == 9  # 10th = index 9

    # Demonstrative tests (English only)
    def test_extract_english_demonstrative_this_one(self, resolver):
        """Test extraction of English 'this one'."""
        refs = resolver.extract_references("send this one")
        demonstratives = [r for r in refs.references if r.type == "demonstrative"]
        assert len(demonstratives) > 0

    def test_extract_english_demonstrative_that_one(self, resolver):
        """Test extraction of English 'that one'."""
        refs = resolver.extract_references("delete that one")
        demonstratives = [r for r in refs.references if r.type == "demonstrative"]
        assert len(demonstratives) > 0

    # Comparative tests (English only)
    def test_extract_english_comparative_next(self, resolver):
        """Test extraction of English 'the next'."""
        refs = resolver.extract_references("show the next item")
        comparatives = [r for r in refs.references if r.type == "comparative"]
        assert len(comparatives) > 0

    def test_extract_english_comparative_another(self, resolver):
        """Test extraction of English 'another'."""
        refs = resolver.extract_references("find another contact")
        comparatives = [r for r in refs.references if r.type == "comparative"]
        assert len(comparatives) > 0

    # Edge cases
    def test_extract_no_references(self, resolver):
        """Test query with no references."""
        refs = resolver.extract_references("search for john smith")
        assert len(refs.references) == 0
        assert refs.has_explicit() is False

    def test_extract_case_insensitive(self, resolver):
        """Test that extraction is case-insensitive."""
        refs_lower = resolver.extract_references("the first")
        refs_upper = resolver.extract_references("THE FIRST")
        assert len(refs_lower.references) > 0
        assert len(refs_upper.references) > 0

    def test_extract_multiple_references(self, resolver):
        """Test extraction of multiple references in one query."""
        # Note: Implementation only takes first match per language to avoid duplicates
        refs = resolver.extract_references("send the first and the second")
        # Should have at least 1 reference (first match)
        assert len(refs.references) >= 1


class TestHasReferences:
    @pytest.fixture
    def resolver(self):
        """Provide ReferenceResolver instance."""
        return ReferenceResolver()

    def test_has_references_true(self, resolver):
        """Test has_references() returns True when references exist."""
        assert resolver.has_references("the first") is True

    def test_has_references_false(self, resolver):
        """Test has_references() returns False when no references."""
        assert resolver.has_references("search for contacts") is False


class TestResolveOrdinalToItem:
    @pytest.fixture
    def resolver(self):
        """Provide ReferenceResolver instance."""
        return ReferenceResolver()

    def test_resolve_first_item(self, resolver):
        """Test resolving first item (index 0)."""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        item, confidence = resolver.resolve_ordinal_to_item(0, items)
        assert item == {"id": 1}
        assert confidence == 1.0

    def test_resolve_second_item(self, resolver):
        """Test resolving second item (index 1)."""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        item, confidence = resolver.resolve_ordinal_to_item(1, items)
        assert item == {"id": 2}
        assert confidence == 1.0

    def test_resolve_last_item(self, resolver):
        """Test resolving last item (index -1)."""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        item, confidence = resolver.resolve_ordinal_to_item(-1, items)
        assert item == {"id": 3}
        assert confidence == 1.0

    def test_resolve_empty_candidates(self, resolver):
        """Test resolving with empty candidates list."""
        item, confidence = resolver.resolve_ordinal_to_item(0, [])
        assert item is None
        assert confidence == 0.0

    def test_resolve_out_of_bounds_positive(self, resolver):
        """Test resolving with positive out-of-bounds index."""
        items = [{"id": 1}, {"id": 2}]
        item, confidence = resolver.resolve_ordinal_to_item(5, items)
        assert item is None
        assert confidence == 0.0

    def test_resolve_out_of_bounds_negative(self, resolver):
        """Test resolving with negative out-of-bounds index (< -1)."""
        items = [{"id": 1}, {"id": 2}]
        item, confidence = resolver.resolve_ordinal_to_item(-3, items)
        assert item is None
        assert confidence == 0.0


class TestSingletonPattern:
    def test_get_reference_resolver_returns_instance(self):
        """Test get_reference_resolver() returns ReferenceResolver instance."""
        reset_reference_resolver()  # Start fresh
        resolver = get_reference_resolver()
        assert isinstance(resolver, ReferenceResolver)

    def test_get_reference_resolver_returns_singleton(self):
        """Test get_reference_resolver() returns same instance."""
        reset_reference_resolver()  # Start fresh
        resolver1 = get_reference_resolver()
        resolver2 = get_reference_resolver()
        assert resolver1 is resolver2

    def test_reset_reference_resolver(self):
        """Test reset_reference_resolver() clears singleton."""
        resolver1 = get_reference_resolver()
        reset_reference_resolver()
        resolver2 = get_reference_resolver()
        # After reset, should be different instance
        assert resolver1 is not resolver2


def _ctx(items, *, source_domain=None):
    return ResolvedContext(
        items=items,
        confidence=1.0,
        method="explicit",
        source_turn_id=3,
        source_domain=source_domain,
    )


class TestToDict:
    def test_serializes_all_fields(self):
        ctx = ResolvedContext(
            items=[{"id": 1}],
            confidence=0.8,
            method="explicit",
            source_turn_id=2,
            source_domain="contact",
        )
        assert ctx.to_dict() == {
            "items": [{"id": 1}],
            "confidence": 0.8,
            "method": "explicit",
            "source_turn_id": 2,
            "source_domain": "contact",
        }


class TestToLlmContext:
    """``to_llm_context`` builds the string the planner LLM reads to resolve a
    follow-up ("the first one", "that email") without inventing a resolve step.
    A regression yields empty/malformed context and the LLM re-fetches or
    resolves the wrong item — silently, since nothing raises."""

    def test_empty_items_returns_empty_string(self):
        assert _ctx([]).to_llm_context() == ""

    def test_single_item_header_and_fields(self):
        out = _ctx(
            [
                {
                    "name": "Jean Dupont",
                    "email": "jean@example.com",
                    "meta": {"internal": 1},  # excluded field
                    "_hidden": "secret",  # underscore-prefixed → dropped
                    "note": "visible extra",  # non-priority → sorted section
                }
            ],
            source_domain="contact",
        ).to_llm_context()

        assert "RESOLVED CONTEXT" in out
        assert "Source domain: contact" in out
        assert "Items count: 1" in out
        assert "- name: Jean Dupont" in out
        assert "- email: jean@example.com" in out
        assert "- note: visible extra" in out
        # Priority ordering: name (priority idx 4) before email (idx 14).
        assert out.index("- name:") < out.index("- email:")
        # Excluded / internal fields never leak.
        assert "- meta:" not in out
        assert "_hidden" not in out
        # Always-present closing directive.
        assert "CRITICAL:" in out

    def test_single_item_extracts_ready_to_use_values(self):
        out = _ctx(
            [{"name": "Jean", "email": "jean@example.com"}],
            source_domain="contact",
        ).to_llm_context()

        assert "READY-TO-USE VALUES" in out
        assert "get_contacts_tool" in out  # name → contacts hint
        assert "get_emails_tool" in out  # email → emails hint

    def test_single_item_location_ready_to_use_hint(self):
        out = _ctx(
            [{"location": "Tour Eiffel, Paris"}],
            source_domain="place",
        ).to_llm_context()

        assert 'LOCATION: "Tour Eiffel, Paris"' in out
        assert 'get_places_tool(query="Tour Eiffel, Paris")' in out

    def test_multiple_items_have_no_ready_to_use_section(self):
        """READY-TO-USE extraction is intentionally single-item only (ambiguous
        otherwise)."""
        out = _ctx(
            [{"name": "A"}, {"name": "B"}],
            source_domain="contact",
        ).to_llm_context()

        assert "Items count: 2" in out
        assert "Item 1:" in out
        assert "Item 2:" in out
        assert "READY-TO-USE VALUES" not in out

    def test_id_alias_injected_for_known_domain(self):
        """The payload carries ``id`` but ``update_event_tool`` expects
        ``event_id`` — the alias line maps it so the LLM uses the value directly
        instead of inventing a $steps reference."""
        out = _ctx(
            [{"id": "evt_123", "summary": "Standup"}],
            source_domain="event",
        ).to_llm_context()

        assert "event_id: evt_123" in out
        assert "use this directly as tool parameter" in out

    def test_id_alias_not_injected_when_param_already_present(self):
        out = _ctx(
            [{"id": "evt_123", "event_id": "evt_123", "summary": "Standup"}],
            source_domain="event",
        ).to_llm_context()

        # No alias hint line when the tool-param field is already in the payload.
        assert "use this directly as tool parameter" not in out

    def test_non_dict_item_is_stringified(self):
        out = _ctx(["a plain resolved string"]).to_llm_context()
        assert "a plain resolved string" in out
        assert "Source domain: unknown" in out  # None → 'unknown'


class TestFormatValue:
    @pytest.fixture
    def fmt(self):
        return _ctx([])._format_value

    def test_none_returns_none(self, fmt):
        assert fmt(None) is None

    def test_dict_prefers_formatted(self, fmt):
        assert fmt({"formatted": "Jan 5, 09:00", "dateTime": "2026-01-05T09:00:00Z"}) == (
            "Jan 5, 09:00"
        )

    def test_dict_datetime_when_no_formatted(self, fmt):
        assert fmt({"dateTime": "2026-01-05T09:00:00Z"}) == "2026-01-05T09:00:00Z"

    def test_dict_display_name(self, fmt):
        assert fmt({"displayName": "Jean Dupont"}) == "Jean Dupont"

    def test_dict_email(self, fmt):
        assert fmt({"email": "a@b.co"}) == "a@b.co"

    def test_small_dict_as_json(self, fmt):
        assert fmt({"a": 1, "b": 2}) == '{"a": 1, "b": 2}'

    def test_large_dict_summarized(self, fmt):
        assert fmt({"a": 1, "b": 2, "c": 3, "d": 4}) == "{...4 fields}"

    def test_short_list(self, fmt):
        assert fmt([1, 2, 3]) == "[1, 2, 3]"

    def test_empty_list_returns_none(self, fmt):
        assert fmt([]) is None

    def test_long_list_summarized(self, fmt):
        assert fmt([1, 2, 3, 4, 5]) == "[1, 2, ... +3 more]"

    def test_long_string_is_truncated(self, fmt):
        result = fmt("x" * 250)
        assert result is not None
        assert result.endswith("...")
        assert len(result) == 203  # 200 chars + "..."

    def test_null_like_strings_return_none(self, fmt):
        assert fmt("None") is None
        assert fmt("null") is None
        assert fmt("") is None

    def test_zero_is_kept_not_dropped(self, fmt):
        """Integer 0 is a real value, not emptiness — it must survive."""
        assert fmt(0) == "0"

    def test_primitive_int(self, fmt):
        assert fmt(42) == "42"
