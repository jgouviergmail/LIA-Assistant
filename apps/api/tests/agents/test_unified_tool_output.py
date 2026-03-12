"""
Unit tests for UnifiedToolOutput.

Tests factory methods, validation, and compatibility properties.
Gold-grade implementation (2025-12-29).
"""

import pytest
from pydantic import ValidationError

from src.domains.agents.tools.output import UnifiedToolOutput


class TestUnifiedToolOutputFactoryMethods:
    """Tests for factory methods: action_success, data_success, failure."""

    def test_action_success_basic(self):
        """Test action_success creates success response."""
        output = UnifiedToolOutput.action_success(
            message="Rappel créé",
        )

        assert output.success is True
        assert output.message == "Rappel créé"
        assert output.structured_data == {}
        assert output.registry_updates == {}
        assert output.error_code is None
        assert output.error_message is None

    def test_action_success_with_structured_data(self):
        """Test action_success with structured_data parameter."""
        output = UnifiedToolOutput.action_success(
            message="Rappel créé pour demain",
            structured_data={"reminder_id": "abc123", "trigger_at": "2025-12-30T10:00:00"},
        )

        assert output.success is True
        assert output.message == "Rappel créé pour demain"
        assert output.structured_data == {
            "reminder_id": "abc123",
            "trigger_at": "2025-12-30T10:00:00",
        }

    def test_action_success_with_metadata(self):
        """Test action_success with metadata."""
        output = UnifiedToolOutput.action_success(
            message="Done",
            metadata={"execution_time_ms": 150},
        )

        assert output.metadata == {"execution_time_ms": 150}

    def test_data_success_basic(self):
        """Test data_success creates success response with registry."""
        output = UnifiedToolOutput.data_success(
            message="Found 3 contacts",
            structured_data={"contacts": [1, 2, 3], "count": 3},
        )

        assert output.success is True
        assert output.message == "Found 3 contacts"
        assert output.structured_data == {"contacts": [1, 2, 3], "count": 3}

    def test_failure_basic(self):
        """Test failure creates error response."""
        output = UnifiedToolOutput.failure(
            message="Contact not found",
            error_code="NOT_FOUND",
        )

        assert output.success is False
        assert output.message == "Contact not found"
        assert output.error_code == "NOT_FOUND"
        assert output.error_message == "Contact not found"

    def test_failure_with_metadata(self):
        """Test failure with metadata."""
        output = UnifiedToolOutput.failure(
            message="API error",
            error_code="http_error",
            metadata={"status_code": 500},
        )

        assert output.success is False
        assert output.error_code == "http_error"
        assert output.metadata == {"status_code": 500}


class TestUnifiedToolOutputValidation:
    """Tests for Pydantic validation rules."""

    def test_error_code_required_when_success_false(self):
        """Test that error_code is required when success=False."""
        with pytest.raises(ValidationError) as exc_info:
            UnifiedToolOutput(
                success=False,
                message="Error occurred",
                # error_code missing - should fail validation
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "error_code is required when success=False" in str(errors[0]["msg"])

    def test_error_code_optional_when_success_true(self):
        """Test that error_code is optional when success=True."""
        # Should not raise
        output = UnifiedToolOutput(
            success=True,
            message="Success",
            # error_code not provided - should be OK
        )

        assert output.success is True
        assert output.error_code is None

    def test_valid_failure_with_error_code(self):
        """Test that failure with error_code passes validation."""
        output = UnifiedToolOutput(
            success=False,
            message="Error",
            error_code="VALIDATION_ERROR",
        )

        assert output.success is False
        assert output.error_code == "VALIDATION_ERROR"


class TestUnifiedToolOutputCompatibilityProperties:
    """Tests for backward compatibility properties."""

    def test_summary_for_llm_returns_message(self):
        """Test summary_for_llm property returns message."""
        output = UnifiedToolOutput.action_success(message="Test message")

        assert output.summary_for_llm == "Test message"

    def test_tool_metadata_returns_metadata(self):
        """Test tool_metadata property returns metadata."""
        output = UnifiedToolOutput.action_success(
            message="Test",
            metadata={"key": "value"},
        )

        assert output.tool_metadata == {"key": "value"}

    def test_error_property_returns_error_code(self):
        """Test error property returns error_code for backward compatibility."""
        output = UnifiedToolOutput.failure(
            message="Error",
            error_code="NOT_FOUND",
        )

        # The .error property should return error_code
        assert output.error == "NOT_FOUND"

    def test_error_property_none_on_success(self):
        """Test error property returns None on success."""
        output = UnifiedToolOutput.action_success(message="OK")

        assert output.error is None


class TestUnifiedToolOutputStringConversion:
    """Tests for __str__ and __repr__ methods."""

    def test_str_returns_message(self):
        """Test str() returns message for LangChain compatibility."""
        output = UnifiedToolOutput.action_success(message="Rappel créé")

        assert str(output) == "Rappel créé"

    def test_str_returns_error_message(self):
        """Test str() returns message even for errors."""
        output = UnifiedToolOutput.failure(
            message="Contact not found",
            error_code="NOT_FOUND",
        )

        assert str(output) == "Contact not found"

    def test_repr_includes_status(self):
        """Test __repr__ includes success/failure status."""
        success = UnifiedToolOutput.action_success(message="OK")
        failure = UnifiedToolOutput.failure(message="Error", error_code="ERR")

        assert "✓" in repr(success)
        assert "✗" in repr(failure)


class TestUnifiedToolOutputConversion:
    """Tests for conversion methods."""

    def test_to_standard_converts_correctly(self):
        """Test to_standard() converts to StandardToolOutput."""
        output = UnifiedToolOutput.action_success(
            message="Test message",
            structured_data={"key": "value"},
            metadata={"meta": "data"},
        )

        standard = output.to_standard()

        assert standard.summary_for_llm == "Test message"
        assert standard.structured_data == {"key": "value"}
        assert standard.tool_metadata == {"meta": "data"}
        assert standard.registry_updates == {}

    def test_get_step_output_returns_structured_data(self):
        """Test get_step_output returns structured_data when present."""
        output = UnifiedToolOutput.action_success(
            message="Test",
            structured_data={"contacts": [{"name": "John"}], "count": 1},
        )

        step_output = output.get_step_output()

        assert step_output == {"contacts": [{"name": "John"}], "count": 1}

    def test_get_step_output_fallback_to_message(self):
        """Test get_step_output fallback when no structured_data."""
        output = UnifiedToolOutput.action_success(message="Just a message")

        step_output = output.get_step_output()

        assert step_output["message"] == "Just a message"
        assert step_output["success"] is True
        assert step_output["count"] == 0


class TestUnifiedToolOutputUtilities:
    """Tests for utility methods."""

    def test_to_llm_message_returns_message(self):
        """Test to_llm_message returns message field."""
        output = UnifiedToolOutput.action_success(message="LLM message here")

        assert output.to_llm_message() == "LLM message here"

    def test_get_registry_ids_empty(self):
        """Test get_registry_ids returns empty list when no registry."""
        output = UnifiedToolOutput.action_success(message="No registry")

        assert output.get_registry_ids() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
