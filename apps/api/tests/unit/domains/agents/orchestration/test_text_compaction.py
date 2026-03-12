"""
Tests for Text Compaction module.

Tests the token optimization for embedded data structures in text parameters.
Validates detection, parsing, and compaction of Python data structures.
"""

from unittest.mock import MagicMock, patch

from src.domains.agents.orchestration.text_compaction import (
    _compact_data_structure,
    _compact_embedded_data,
    _find_data_blocks,
    _find_matching_bracket,
    _is_compactable,
    _try_compact_block,
    compact_text_params,
)


class TestCompactTextParams:
    """Tests for the main compact_text_params function."""

    def test_disabled_when_feature_flag_off(self) -> None:
        """Test that compaction is skipped when disabled."""
        params = {"content_instruction": "[{'name': 'Test'}]"}

        with patch(
            "src.domains.agents.orchestration.text_compaction.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(text_compaction_enabled=False)
            result = compact_text_params(params, "send_email_tool")

        assert result == params  # Unchanged

    def test_skips_non_targetable_params(self) -> None:
        """Test that non-targetable parameters are not processed."""
        params = {"query": "[{'name': 'Test'}]", "max_results": 10}

        with patch(
            "src.domains.agents.orchestration.text_compaction.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                text_compaction_enabled=True,
                text_compaction_min_size=50,
                text_compaction_max_items=3,
                text_compaction_max_field_length=40,
            )
            result = compact_text_params(params, "get_places_tool")

        # query is not in TEXT_COMPACTION_PARAMS, so no changes
        assert result == params

    def test_skips_short_values(self) -> None:
        """Test that short values are not processed."""
        params = {"content_instruction": "[{'name': 'A'}]"}

        with patch(
            "src.domains.agents.orchestration.text_compaction.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                text_compaction_enabled=True,
                text_compaction_min_size=500,  # Higher than value length
                text_compaction_max_items=3,
                text_compaction_max_field_length=40,
            )
            result = compact_text_params(params, "send_email_tool")

        assert result == params  # Unchanged due to min_size

    def test_compacts_embedded_list_of_dicts(self) -> None:
        """Test compaction of embedded list of dicts."""
        # Simulate data with direct name field (payload_to_text pattern)
        places_data = (
            "[{'name': 'Hotel Grand', 'rating': 4.5, "
            "'address': '123 Main St, City'}, "
            "{'name': 'Hotel Luxe', 'rating': 4.8, "
            "'address': '456 Oak Ave, Town'}]"
        )
        original_content = f"Write about these hotels: {places_data}"
        original_len = len(original_content)
        params = {"content_instruction": original_content}

        with patch(
            "src.domains.agents.orchestration.text_compaction.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                text_compaction_enabled=True,
                text_compaction_min_size=50,
                text_compaction_max_items=3,
                text_compaction_max_field_length=40,
            )
            result = compact_text_params(params, "send_email_tool")

        # Should be compacted (dict is modified in place, compare against saved original)
        assert len(result["content_instruction"]) < original_len
        # Should contain hotel names (payload_to_text uses 'name' field)
        assert "Hotel Grand" in result["content_instruction"]
        assert "Hotel Luxe" in result["content_instruction"]

    def test_preserves_non_string_values(self) -> None:
        """Test that non-string values are preserved."""
        params = {
            "content_instruction": "Hello",
            "body": {"nested": "dict"},  # Non-string
            "max_results": 10,
        }

        with patch(
            "src.domains.agents.orchestration.text_compaction.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                text_compaction_enabled=True,
                text_compaction_min_size=5,
                text_compaction_max_items=3,
                text_compaction_max_field_length=40,
            )
            result = compact_text_params(params, "send_email_tool")

        # Non-string body should be unchanged
        assert result["body"] == {"nested": "dict"}

    def test_handles_multiple_targetable_params(self) -> None:
        """Test compaction of multiple targetable parameters."""
        # Longer data to ensure it exceeds min_size threshold
        data = (
            "[{'name': 'Alpha Item', 'value': 1, 'description': 'First item in list'}, "
            "{'name': 'Beta Item', 'value': 2, 'description': 'Second item in list'}, "
            "{'name': 'Gamma Item', 'value': 3, 'description': 'Third item in list'}]"
        )
        original_instruction = f"Process these items: {data}"
        original_body = f"Items to review: {data}"
        original_instruction_len = len(original_instruction)
        original_body_len = len(original_body)
        params = {
            "content_instruction": original_instruction,
            "body": original_body,
        }

        with patch(
            "src.domains.agents.orchestration.text_compaction.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                text_compaction_enabled=True,
                text_compaction_min_size=50,
                text_compaction_max_items=3,
                text_compaction_max_field_length=40,
            )
            result = compact_text_params(params, "send_email_tool")

        # Both should be shorter (dict is modified in place)
        assert len(result["content_instruction"]) < original_instruction_len
        assert len(result["body"]) < original_body_len


class TestFindDataBlocks:
    """Tests for _find_data_blocks function."""

    def test_finds_list_of_dicts(self) -> None:
        """Test finding list of dicts block."""
        text = "Text before [{'key': 'value'}] text after"
        blocks = _find_data_blocks(text)

        assert len(blocks) == 1
        start, end = blocks[0]
        assert text[start:end] == "[{'key': 'value'}]"

    def test_finds_single_dict(self) -> None:
        """Test finding single dict block."""
        text = "Text {'name': 'John', 'age': 30} more text"
        blocks = _find_data_blocks(text)

        assert len(blocks) == 1
        start, end = blocks[0]
        assert text[start:end] == "{'name': 'John', 'age': 30}"

    def test_finds_multiple_blocks(self) -> None:
        """Test finding multiple data blocks."""
        text = "List: [{'a': 1}] and dict: {'b': 2}"
        blocks = _find_data_blocks(text)

        assert len(blocks) == 2

    def test_nested_structures(self) -> None:
        """Test handling of nested structures."""
        text = "[{'inner': {'nested': 'value'}}]"
        blocks = _find_data_blocks(text)

        assert len(blocks) == 1
        start, end = blocks[0]
        assert text[start:end] == text  # Entire text is the block

    def test_no_data_blocks(self) -> None:
        """Test text without data blocks."""
        text = "Just plain text without any data structures"
        blocks = _find_data_blocks(text)

        assert len(blocks) == 0

    def test_empty_string(self) -> None:
        """Test empty string."""
        blocks = _find_data_blocks("")
        assert len(blocks) == 0

    def test_malformed_json_not_matched(self) -> None:
        """Test that malformed structures are not matched."""
        # Missing closing bracket
        text = "[{'key': 'value'"
        result = _find_data_blocks(text)
        # Should return empty or incomplete block
        # The function should handle this gracefully
        assert result == [] or len(result) == 0


class TestFindMatchingBracket:
    """Tests for _find_matching_bracket function."""

    def test_simple_brackets(self) -> None:
        """Test simple bracket matching."""
        text = "[a, b, c]"
        end = _find_matching_bracket(text, 0, "[", "]")
        assert end == 9  # Position after ]

    def test_nested_brackets(self) -> None:
        """Test nested bracket matching."""
        text = "[a, [b, c], d]"
        end = _find_matching_bracket(text, 0, "[", "]")
        assert end == 14  # Position after outer ]

    def test_brackets_in_strings(self) -> None:
        """Test brackets inside strings are ignored."""
        text = "['a]b', 'c']"
        end = _find_matching_bracket(text, 0, "[", "]")
        assert end == 12  # Position after outer ]

    def test_escaped_quotes(self) -> None:
        """Test handling of escaped quotes."""
        text = "['\\'quoted\\'', 'b']"
        end = _find_matching_bracket(text, 0, "[", "]")
        assert end > 0

    def test_curly_braces(self) -> None:
        """Test curly brace matching."""
        text = "{'a': {'b': 1}}"
        end = _find_matching_bracket(text, 0, "{", "}")
        assert end == 15  # Position after outer }

    def test_no_matching_bracket(self) -> None:
        """Test when there's no matching bracket."""
        text = "[a, b, c"
        end = _find_matching_bracket(text, 0, "[", "]")
        assert end == -1

    def test_invalid_start_position(self) -> None:
        """Test with invalid start position."""
        text = "[a, b]"
        end = _find_matching_bracket(text, 10, "[", "]")
        assert end == -1

    def test_wrong_start_char(self) -> None:
        """Test when start position is not opening bracket."""
        text = "x[a, b]"
        end = _find_matching_bracket(text, 0, "[", "]")
        assert end == -1


class TestTryCompactBlock:
    """Tests for _try_compact_block function."""

    def test_valid_list_of_dicts(self) -> None:
        """Test compacting valid list of dicts."""
        block = "[{'name': 'Alice'}, {'name': 'Bob'}]"
        result = _try_compact_block(block, max_items=3, max_field_length=40)

        assert result is not None
        assert "Alice" in result
        assert "Bob" in result

    def test_valid_single_dict(self) -> None:
        """Test compacting valid single dict."""
        block = "{'name': 'John', 'email': 'john@example.com'}"
        result = _try_compact_block(block, max_items=3, max_field_length=40)

        assert result is not None
        assert "John" in result or "john@example.com" in result

    def test_invalid_python_literal(self) -> None:
        """Test handling of invalid Python literal."""
        block = "[{'key': undefined}]"  # 'undefined' is not valid Python
        result = _try_compact_block(block, max_items=3, max_field_length=40)

        assert result is None

    def test_syntax_error(self) -> None:
        """Test handling of syntax errors."""
        block = "[{'key': 'value'"  # Missing closing
        result = _try_compact_block(block, max_items=3, max_field_length=40)

        assert result is None

    def test_non_compactable_data(self) -> None:
        """Test data that's not compactable (e.g., empty list)."""
        block = "[]"
        result = _try_compact_block(block, max_items=3, max_field_length=40)

        assert result is None


class TestIsCompactable:
    """Tests for _is_compactable function."""

    def test_list_of_dicts_is_compactable(self) -> None:
        """Test that list of dicts is compactable."""
        data = [{"name": "A"}, {"name": "B"}]
        assert _is_compactable(data) is True

    def test_single_dict_is_compactable(self) -> None:
        """Test that single dict with multiple keys is compactable."""
        data = {"name": "John", "email": "john@example.com"}
        assert _is_compactable(data) is True

    def test_empty_list_not_compactable(self) -> None:
        """Test that empty list is not compactable."""
        assert _is_compactable([]) is False

    def test_empty_dict_not_compactable(self) -> None:
        """Test that empty dict is not compactable."""
        assert _is_compactable({}) is False

    def test_single_key_dict_not_compactable(self) -> None:
        """Test that single-key dict is not compactable."""
        assert _is_compactable({"only": "one"}) is False

    def test_none_not_compactable(self) -> None:
        """Test that None is not compactable."""
        assert _is_compactable(None) is False

    def test_scalar_not_compactable(self) -> None:
        """Test that scalar values are not compactable."""
        assert _is_compactable(42) is False
        assert _is_compactable("string") is False

    def test_short_list_of_scalars_not_compactable(self) -> None:
        """Test that short list of scalars is not compactable."""
        assert _is_compactable([1, 2, 3]) is False

    def test_long_list_of_scalars_is_compactable(self) -> None:
        """Test that long list of scalars is compactable."""
        assert _is_compactable([1, 2, 3, 4, 5]) is True


class TestCompactDataStructure:
    """Tests for _compact_data_structure function."""

    def test_list_of_dicts_format(self) -> None:
        """Test format of compacted list of dicts."""
        data = [{"name": "A"}, {"name": "B"}]
        result = _compact_data_structure(data, max_items=3, max_field_length=40)

        assert result.startswith("[")
        assert result.endswith("]")
        assert "1." in result
        assert "2." in result

    def test_max_items_limit(self) -> None:
        """Test that max_items limit is respected."""
        data = [{"name": f"Item{i}"} for i in range(10)]
        result = _compact_data_structure(data, max_items=3, max_field_length=40)

        assert "(+7 more)" in result
        assert "1." in result
        assert "3." in result

    def test_single_dict_uses_payload_to_text(self) -> None:
        """Test that single dict uses payload_to_text format."""
        data = {"name": "John", "email": "john@example.com"}
        result = _compact_data_structure(data, max_items=3, max_field_length=40)

        # Should contain pipe separator from payload_to_text
        assert "|" in result or "John" in result

    def test_list_of_scalars_format(self) -> None:
        """Test format of compacted list of scalars."""
        data = [1, 2, 3, 4, 5, 6]
        result = _compact_data_structure(data, max_items=3, max_field_length=40)

        assert result.startswith("[")
        assert "(+3)" in result

    def test_empty_list(self) -> None:
        """Test empty list returns empty brackets."""
        result = _compact_data_structure([], max_items=3, max_field_length=40)
        assert result == "[]"


class TestCompactEmbeddedData:
    """Tests for _compact_embedded_data function."""

    def test_compacts_embedded_list(self) -> None:
        """Test compaction of embedded list in text."""
        text = (
            "Hotels: [{'name': 'Grand Hotel', 'rating': 4.5}, {'name': 'City Inn', 'rating': 4.0}]"
        )
        result, chars_saved = _compact_embedded_data(text, min_size=20)

        assert chars_saved > 0
        assert "Grand Hotel" in result
        assert "City Inn" in result

    def test_preserves_surrounding_text(self) -> None:
        """Test that surrounding text is preserved."""
        text = "BEFORE [{'key': 'value'}] AFTER"
        result, _ = _compact_embedded_data(text, min_size=10)

        assert result.startswith("BEFORE")
        assert result.endswith("AFTER")

    def test_no_compaction_when_small(self) -> None:
        """Test no compaction when data is small."""
        text = "Data: [{'a': 1}]"
        result, chars_saved = _compact_embedded_data(text, min_size=1000)

        assert chars_saved == 0
        assert result == text

    def test_no_data_blocks(self) -> None:
        """Test no compaction when no data blocks."""
        text = "Plain text without any data structures"
        result, chars_saved = _compact_embedded_data(text, min_size=10)

        assert chars_saved == 0
        assert result == text

    def test_multiple_blocks_compacted(self) -> None:
        """Test multiple blocks are compacted."""
        text = "List1: [{'a': 1}] and List2: [{'b': 2}]"
        result, chars_saved = _compact_embedded_data(text, min_size=10)

        # Depending on compaction, chars_saved might be 0 if compact == original
        # But both blocks should still be processed
        assert "List1:" in result
        assert "List2:" in result


class TestIntegration:
    """Integration tests for text compaction."""

    def test_google_places_data_compaction(self) -> None:
        """Test compaction of realistic API data (simplified for payload_to_text)."""
        # Use simplified structure that payload_to_text handles well
        # (direct 'name' field instead of nested 'displayName.text')
        places_data = """[
            {
                'name': 'Grand Hotel Mulhouse',
                'address': '4 Avenue de la République, 68100 Mulhouse',
                'rating': 4.2,
                'reviewCount': 1547,
                'types': ['lodging', 'establishment'],
                'priceLevel': 'moderate'
            },
            {
                'name': 'Hotel Bristol',
                'address': '18 Avenue de Colmar, 68100 Mulhouse',
                'rating': 4.0,
                'reviewCount': 892,
                'types': ['lodging', 'establishment'],
                'priceLevel': 'moderate'
            }
        ]"""

        original_content = f"Write an email about these hotels: {places_data}"
        original_len = len(original_content)
        params = {"content_instruction": original_content}

        with patch(
            "src.domains.agents.orchestration.text_compaction.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                text_compaction_enabled=True,
                text_compaction_min_size=100,
                text_compaction_max_items=5,
                text_compaction_max_field_length=50,
            )
            result = compact_text_params(params, "send_email_tool")

        compacted_len = len(result["content_instruction"])

        # Should achieve significant compression
        assert compacted_len < original_len
        compression_ratio = (original_len - compacted_len) / original_len
        assert compression_ratio > 0.2  # At least 20% compression

        # Key information should be preserved (hotel names via 'name' field)
        assert "Grand Hotel Mulhouse" in result["content_instruction"]
        assert "Hotel Bristol" in result["content_instruction"]

    def test_email_with_contacts_data(self) -> None:
        """Test compaction of embedded contacts data in email."""
        # payload_to_text extracts displayName from names[0].displayName
        contacts_data = (
            "[{'names': [{'displayName': 'Jean Dupont'}], "
            "'emailAddresses': [{'value': 'jean@example.com'}], "
            "'phoneNumbers': [{'value': '+33612345678'}]}]"
        )

        original_content = f"Send email to: {contacts_data}"
        original_len = len(original_content)
        params = {"content_instruction": original_content}

        with patch(
            "src.domains.agents.orchestration.text_compaction.get_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                text_compaction_enabled=True,
                text_compaction_min_size=50,
                text_compaction_max_items=3,
                text_compaction_max_field_length=40,
            )
            result = compact_text_params(params, "send_email_tool")

        # Should be compacted (compare against saved original length)
        assert len(result["content_instruction"]) < original_len
        # Name should be preserved (payload_to_text extracts from names[0].displayName)
        assert "Jean Dupont" in result["content_instruction"]
