"""
Unit tests for HITL Validator.

Tests centralized validation framework for HITL flows including:
- Tool name/args extraction
- DoS protection (action count validation)
- Parameter validation
- Tool call ID extraction
- Error message formatting

@created: 2026-02-02
@coverage: validator.py
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.hitl.validator import (
    HitlValidator,
    ValidationError,
    ValidationResult,
)

# ============================================================================
# ValidationError Dataclass Tests
# ============================================================================


class TestValidationErrorDataclass:
    """Tests for ValidationError dataclass."""

    def test_validation_error_required_fields(self):
        """Test ValidationError with required fields only."""
        error = ValidationError(
            field="tool_name",
            message="Tool name is required",
            error_code="MISSING_TOOL_NAME",
        )
        assert error.field == "tool_name"
        assert error.message == "Tool name is required"
        assert error.error_code == "MISSING_TOOL_NAME"
        assert error.context is None

    def test_validation_error_with_context(self):
        """Test ValidationError with context."""
        error = ValidationError(
            field="action_count",
            message="Too many actions",
            error_code="MAX_ACTIONS_EXCEEDED",
            context={"count": 15, "max": 10},
        )
        assert error.context == {"count": 15, "max": 10}


# ============================================================================
# ValidationResult Dataclass Tests
# ============================================================================


class TestValidationResultDataclass:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Test valid ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=[],
        )
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_invalid_result_with_errors(self):
        """Test invalid ValidationResult with errors."""
        error = ValidationError(
            field="test",
            message="Test error",
            error_code="TEST_ERROR",
        )
        result = ValidationResult(
            is_valid=False,
            errors=[error],
            warnings=["This is a warning"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "TEST_ERROR"
        assert len(result.warnings) == 1


# ============================================================================
# HitlValidator Class Tests
# ============================================================================


class TestHitlValidatorInit:
    """Tests for HitlValidator initialization."""

    def test_default_max_actions(self):
        """Test default max_actions is from constants."""
        validator = HitlValidator()
        # Default is MAX_HITL_ACTIONS_PER_REQUEST = 10
        assert validator.max_actions == 10

    def test_custom_max_actions(self):
        """Test custom max_actions is respected."""
        validator = HitlValidator(max_actions=5)
        assert validator.max_actions == 5


# ============================================================================
# extract_tool_name Tests
# ============================================================================


class TestExtractToolName:
    """Tests for HitlValidator.extract_tool_name static method."""

    def test_extract_from_name_key(self):
        """Test extraction from 'name' key (primary)."""
        action = {"name": "search_contacts", "args": {"query": "John"}}
        result = HitlValidator.extract_tool_name(action)
        assert result == "search_contacts"

    def test_extract_from_tool_key(self):
        """Test extraction from 'tool' key (fallback)."""
        action = {"tool": "send_email", "tool_input": {"to": "user@example.com"}}
        result = HitlValidator.extract_tool_name(action)
        assert result == "send_email"

    def test_extract_from_tool_name_key(self):
        """Test extraction from 'tool_name' key (alternative)."""
        action = {"tool_name": "get_weather", "parameters": {"city": "Paris"}}
        result = HitlValidator.extract_tool_name(action)
        assert result == "get_weather"

    def test_name_key_takes_precedence(self):
        """Test 'name' key takes precedence over 'tool'."""
        action = {"name": "primary_tool", "tool": "fallback_tool"}
        result = HitlValidator.extract_tool_name(action)
        assert result == "primary_tool"

    def test_missing_tool_name_raises_value_error(self):
        """Test missing tool name raises ValueError."""
        action = {"args": {"query": "test"}}
        with pytest.raises(ValueError) as exc_info:
            HitlValidator.extract_tool_name(action)
        assert "Tool name is missing" in str(exc_info.value)
        assert "name" in str(exc_info.value)

    def test_none_tool_name_raises_value_error(self):
        """Test None tool name raises ValueError."""
        action = {"name": None, "args": {}}
        with pytest.raises(ValueError) as exc_info:
            HitlValidator.extract_tool_name(action)
        assert "Tool name is missing" in str(exc_info.value)

    def test_empty_string_tool_name_raises_value_error(self):
        """Test empty string tool name raises ValueError.

        Note: Empty string is falsy in Python, so the `or` chain treats it
        as missing (same as None). The error message says "missing" not "empty".
        """
        action = {"name": "", "args": {}}
        with pytest.raises(ValueError) as exc_info:
            HitlValidator.extract_tool_name(action)
        # Empty string is treated as missing (falsy in or chain)
        assert "missing" in str(exc_info.value).lower()

    def test_integer_tool_name_coerced_to_string(self):
        """Test integer tool name is coerced to string."""
        action = {"name": 123, "args": {}}
        result = HitlValidator.extract_tool_name(action)
        assert result == "123"
        assert isinstance(result, str)

    def test_error_includes_available_keys(self):
        """Test error message includes available keys."""
        action = {"unknown_key": "value", "other_key": "data"}
        with pytest.raises(ValueError) as exc_info:
            HitlValidator.extract_tool_name(action)
        # Should list received keys in error
        assert "unknown_key" in str(exc_info.value) or "Received keys" in str(exc_info.value)


# ============================================================================
# extract_tool_args Tests
# ============================================================================


class TestExtractToolArgs:
    """Tests for HitlValidator.extract_tool_args static method."""

    def test_extract_from_args_key(self):
        """Test extraction from 'args' key (primary)."""
        action = {"name": "search", "args": {"query": "test"}}
        result = HitlValidator.extract_tool_args(action)
        assert result == {"query": "test"}

    def test_extract_from_tool_input_key(self):
        """Test extraction from 'tool_input' key (legacy)."""
        action = {"name": "search", "tool_input": {"limit": 10}}
        result = HitlValidator.extract_tool_args(action)
        assert result == {"limit": 10}

    def test_extract_from_tool_args_key(self):
        """Test extraction from 'tool_args' key (alternative)."""
        action = {"name": "search", "tool_args": {"offset": 5}}
        result = HitlValidator.extract_tool_args(action)
        assert result == {"offset": 5}

    def test_args_key_takes_precedence(self):
        """Test 'args' key takes precedence."""
        action = {
            "name": "search",
            "args": {"primary": True},
            "tool_input": {"fallback": True},
        }
        result = HitlValidator.extract_tool_args(action)
        assert result == {"primary": True}

    def test_missing_args_returns_empty_dict(self):
        """Test missing args returns empty dict (not None)."""
        action = {"name": "no_args_tool"}
        result = HitlValidator.extract_tool_args(action)
        assert result == {}
        assert isinstance(result, dict)

    def test_none_args_returns_empty_dict(self):
        """Test None args returns empty dict."""
        action = {"name": "tool", "args": None}
        result = HitlValidator.extract_tool_args(action)
        assert result == {}


# ============================================================================
# validate_action_count Tests (DoS Protection)
# ============================================================================


class TestValidateActionCount:
    """Tests for HitlValidator.validate_action_count method."""

    def test_valid_action_count(self):
        """Test valid action count passes."""
        validator = HitlValidator(max_actions=10)
        actions = [{"name": f"tool_{i}"} for i in range(5)]
        result = validator.validate_action_count(actions, raise_on_error=False)
        assert result.is_valid is True
        assert result.errors == []

    def test_exactly_at_max_passes(self):
        """Test exactly at max limit passes."""
        validator = HitlValidator(max_actions=10)
        actions = [{"name": f"tool_{i}"} for i in range(10)]
        result = validator.validate_action_count(actions, raise_on_error=False)
        assert result.is_valid is True

    def test_exceeds_max_fails(self):
        """Test exceeding max limit fails."""
        validator = HitlValidator(max_actions=10)
        actions = [{"name": f"tool_{i}"} for i in range(15)]
        result = validator.validate_action_count(actions, raise_on_error=False)
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "HITL_MAX_ACTIONS_EXCEEDED"

    def test_exceeds_max_raises_on_default(self):
        """Test exceeding max raises ValueError by default."""
        validator = HitlValidator(max_actions=10)
        actions = [{"name": f"tool_{i}"} for i in range(15)]
        with pytest.raises(ValueError) as exc_info:
            validator.validate_action_count(actions)  # raise_on_error=True by default
        assert "Too many HITL actions" in str(exc_info.value)
        assert "15" in str(exc_info.value)
        assert "10" in str(exc_info.value)

    def test_error_context_includes_counts(self):
        """Test error context includes action counts."""
        validator = HitlValidator(max_actions=10)
        actions = [{"name": f"tool_{i}"} for i in range(12)]
        result = validator.validate_action_count(actions, raise_on_error=False)
        error = result.errors[0]
        assert error.context["action_count"] == 12
        assert error.context["max_allowed"] == 10
        assert error.context["exceeded_by"] == 2

    def test_empty_actions_list_valid(self):
        """Test empty actions list is valid."""
        validator = HitlValidator(max_actions=10)
        result = validator.validate_action_count([], raise_on_error=False)
        assert result.is_valid is True

    @patch("src.domains.agents.services.hitl.validator.logger")
    def test_logs_security_event_on_exceed(self, mock_logger):
        """Test security event is logged when limit exceeded."""
        validator = HitlValidator(max_actions=10)
        actions = [{"name": f"tool_{i}"} for i in range(15)]
        validator.validate_action_count(actions, raise_on_error=False)
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert call_args[0][0] == "hitl_dos_protection_triggered"


# ============================================================================
# validate_edited_params Tests
# ============================================================================


class TestValidateEditedParams:
    """Tests for HitlValidator.validate_edited_params method."""

    def test_edit_with_params_valid(self):
        """Test EDIT decision with edited_params is valid."""
        validator = HitlValidator()
        result = validator.validate_edited_params(
            edited_params={"query": "new query"},
            decision_type="EDIT",
        )
        assert result.is_valid is True

    def test_edit_without_params_invalid(self):
        """Test EDIT decision without edited_params is invalid."""
        validator = HitlValidator()
        result = validator.validate_edited_params(
            edited_params=None,
            decision_type="EDIT",
        )
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "EDIT_MISSING_PARAMS"

    def test_edit_with_empty_dict_invalid(self):
        """Test EDIT decision with empty dict is invalid."""
        validator = HitlValidator()
        result = validator.validate_edited_params(
            edited_params={},  # Falsy empty dict
            decision_type="EDIT",
        )
        assert result.is_valid is False

    def test_approve_without_params_valid(self):
        """Test APPROVE decision without edited_params is valid."""
        validator = HitlValidator()
        result = validator.validate_edited_params(
            edited_params=None,
            decision_type="APPROVE",
        )
        assert result.is_valid is True

    def test_reject_without_params_valid(self):
        """Test REJECT decision without edited_params is valid."""
        validator = HitlValidator()
        result = validator.validate_edited_params(
            edited_params=None,
            decision_type="REJECT",
        )
        assert result.is_valid is True

    def test_ambiguous_without_params_valid(self):
        """Test AMBIGUOUS decision without edited_params is valid."""
        validator = HitlValidator()
        result = validator.validate_edited_params(
            edited_params=None,
            decision_type="AMBIGUOUS",
        )
        assert result.is_valid is True

    @patch("src.domains.agents.services.hitl.validator.logger")
    def test_logs_error_on_missing_edit_params(self, mock_logger):
        """Test error is logged when EDIT missing params."""
        validator = HitlValidator()
        validator.validate_edited_params(
            edited_params=None,
            decision_type="EDIT",
        )
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert call_args[0][0] == "hitl_edit_missing_params"


# ============================================================================
# extract_tool_call_id Tests
# ============================================================================


class TestExtractToolCallId:
    """Tests for HitlValidator.extract_tool_call_id static method."""

    def test_extract_from_dict_with_id(self):
        """Test extraction from dict with 'id' key."""
        tool_call = {"id": "call_abc123", "name": "search", "args": {}}
        result = HitlValidator.extract_tool_call_id(tool_call)
        assert result == "call_abc123"

    def test_extract_from_dict_without_id(self):
        """Test extraction from dict without 'id' returns None."""
        tool_call = {"name": "search", "args": {}}
        result = HitlValidator.extract_tool_call_id(tool_call)
        assert result is None

    def test_extract_from_object_with_id(self):
        """Test extraction from object with id attribute."""
        tool_call = MagicMock()
        tool_call.id = "call_xyz789"
        result = HitlValidator.extract_tool_call_id(tool_call)
        assert result == "call_xyz789"

    def test_extract_from_object_without_id(self):
        """Test extraction from object without id attribute."""
        tool_call = MagicMock(spec=[])  # No attributes
        result = HitlValidator.extract_tool_call_id(tool_call)
        assert result is None

    @patch("src.domains.agents.services.hitl.validator.logger")
    def test_logs_warning_on_unexpected_type(self, mock_logger):
        """Test warning is logged when tool_call is unexpected type.

        Note: Dict and object types return silently (dict.get returns None,
        object.id is checked). Warning is only logged for unexpected types
        that are neither dict nor have id attribute.
        """
        # Use a simple string which is neither dict nor has id attribute
        tool_call = "unexpected_string_type"
        result = HitlValidator.extract_tool_call_id(tool_call)
        assert result is None
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "tool_call_missing_id"


# ============================================================================
# format_validation_errors Tests
# ============================================================================


class TestFormatValidationErrors:
    """Tests for HitlValidator.format_validation_errors static method."""

    def test_empty_errors_returns_empty_string(self):
        """Test empty error list returns empty string."""
        result = HitlValidator.format_validation_errors([], "en")
        assert result == ""

    def test_single_error_formatted(self):
        """Test single error is formatted correctly."""
        errors = [
            ValidationError(
                field="query",
                message="Query is required",
                error_code="MISSING_QUERY",
            )
        ]
        result = HitlValidator.format_validation_errors(errors, "en")
        assert "couldn't apply your edits" in result.lower()
        assert "query" in result.lower()
        assert "Please try again" in result

    def test_multiple_errors_formatted(self):
        """Test multiple errors are formatted as bullet list."""
        errors = [
            ValidationError(
                field="query",
                message="Query is required",
                error_code="MISSING_QUERY",
            ),
            ValidationError(
                field="limit",
                message="Limit must be positive",
                error_code="INVALID_LIMIT",
            ),
        ]
        result = HitlValidator.format_validation_errors(errors, "en")
        # Should have bullet points
        assert "- " in result
        # Should have header and footer
        lines = result.strip().split("\n")
        assert len(lines) >= 3  # Header, errors, footer

    def test_french_language(self):
        """Test French language formatting."""
        errors = [
            ValidationError(
                field="query",
                message="Query is required",
                error_code="MISSING_QUERY",
            )
        ]
        result = HitlValidator.format_validation_errors(errors, "fr")
        assert "Je n'ai pas pu appliquer" in result
        assert "Veuillez réessayer" in result

    def test_spanish_language(self):
        """Test Spanish language formatting."""
        errors = [
            ValidationError(
                field="test",
                message="Test",
                error_code="TEST",
            )
        ]
        result = HitlValidator.format_validation_errors(errors, "es")
        assert "No pude aplicar" in result
        assert "Por favor" in result

    def test_german_language(self):
        """Test German language formatting."""
        errors = [
            ValidationError(
                field="test",
                message="Test",
                error_code="TEST",
            )
        ]
        result = HitlValidator.format_validation_errors(errors, "de")
        assert "Ich konnte Ihre Änderungen" in result
        assert "Bitte versuchen Sie" in result

    def test_italian_language(self):
        """Test Italian language formatting."""
        errors = [
            ValidationError(
                field="test",
                message="Test",
                error_code="TEST",
            )
        ]
        result = HitlValidator.format_validation_errors(errors, "it")
        assert "Non sono riuscito" in result
        assert "Si prega di riprovare" in result

    def test_chinese_language(self):
        """Test Chinese language formatting."""
        errors = [
            ValidationError(
                field="test",
                message="Test",
                error_code="TEST",
            )
        ]
        result = HitlValidator.format_validation_errors(errors, "zh-CN")
        assert "由于以下错误" in result
        assert "请使用有效参数重试" in result

    def test_unknown_language_falls_back_to_english(self):
        """Test unknown language falls back to English."""
        errors = [
            ValidationError(
                field="test",
                message="Test",
                error_code="TEST",
            )
        ]
        result = HitlValidator.format_validation_errors(errors, "xx-unknown")
        assert "couldn't apply your edits" in result.lower()
        assert "Please try again" in result


# ============================================================================
# Integration Tests
# ============================================================================


class TestHitlValidatorIntegration:
    """Integration tests for HitlValidator."""

    def test_full_validation_workflow(self):
        """Test complete validation workflow."""
        validator = HitlValidator(max_actions=5)

        # Simulate action requests
        actions = [
            {"name": "search_contacts", "args": {"query": "John"}},
            {"name": "send_email", "args": {"to": "john@example.com"}},
        ]

        # Validate action count
        count_result = validator.validate_action_count(actions, raise_on_error=False)
        assert count_result.is_valid is True

        # Extract tool info from each action
        for action in actions:
            tool_name = validator.extract_tool_name(action)
            tool_args = validator.extract_tool_args(action)
            assert tool_name != ""
            assert isinstance(tool_args, dict)

        # Validate edited params for EDIT decision
        edit_result = validator.validate_edited_params(
            edited_params={"query": "Jane"},
            decision_type="EDIT",
        )
        assert edit_result.is_valid is True

    def test_validation_failure_workflow(self):
        """Test validation failure workflow with error formatting."""
        validator = HitlValidator(max_actions=3)

        # Too many actions
        actions = [{"name": f"tool_{i}"} for i in range(5)]
        count_result = validator.validate_action_count(actions, raise_on_error=False)
        assert count_result.is_valid is False

        # Format errors for user
        formatted = validator.format_validation_errors(count_result.errors, "en")
        assert formatted != ""

    def test_tool_call_with_langchain_format(self):
        """Test extraction with LangChain tool call format."""
        # LangChain ToolCall format
        tool_call = {
            "id": "call_abc123",
            "name": "search_contacts",
            "args": {"query": "John", "limit": 10},
        }

        tool_name = HitlValidator.extract_tool_name(tool_call)
        tool_args = HitlValidator.extract_tool_args(tool_call)
        tool_id = HitlValidator.extract_tool_call_id(tool_call)

        assert tool_name == "search_contacts"
        assert tool_args == {"query": "John", "limit": 10}
        assert tool_id == "call_abc123"

    def test_legacy_langchain_format(self):
        """Test extraction with legacy LangChain format."""
        # Legacy format (pre 0.2)
        tool_call = {
            "tool": "old_tool_name",
            "tool_input": {"param1": "value1"},
        }

        tool_name = HitlValidator.extract_tool_name(tool_call)
        tool_args = HitlValidator.extract_tool_args(tool_call)

        assert tool_name == "old_tool_name"
        assert tool_args == {"param1": "value1"}
