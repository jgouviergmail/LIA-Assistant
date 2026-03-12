"""
Tests for FOR_EACH utilities module.

Tests the shared patterns and helper functions used by
dependency_graph.py and parallel_executor.py.
"""

from src.domains.agents.orchestration.for_each_utils import (
    PATTERN_DOLLAR_STEPS,
    PATTERN_FOR_EACH_PROVIDER,
    PATTERN_FOR_EACH_REF,
    PATTERN_ITEM_REF,
    PATTERN_JINJA_STEPS,
    count_items_at_path,
    extract_step_references,
    get_for_each_provider_step_id,
    parse_for_each_reference,
)


class TestPatternForEachRef:
    """Tests for PATTERN_FOR_EACH_REF regex pattern."""

    def test_simple_reference(self) -> None:
        """Test simple step reference parsing."""
        match = PATTERN_FOR_EACH_REF.match("$steps.step_1.places")
        assert match is not None
        assert match.group(1) == "step_1"
        assert match.group(2) == "places"

    def test_nested_field_path(self) -> None:
        """Test reference with nested field path."""
        match = PATTERN_FOR_EACH_REF.match("$steps.get_data.data.items")
        assert match is not None
        assert match.group(1) == "get_data"
        assert match.group(2) == "data.items"

    def test_array_wildcard_suffix(self) -> None:
        """Test reference with [*] wildcard suffix."""
        match = PATTERN_FOR_EACH_REF.match("$steps.search.contacts[*]")
        assert match is not None
        assert match.group(1) == "search"
        assert match.group(2) == "contacts"

    def test_invalid_reference_no_match(self) -> None:
        """Test invalid references don't match."""
        assert PATTERN_FOR_EACH_REF.match("invalid") is None
        assert PATTERN_FOR_EACH_REF.match("$step.foo.bar") is None  # Missing 's'
        assert PATTERN_FOR_EACH_REF.match("steps.foo.bar") is None  # Missing '$'


class TestPatternForEachProvider:
    """Tests for PATTERN_FOR_EACH_PROVIDER regex pattern."""

    def test_extracts_step_id(self) -> None:
        """Test step_id extraction."""
        match = PATTERN_FOR_EACH_PROVIDER.match("$steps.step_1.places")
        assert match is not None
        assert match.group(1) == "step_1"

    def test_works_with_long_paths(self) -> None:
        """Test with longer field paths."""
        match = PATTERN_FOR_EACH_PROVIDER.match("$steps.get_contacts.data.contacts[0]")
        assert match is not None
        assert match.group(1) == "get_contacts"


class TestPatternDollarSteps:
    """Tests for PATTERN_DOLLAR_STEPS regex pattern."""

    def test_with_dot_accessor(self) -> None:
        """Test pattern with dot accessor."""
        matches = PATTERN_DOLLAR_STEPS.findall("$steps.search.contacts")
        assert matches == ["search"]

    def test_with_bracket_accessor(self) -> None:
        """Test pattern with bracket accessor."""
        matches = PATTERN_DOLLAR_STEPS.findall("$steps.search[0]")
        assert matches == ["search"]

    def test_multiple_references(self) -> None:
        """Test multiple references in same string."""
        expr = "$steps.a.x > $steps.b.y"
        matches = PATTERN_DOLLAR_STEPS.findall(expr)
        assert set(matches) == {"a", "b"}


class TestPatternJinjaSteps:
    """Tests for PATTERN_JINJA_STEPS regex pattern."""

    def test_jinja_for_loop(self) -> None:
        """Test Jinja for loop reference."""
        template = "{% for g in steps.group.groups %}"
        matches = PATTERN_JINJA_STEPS.findall(template)
        assert matches == ["group"]

    def test_jinja_expression(self) -> None:
        """Test Jinja expression reference."""
        template = "{{ steps.data.value }}"
        matches = PATTERN_JINJA_STEPS.findall(template)
        assert matches == ["data"]

    def test_does_not_match_dollar_steps(self) -> None:
        """Test that $steps doesn't match (negative lookbehind)."""
        expr = "$steps.search.contacts"
        matches = PATTERN_JINJA_STEPS.findall(expr)
        assert matches == []


class TestPatternItemRef:
    """Tests for PATTERN_ITEM_REF regex pattern."""

    def test_simple_item(self) -> None:
        """Test simple $item reference."""
        matches = PATTERN_ITEM_REF.findall("$item")
        assert matches == ["$item"]

    def test_item_with_field(self) -> None:
        """Test $item.field reference."""
        matches = PATTERN_ITEM_REF.findall("$item.email")
        assert matches == ["$item.email"]

    def test_item_with_nested_field(self) -> None:
        """Test $item.field.subfield reference."""
        matches = PATTERN_ITEM_REF.findall("$item.contact.email")
        assert matches == ["$item.contact.email"]

    def test_item_with_index_in_field(self) -> None:
        """Test $item.field[0] reference (index must be after dot)."""
        matches = PATTERN_ITEM_REF.findall("$item.contacts[0]")
        assert matches == ["$item.contacts[0]"]

    def test_direct_index_captures_base_only(self) -> None:
        """Test $item[0] captures only $item (regex requires dot before index)."""
        # The pattern requires a dot before any segment, so $item[0] only captures $item
        matches = PATTERN_ITEM_REF.findall("$item[0]")
        assert matches == ["$item"]


class TestParseForEachReference:
    """Tests for parse_for_each_reference function."""

    def test_simple_reference(self) -> None:
        """Test parsing simple reference."""
        step_id, field_path = parse_for_each_reference("$steps.step_1.places")
        assert step_id == "step_1"
        assert field_path == "places"

    def test_nested_field_path(self) -> None:
        """Test parsing nested field path."""
        step_id, field_path = parse_for_each_reference("$steps.get_events.events")
        assert step_id == "get_events"
        assert field_path == "events"

    def test_with_wildcard(self) -> None:
        """Test parsing reference with [*] suffix."""
        step_id, field_path = parse_for_each_reference("$steps.search.contacts[*]")
        assert step_id == "search"
        assert field_path == "contacts"

    def test_invalid_returns_none(self) -> None:
        """Test invalid reference returns None tuple."""
        step_id, field_path = parse_for_each_reference("invalid")
        assert step_id is None
        assert field_path is None

    def test_empty_string(self) -> None:
        """Test empty string returns None tuple."""
        step_id, field_path = parse_for_each_reference("")
        assert step_id is None
        assert field_path is None


class TestGetForEachProviderStepId:
    """Tests for get_for_each_provider_step_id function."""

    def test_extracts_step_id(self) -> None:
        """Test extraction of step_id."""
        result = get_for_each_provider_step_id("$steps.step_1.places")
        assert result == "step_1"

    def test_complex_step_id(self) -> None:
        """Test with underscores in step_id."""
        result = get_for_each_provider_step_id("$steps.get_contacts_v2.contacts")
        assert result == "get_contacts_v2"

    def test_invalid_returns_none(self) -> None:
        """Test invalid reference returns None."""
        assert get_for_each_provider_step_id("invalid") is None
        assert get_for_each_provider_step_id("steps.foo.bar") is None
        assert get_for_each_provider_step_id("") is None


class TestExtractStepReferences:
    """Tests for extract_step_references function."""

    def test_single_dollar_reference(self) -> None:
        """Test extraction of single $steps reference."""
        refs = extract_step_references("$steps.search.contacts[0].email")
        assert refs == {"search"}

    def test_multiple_dollar_references(self) -> None:
        """Test extraction of multiple $steps references."""
        refs = extract_step_references("$steps.a.x > $steps.b.y")
        assert refs == {"a", "b"}

    def test_jinja_reference(self) -> None:
        """Test extraction of Jinja template reference."""
        refs = extract_step_references("{% for g in steps.group.groups %}")
        assert refs == {"group"}

    def test_mixed_references(self) -> None:
        """Test extraction of mixed $steps and Jinja references."""
        expr = "$steps.a.x and {{ steps.b.y }}"
        refs = extract_step_references(expr)
        assert refs == {"a", "b"}

    def test_no_references(self) -> None:
        """Test empty set when no references."""
        refs = extract_step_references("just some text")
        assert refs == set()

    def test_empty_string(self) -> None:
        """Test empty string returns empty set."""
        refs = extract_step_references("")
        assert refs == set()


class TestCountItemsAtPath:
    """Tests for count_items_at_path function."""

    def test_simple_list_path(self) -> None:
        """Test counting items in a simple list."""
        data = {"events": [1, 2, 3]}
        assert count_items_at_path(data, "events") == 3

    def test_nested_list_path(self) -> None:
        """Test counting items in a nested list."""
        data = {"data": {"items": [1, 2]}}
        assert count_items_at_path(data, "data.items") == 2

    def test_deeply_nested_path(self) -> None:
        """Test counting items in a deeply nested structure."""
        data = {"response": {"results": {"contacts": ["a", "b", "c", "d"]}}}
        assert count_items_at_path(data, "response.results.contacts") == 4

    def test_non_existent_path(self) -> None:
        """Test returns 0 for non-existent path."""
        data = {"other": []}
        assert count_items_at_path(data, "events") == 0

    def test_empty_list(self) -> None:
        """Test returns 0 for empty list."""
        data = {"events": []}
        assert count_items_at_path(data, "events") == 0

    def test_none_value_at_path(self) -> None:
        """Test returns 0 for None value at path."""
        data = {"events": None}
        assert count_items_at_path(data, "events") == 0

    def test_scalar_value_at_path(self) -> None:
        """Test returns 1 for non-empty scalar value."""
        data = {"count": 42}
        assert count_items_at_path(data, "count") == 1

    def test_string_value_at_path(self) -> None:
        """Test returns 1 for non-empty string value."""
        data = {"name": "John"}
        assert count_items_at_path(data, "name") == 1

    def test_dict_value_at_path(self) -> None:
        """Test returns 1 for non-empty dict value."""
        data = {"contact": {"name": "John", "email": "john@example.com"}}
        assert count_items_at_path(data, "contact") == 1

    def test_empty_dict_at_path(self) -> None:
        """Test returns 0 for empty dict at path."""
        data = {"contact": {}}
        assert count_items_at_path(data, "contact") == 0

    def test_false_value_at_path(self) -> None:
        """Test returns 0 for False boolean value."""
        data = {"active": False}
        assert count_items_at_path(data, "active") == 0

    def test_true_value_at_path(self) -> None:
        """Test returns 1 for True boolean value."""
        data = {"active": True}
        assert count_items_at_path(data, "active") == 1

    def test_zero_value_at_path(self) -> None:
        """Test returns 0 for zero numeric value."""
        data = {"count": 0}
        assert count_items_at_path(data, "count") == 0

    def test_partial_path_exists(self) -> None:
        """Test returns 0 when path is only partially valid."""
        data = {"data": {"other": []}}
        assert count_items_at_path(data, "data.items") == 0

    def test_path_through_non_dict(self) -> None:
        """Test returns 0 when path goes through non-dict."""
        data = {"data": [1, 2, 3]}
        assert count_items_at_path(data, "data.items") == 0

    def test_empty_data(self) -> None:
        """Test returns 0 for empty data dict."""
        assert count_items_at_path({}, "events") == 0

    def test_empty_path(self) -> None:
        """Test returns 0 for empty path."""
        data = {"events": [1, 2, 3]}
        # Empty path would try to get "" key, which doesn't exist
        assert count_items_at_path(data, "") == 0

    def test_list_of_dicts(self) -> None:
        """Test counting list of dict items."""
        data = {
            "contacts": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ]
        }
        assert count_items_at_path(data, "contacts") == 2

    def test_exception_handling(self) -> None:
        """Test graceful handling of unexpected errors."""
        # Pass something that might cause issues
        data = {"nested": {"key": object()}}  # Non-standard object
        # Should return 0 or 1, not raise
        result = count_items_at_path(data, "nested.key")
        assert result in (0, 1)
