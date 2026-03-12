"""
Unit tests for Manifest Helpers utilities.

Tests for utility functions that help with tool manifest management,
including compact example formatting for LLM prompts.
"""

import pytest

from src.domains.agents.registry.manifest_helpers import (
    _format_minimal,
    _format_structured,
    _summarize_output,
    enrich_description_with_examples,
    format_compact_examples,
)


class TestSummarizeOutput:
    """Tests for _summarize_output() helper."""

    def test_summarize_empty_list(self):
        """Test summarizing empty list."""
        result = _summarize_output({"items": []})
        assert result == "items=[]"

    def test_summarize_single_item_list_with_dict(self):
        """Test summarizing single-item list with dict."""
        result = _summarize_output({"items": [{"id": "1", "name": "John", "email": "j@e.com"}]})
        assert "items=" in result
        assert "id" in result
        assert "name" in result

    def test_summarize_single_item_list_with_primitive(self):
        """Test summarizing single-item list with primitive."""
        result = _summarize_output({"items": ["hello"]})
        assert result == "items=[hello]"

    def test_summarize_multi_item_list(self):
        """Test summarizing multi-item list."""
        result = _summarize_output({"items": [1, 2, 3, 4, 5]})
        assert "items=[5 items]" in result

    def test_summarize_dict_shows_first_3_keys(self):
        """Test summarizing dict shows first 3 keys."""
        result = _summarize_output(
            {"data": {"key1": "v1", "key2": "v2", "key3": "v3", "key4": "v4"}}
        )
        assert "data=" in result
        assert "key1" in result
        assert "key2" in result
        assert "key3" in result

    def test_summarize_short_string(self):
        """Test summarizing short string."""
        result = _summarize_output({"message": "Hello world"})
        assert result == "message='Hello world'"

    def test_summarize_long_string_truncates(self):
        """Test summarizing long string truncates at 27 chars."""
        long_string = "A" * 50
        result = _summarize_output({"message": long_string})
        assert "..." in result
        assert len(result) < len(f"message='{long_string}'")

    def test_summarize_integer(self):
        """Test summarizing integer."""
        result = _summarize_output({"count": 42})
        assert result == "count=42"

    def test_summarize_float(self):
        """Test summarizing float."""
        result = _summarize_output({"score": 0.95})
        assert result == "score=0.95"

    def test_summarize_boolean(self):
        """Test summarizing boolean."""
        result = _summarize_output({"active": True})
        assert result == "active=True"

    def test_summarize_multiple_fields(self):
        """Test summarizing multiple fields."""
        result = _summarize_output(
            {
                "items": [{"id": 1}],
                "total": 1,
                "status": "ok",
            }
        )
        assert "items=" in result
        assert "total=1" in result
        assert "status='ok'" in result

    def test_summarize_unknown_type(self):
        """Test summarizing unknown type shows type name."""

        class CustomType:
            pass

        result = _summarize_output({"obj": CustomType()})
        assert "obj=CustomType" in result


class TestFormatMinimal:
    """Tests for _format_minimal() helper."""

    def test_format_minimal_simple_example(self):
        """Test minimal format with simple example."""
        examples = [
            {
                "input": {"query": "john"},
                "output": {"total": 1},
            }
        ]
        result = _format_minimal(examples)
        assert "**Examples**:" in result
        assert "query='john'" in result
        assert "total=1" in result
        assert "•" in result  # Bullet point

    def test_format_minimal_multiple_inputs(self):
        """Test minimal format with multiple input params."""
        examples = [
            {
                "input": {"query": "john", "limit": 10},
                "output": {"total": 1},
            }
        ]
        result = _format_minimal(examples)
        assert "query='john'" in result
        assert "limit=10" in result

    def test_format_minimal_list_input(self):
        """Test minimal format with list input."""
        examples = [
            {
                "input": {"ids": [1, 2, 3]},
                "output": {"success": True},
            }
        ]
        result = _format_minimal(examples)
        assert "ids=[3 items]" in result

    def test_format_minimal_dict_input(self):
        """Test minimal format with dict input."""
        examples = [
            {
                "input": {"filter": {"key": "value"}},
                "output": {"success": True},
            }
        ]
        result = _format_minimal(examples)
        assert "filter={...}" in result

    def test_format_minimal_boolean_input(self):
        """Test minimal format with boolean input."""
        examples = [
            {
                "input": {"active": True},
                "output": {"count": 5},
            }
        ]
        result = _format_minimal(examples)
        assert "active=True" in result

    def test_format_minimal_multiple_examples(self):
        """Test minimal format with multiple examples."""
        examples = [
            {"input": {"query": "john"}, "output": {"total": 1}},
            {"input": {"query": "jane"}, "output": {"total": 2}},
        ]
        result = _format_minimal(examples)
        lines = result.split("\n")
        # Header + 2 examples
        assert len(lines) == 3
        assert "john" in lines[1]
        assert "jane" in lines[2]


class TestFormatStructured:
    """Tests for _format_structured() helper."""

    def test_format_structured_simple_example(self):
        """Test structured format with simple example."""
        examples = [
            {
                "input": {"query": "john"},
                "output": {"total": 1},
            }
        ]
        result = _format_structured(examples)
        assert "**Examples**:" in result
        assert "1. Example 1:" in result
        assert "Input:" in result
        assert "Output:" in result

    def test_format_structured_with_description(self):
        """Test structured format uses description."""
        examples = [
            {
                "description": "Search by name",
                "input": {"query": "john"},
                "output": {"total": 1},
            }
        ]
        result = _format_structured(examples)
        assert "1. Search by name:" in result

    def test_format_structured_multiple_examples(self):
        """Test structured format with multiple examples."""
        examples = [
            {"description": "First example", "input": {"a": 1}, "output": {"b": 2}},
            {"description": "Second example", "input": {"c": 3}, "output": {"d": 4}},
        ]
        result = _format_structured(examples)
        assert "1. First example:" in result
        assert "2. Second example:" in result


class TestFormatCompactExamples:
    """Tests for format_compact_examples() main function."""

    def test_empty_examples_returns_empty(self):
        """Test that empty examples returns empty string."""
        result = format_compact_examples([])
        assert result == ""

    def test_default_max_examples_is_2(self):
        """Test that default max_examples is 2."""
        examples = [
            {"input": {"a": 1}, "output": {"b": 1}},
            {"input": {"a": 2}, "output": {"b": 2}},
            {"input": {"a": 3}, "output": {"b": 3}},
        ]
        result = format_compact_examples(examples)
        # Should only include 2 examples
        lines = [line for line in result.split("\n") if line.startswith("•")]
        assert len(lines) == 2

    def test_custom_max_examples(self):
        """Test custom max_examples limit."""
        examples = [{"input": {"a": i}, "output": {"b": i}} for i in range(5)]
        result = format_compact_examples(examples, max_examples=3)
        lines = [line for line in result.split("\n") if line.startswith("•")]
        assert len(lines) == 3

    def test_minimal_format_style(self):
        """Test minimal format style."""
        examples = [{"input": {"q": "test"}, "output": {"r": 1}}]
        result = format_compact_examples(examples, format_style="minimal")
        assert "•" in result

    def test_structured_format_style(self):
        """Test structured format style."""
        examples = [{"input": {"q": "test"}, "output": {"r": 1}}]
        result = format_compact_examples(examples, format_style="structured")
        assert "Input:" in result
        assert "Output:" in result

    def test_unknown_format_style_raises(self):
        """Test unknown format style raises ValueError."""
        examples = [{"input": {"q": "test"}, "output": {"r": 1}}]
        with pytest.raises(ValueError) as exc_info:
            format_compact_examples(examples, format_style="unknown")
        assert "unknown format_style" in str(exc_info.value).lower()


class TestEnrichDescriptionWithExamples:
    """Tests for enrich_description_with_examples() function."""

    def test_empty_examples_returns_base_description(self):
        """Test that empty examples returns base description unchanged."""
        result = enrich_description_with_examples("Search contacts.", [])
        assert result == "Search contacts."

    def test_adds_examples_to_description(self):
        """Test that examples are appended to description."""
        examples = [{"input": {"query": "john"}, "output": {"total": 1}}]
        result = enrich_description_with_examples("Search contacts.", examples)
        assert result.startswith("Search contacts.")
        assert "**Examples**:" in result
        assert "john" in result

    def test_preserves_spacing(self):
        """Test that proper spacing is added between description and examples."""
        examples = [{"input": {"q": "x"}, "output": {"r": 1}}]
        result = enrich_description_with_examples("Description.", examples)
        assert "\n\n" in result  # Double newline between description and examples

    def test_respects_max_examples(self):
        """Test that max_examples is respected."""
        examples = [{"input": {"a": i}, "output": {"b": i}} for i in range(5)]
        result = enrich_description_with_examples("Desc.", examples, max_examples=1)
        lines = [line for line in result.split("\n") if line.startswith("•")]
        assert len(lines) == 1

    def test_respects_format_style(self):
        """Test that format_style is respected."""
        examples = [{"input": {"q": "test"}, "output": {"r": 1}}]
        result = enrich_description_with_examples("Desc.", examples, format_style="structured")
        assert "Input:" in result
        assert "Output:" in result


class TestIntegration:
    """Integration tests for realistic scenarios."""

    def test_contact_search_example(self):
        """Test formatting contact search examples."""
        examples = [
            {
                "description": "Search by name",
                "input": {"query": "john", "max_results": 5},
                "output": {
                    "contacts": [{"name": "John Doe", "email": "john@example.com"}],
                    "total": 1,
                },
            },
            {
                "description": "Search all",
                "input": {"query": "", "max_results": 10},
                "output": {
                    "contacts": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
                    "total": 3,
                },
            },
        ]

        # Test minimal format
        minimal = format_compact_examples(examples, format_style="minimal")
        assert "query='john'" in minimal
        assert "max_results=5" in minimal

        # Test structured format
        structured = format_compact_examples(examples, format_style="structured")
        assert "Search by name:" in structured
        assert "Search all:" in structured

    def test_enriched_tool_description(self):
        """Test enriching a complete tool description."""
        base_desc = (
            "Search contacts by name, email, or phone number. "
            "Returns a list of matching contacts with their details."
        )
        examples = [
            {
                "input": {"query": "john smith"},
                "output": {"contacts": [{"name": "John Smith"}], "total": 1},
            }
        ]

        enriched = enrich_description_with_examples(base_desc, examples)

        # Base description preserved
        assert "Search contacts by name" in enriched
        # Examples added
        assert "**Examples**:" in enriched
        assert "john smith" in enriched
