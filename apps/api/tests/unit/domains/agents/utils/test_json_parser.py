"""
Unit tests for JSON parser utilities.

Tests for robust JSON parsing from LLM responses,
handling various formats and edge cases.
"""

from unittest.mock import patch

import pytest

from src.domains.agents.utils.json_parser import (
    JSONParseError,
    JSONParseResult,
    _extract_json_text,
    extract_json_from_llm_response,
    validate_json_structure,
)

# ============================================================================
# Tests for JSONParseResult dataclass
# ============================================================================


class TestJSONParseResult:
    """Tests for JSONParseResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful result."""
        result = JSONParseResult(
            success=True,
            data={"key": "value"},
        )

        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None
        assert result.raw_text is None
        assert result.extracted_json is None

    def test_create_error_result(self):
        """Test creating an error result."""
        result = JSONParseResult(
            success=False,
            data=None,
            error="Parse error",
            raw_text="invalid json",
        )

        assert result.success is False
        assert result.data is None
        assert result.error == "Parse error"
        assert result.raw_text == "invalid json"

    def test_create_with_all_fields(self):
        """Test creating result with all fields."""
        result = JSONParseResult(
            success=True,
            data={"test": 123},
            error=None,
            raw_text='```json\n{"test": 123}\n```',
            extracted_json='{"test": 123}',
        )

        assert result.success is True
        assert result.data == {"test": 123}
        assert result.extracted_json == '{"test": 123}'


# ============================================================================
# Tests for JSONParseError exception
# ============================================================================


class TestJSONParseError:
    """Tests for JSONParseError exception."""

    def test_create_error_with_message(self):
        """Test creating error with message only."""
        error = JSONParseError("Test error message")

        assert str(error) == "Test error message"
        assert error.raw_text is None

    def test_create_error_with_raw_text(self):
        """Test creating error with message and raw_text."""
        error = JSONParseError("Parse failed", raw_text="invalid data")

        assert str(error) == "Parse failed"
        assert error.raw_text == "invalid data"

    def test_error_is_exception(self):
        """Test that JSONParseError is an Exception."""
        error = JSONParseError("Test")

        assert isinstance(error, Exception)

    def test_error_can_be_raised(self):
        """Test that JSONParseError can be raised and caught."""
        with pytest.raises(JSONParseError) as exc_info:
            raise JSONParseError("Raised error", raw_text="test")

        assert str(exc_info.value) == "Raised error"
        assert exc_info.value.raw_text == "test"


# ============================================================================
# Tests for _extract_json_text
# ============================================================================


class TestExtractJsonTextCodeBlocks:
    """Tests for JSON extraction from code blocks."""

    def test_extract_from_json_code_block(self):
        """Test extraction from ```json block."""
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'

    def test_extract_from_json_code_block_with_spaces(self):
        """Test extraction from ```json block with whitespace."""
        text = '```json\n  {"key": "value"}  \n```'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'

    def test_extract_from_generic_code_block(self):
        """Test extraction from ``` block without language."""
        text = '```\n{"key": "value"}\n```'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'

    def test_extract_from_code_block_with_json_word(self):
        """Test extraction removes 'json' word from block start."""
        text = '```\njson\n{"key": "value"}\n```'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'

    def test_extract_with_text_before_code_block(self):
        """Test extraction ignores text before code block."""
        text = 'Here is the JSON:\n```json\n{"key": "value"}\n```'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'

    def test_extract_with_text_after_code_block(self):
        """Test extraction ignores text after code block."""
        text = '```json\n{"key": "value"}\n```\nAnd more text.'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'


class TestExtractJsonTextBrackets:
    """Tests for JSON extraction using bracket matching."""

    def test_extract_plain_json_object(self):
        """Test extraction of plain JSON object."""
        text = '{"key": "value"}'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'

    def test_extract_plain_json_array(self):
        """Test extraction of plain JSON array."""
        text = "[1, 2, 3]"
        result = _extract_json_text(text)
        assert result == "[1, 2, 3]"

    def test_extract_json_with_text_before(self):
        """Test extraction of JSON with text before."""
        text = 'Result: {"key": "value"}'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'

    def test_extract_json_with_text_after(self):
        """Test extraction of JSON with text after."""
        text = '{"key": "value"} More text'
        result = _extract_json_text(text)
        assert result == '{"key": "value"}'

    def test_extract_nested_json(self):
        """Test extraction of nested JSON."""
        text = '{"outer": {"inner": "value"}}'
        result = _extract_json_text(text)
        assert result == '{"outer": {"inner": "value"}}'

    def test_extract_array_of_objects(self):
        """Test extraction of array of objects."""
        text = '[{"a": 1}, {"b": 2}]'
        result = _extract_json_text(text)
        assert result == '[{"a": 1}, {"b": 2}]'

    def test_extract_json_with_string_containing_braces(self):
        """Test extraction handles strings containing braces."""
        text = '{"text": "value with { and } inside"}'
        result = _extract_json_text(text)
        assert result == '{"text": "value with { and } inside"}'

    def test_extract_json_with_escaped_quotes(self):
        """Test extraction handles escaped quotes in strings."""
        text = r'{"text": "value with \"quotes\""}'
        result = _extract_json_text(text)
        assert result == r'{"text": "value with \"quotes\""}'


class TestExtractJsonTextEdgeCases:
    """Tests for edge cases in JSON extraction."""

    def test_extract_from_empty_string(self):
        """Test extraction from empty string."""
        result = _extract_json_text("")
        assert result == ""

    def test_extract_from_whitespace_only(self):
        """Test extraction from whitespace-only string."""
        result = _extract_json_text("   \n\t  ")
        assert result == ""

    def test_extract_no_json_structure(self):
        """Test extraction when no JSON structure found."""
        text = "Just plain text without JSON"
        result = _extract_json_text(text)
        assert result == text

    def test_extract_unbalanced_brackets(self):
        """Test extraction with unbalanced brackets."""
        text = '{"incomplete": '
        result = _extract_json_text(text)
        assert '{"incomplete":' in result

    def test_prefers_first_json_structure(self):
        """Test that first JSON structure is extracted."""
        text = '{"first": 1} {"second": 2}'
        result = _extract_json_text(text)
        assert result == '{"first": 1}'


# ============================================================================
# Tests for extract_json_from_llm_response
# ============================================================================


class TestExtractJsonFromLLMResponseBasic:
    """Tests for basic JSON extraction from LLM responses."""

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_success_total")
    def test_parse_simple_json(self, mock_metric):
        """Test parsing simple JSON object."""
        result = extract_json_from_llm_response('{"key": "value"}')

        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_success_total")
    def test_parse_json_in_code_block(self, mock_metric):
        """Test parsing JSON in code block."""
        text = '```json\n{"key": "value"}\n```'
        result = extract_json_from_llm_response(text)

        assert result.success is True
        assert result.data == {"key": "value"}

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_success_total")
    def test_parse_json_array(self, mock_metric):
        """Test parsing JSON array."""
        result = extract_json_from_llm_response("[1, 2, 3]", expected_type=list)

        assert result.success is True
        assert result.data == [1, 2, 3]

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_success_total")
    def test_stores_raw_text_and_extracted_json(self, mock_metric):
        """Test that raw_text and extracted_json are stored."""
        raw = '```json\n{"key": "value"}\n```'
        result = extract_json_from_llm_response(raw)

        assert result.raw_text == raw
        assert result.extracted_json == '{"key": "value"}'


class TestExtractJsonFromLLMResponseErrors:
    """Tests for error handling in JSON extraction."""

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_errors_total")
    def test_empty_response_returns_error(self, mock_metric):
        """Test that empty response returns error."""
        result = extract_json_from_llm_response("")

        assert result.success is False
        assert "Empty response" in result.error

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_errors_total")
    def test_none_response_returns_error(self, mock_metric):
        """Test that None-like response returns error."""
        result = extract_json_from_llm_response(None)  # type: ignore

        assert result.success is False

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_errors_total")
    def test_invalid_json_returns_error(self, mock_metric):
        """Test that invalid JSON returns error."""
        result = extract_json_from_llm_response("{invalid json}")

        assert result.success is False
        assert "JSON decode error" in result.error

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_errors_total")
    def test_type_mismatch_returns_error(self, mock_metric):
        """Test that type mismatch returns error."""
        result = extract_json_from_llm_response("[1, 2, 3]", expected_type=dict)

        assert result.success is False
        assert "Expected dict" in result.error


class TestExtractJsonFromLLMResponseRequiredFields:
    """Tests for required field validation."""

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_success_total")
    def test_succeeds_with_required_fields_present(self, mock_metric):
        """Test success when required fields are present."""
        result = extract_json_from_llm_response(
            '{"name": "test", "count": 5}',
            required_fields=["name", "count"],
        )

        assert result.success is True
        assert result.data["name"] == "test"
        assert result.data["count"] == 5

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_errors_total")
    def test_fails_with_missing_required_fields(self, mock_metric):
        """Test failure when required fields are missing."""
        result = extract_json_from_llm_response(
            '{"name": "test"}',
            required_fields=["name", "count"],
        )

        assert result.success is False
        assert "Missing required fields" in result.error
        # Partial data should still be returned
        assert result.data == {"name": "test"}

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_success_total")
    def test_no_validation_for_list_with_required_fields(self, mock_metric):
        """Test that required_fields is ignored for lists."""
        result = extract_json_from_llm_response(
            "[1, 2, 3]",
            expected_type=list,
            required_fields=["impossible_field"],
        )

        # Should succeed because required_fields only applies to dicts
        assert result.success is True


class TestExtractJsonFromLLMResponseContext:
    """Tests for context and run_id parameters."""

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_success_total")
    def test_accepts_context_parameter(self, mock_metric):
        """Test that context parameter is accepted."""
        result = extract_json_from_llm_response(
            '{"key": "value"}',
            context="test_context",
        )

        assert result.success is True

    @patch("src.domains.agents.utils.json_parser.agent_llm_json_parse_success_total")
    def test_accepts_run_id_parameter(self, mock_metric):
        """Test that run_id parameter is accepted."""
        result = extract_json_from_llm_response(
            '{"key": "value"}',
            run_id="test_run_123",
        )

        assert result.success is True


# ============================================================================
# Tests for validate_json_structure
# ============================================================================


class TestValidateJsonStructure:
    """Tests for JSON structure validation."""

    def test_valid_structure_returns_true(self):
        """Test validation returns True for valid structure."""
        data = {"name": "test", "count": 5, "items": [1, 2, 3]}
        schema = {"name": str, "count": int, "items": list}

        valid, errors = validate_json_structure(data, schema)

        assert valid is True
        assert errors == []

    def test_missing_field_returns_error(self):
        """Test validation returns error for missing field."""
        data = {"name": "test"}
        schema = {"name": str, "count": int}

        valid, errors = validate_json_structure(data, schema)

        assert valid is False
        assert any("Missing field: count" in e for e in errors)

    def test_wrong_type_returns_error(self):
        """Test validation returns error for wrong type."""
        data = {"name": 123}  # Should be str
        schema = {"name": str}

        valid, errors = validate_json_structure(data, schema)

        assert valid is False
        assert any("expected str" in e for e in errors)

    def test_multiple_errors_returned(self):
        """Test that multiple errors are returned."""
        data = {"wrong": "type"}  # Missing 'name', has 'wrong' instead
        schema = {"name": str, "count": int}

        valid, errors = validate_json_structure(data, schema)

        assert valid is False
        assert len(errors) == 2  # Missing name, missing count

    def test_empty_schema_validates_anything(self):
        """Test that empty schema validates any dict."""
        data = {"any": "data", "structure": [1, 2, 3]}
        schema: dict[str, type] = {}

        valid, errors = validate_json_structure(data, schema)

        assert valid is True
        assert errors == []

    def test_accepts_context_parameter(self):
        """Test that context parameter is accepted."""
        data = {"name": "test"}
        schema = {"name": str}

        valid, errors = validate_json_structure(data, schema, context="test_validation")

        assert valid is True


class TestValidateJsonStructureTypes:
    """Tests for type validation in validate_json_structure."""

    def test_validates_bool_type(self):
        """Test validation of boolean type."""
        data = {"flag": True}
        schema = {"flag": bool}

        valid, errors = validate_json_structure(data, schema)
        assert valid is True

    def test_validates_float_type(self):
        """Test validation of float type."""
        data = {"price": 9.99}
        schema = {"price": float}

        valid, errors = validate_json_structure(data, schema)
        assert valid is True

    def test_validates_dict_type(self):
        """Test validation of nested dict type."""
        data = {"metadata": {"key": "value"}}
        schema = {"metadata": dict}

        valid, errors = validate_json_structure(data, schema)
        assert valid is True

    def test_int_does_not_validate_as_bool(self):
        """Test that int doesn't validate as bool."""
        data = {"flag": 1}  # int, not bool
        schema = {"flag": bool}

        valid, errors = validate_json_structure(data, schema)
        # Note: isinstance(1, bool) is False because int is not an instance of bool
        # (even though bool is a subclass of int)
        assert valid is False
        assert any("expected bool" in e for e in errors)

    def test_bool_validates_as_int(self):
        """Test that bool validates as int (Python behavior)."""
        data = {"count": True}  # bool, which is int subclass
        schema = {"count": int}

        valid, errors = validate_json_structure(data, schema)
        # Python behavior: bool is subclass of int
        assert valid is True
