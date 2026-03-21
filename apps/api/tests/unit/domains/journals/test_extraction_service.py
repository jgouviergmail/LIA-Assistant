"""Unit tests for journal extraction service (JSON parsing)."""

import pytest

from src.domains.journals.extraction_service import _parse_journal_extraction_result


@pytest.mark.unit
class TestParseJournalExtractionResult:
    """Tests for the JSON parsing with fallback."""

    def test_empty_array(self) -> None:
        """Empty array returns no actions."""
        result = _parse_journal_extraction_result("[]")
        assert result == []

    def test_valid_create_action(self) -> None:
        """Valid create action is parsed correctly."""
        json_str = """[{
            "action": "create",
            "theme": "self_reflection",
            "title": "My thought",
            "content": "I reflected on something.",
            "mood": "reflective"
        }]"""
        result = _parse_journal_extraction_result(json_str)
        assert len(result) == 1
        assert result[0].action == "create"
        assert result[0].theme.value == "self_reflection"
        assert result[0].title == "My thought"

    def test_valid_delete_action(self) -> None:
        """Valid delete action is parsed correctly."""
        test_uuid = "00000000-0000-0000-0000-000000000001"
        json_str = f'[{{"action": "delete", "entry_id": "{test_uuid}"}}]'
        result = _parse_journal_extraction_result(json_str)
        assert len(result) == 1
        assert result[0].action == "delete"
        assert result[0].entry_id == test_uuid

    def test_multiple_actions(self) -> None:
        """Multiple actions parsed correctly."""
        json_str = """[
            {"action": "create", "theme": "learnings", "title": "Lesson", "content": "Content", "mood": "inspired"},
            {"action": "delete", "entry_id": "00000000-0000-0000-0000-000000000002"}
        ]"""
        result = _parse_journal_extraction_result(json_str)
        assert len(result) == 2

    def test_markdown_code_fences_stripped(self) -> None:
        """Markdown code fences around JSON are handled."""
        json_str = '```json\n[{"action": "create", "theme": "learnings", "title": "T", "content": "C"}]\n```'
        result = _parse_journal_extraction_result(json_str)
        assert len(result) == 1
        assert result[0].action == "create"

    def test_trailing_commas_cleaned(self) -> None:
        """Trailing commas before ] are cleaned."""
        json_str = '[{"action": "delete", "entry_id": "00000000-0000-0000-0000-000000000003",}]'
        result = _parse_journal_extraction_result(json_str)
        assert len(result) == 1

    def test_invalid_json_returns_empty(self) -> None:
        """Completely invalid JSON returns empty list."""
        result = _parse_journal_extraction_result("not json at all")
        assert result == []

    def test_non_list_returns_empty(self) -> None:
        """JSON object (not array) returns empty list."""
        result = _parse_journal_extraction_result('{"action": "create"}')
        assert result == []

    def test_mixed_valid_invalid_items(self) -> None:
        """Invalid items are skipped, valid ones kept."""
        json_str = """[
            {"action": "create", "theme": "learnings", "title": "Valid", "content": "OK"},
            {"invalid": "item"},
            {"action": "delete", "entry_id": "00000000-0000-0000-0000-000000000004"}
        ]"""
        result = _parse_journal_extraction_result(json_str)
        assert len(result) == 2  # Invalid item skipped

    def test_embedded_json_in_text(self) -> None:
        """JSON array embedded in surrounding text is extracted."""
        json_str = 'Here are my thoughts:\n[{"action": "delete", "entry_id": "00000000-0000-0000-0000-000000000005"}]\nDone.'
        result = _parse_journal_extraction_result(json_str)
        assert len(result) == 1

    def test_invalid_uuid_entry_id_filtered(self) -> None:
        """Actions with malformed UUIDs are filtered out during parsing."""
        json_str = """[
            {"action": "delete", "entry_id": "not-a-valid-uuid"},
            {"action": "create", "theme": "learnings", "title": "Valid", "content": "OK"}
        ]"""
        result = _parse_journal_extraction_result(json_str)
        assert len(result) == 1
        assert result[0].action == "create"

    def test_null_string(self) -> None:
        """Null/empty string returns empty list."""
        assert _parse_journal_extraction_result("") == []
        assert _parse_journal_extraction_result("null") == []
