"""
Unit tests for tool response schemas.

Phase 3.2.4: Tests for ToolResponse Pydantic validation.
"""

import json

import pytest
from pydantic import ValidationError

from src.domains.agents.tools.schemas import ToolResponse, ToolResponseError, ToolResponseSuccess


class TestToolResponse:
    """Tests for ToolResponse schema."""

    def test_success_response_with_data(self):
        """Test creating a success response with data."""
        # Given: Success response data
        data = {"contacts": [{"name": "Jean"}, {"name": "Marie"}], "total": 2}

        # When: Create ToolResponse
        response = ToolResponse(success=True, data=data)

        # Then: Valid response
        assert response.success is True
        assert response.data == data
        assert response.error is None
        assert response.message is None

    def test_error_response_with_error_code(self):
        """Test creating an error response with error code."""
        # Given: Error response data
        error_code = "NOT_FOUND"
        message = "Contact not found"

        # When: Create ToolResponse
        response = ToolResponse(success=False, error=error_code, message=message)

        # Then: Valid error response
        assert response.success is False
        assert response.error == error_code
        assert response.message == message
        assert response.data is None

    def test_success_response_factory_method(self):
        """Test success_response factory method."""
        # Given: Success data
        data = {"count": 5}
        message = "Found 5 items"

        # When: Use factory method
        response = ToolResponse.success_response(data=data, message=message)

        # Then: Correct response
        assert response.success is True
        assert response.data == data
        assert response.message == message

    def test_error_response_factory_method(self):
        """Test error_response factory method."""
        # Given: Error data
        error = "VALIDATION_ERROR"
        message = "Invalid input"

        # When: Use factory method
        response = ToolResponse.error_response(error=error, message=message)

        # Then: Correct response
        assert response.success is False
        assert response.error == error
        assert response.message == message

    def test_model_dump_json_excludes_none(self):
        """Test that model_dump_json excludes None values by default."""
        # Given: Response with some None fields
        response = ToolResponse(success=True, data={"count": 3})

        # When: Serialize to JSON
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        # Then: None fields are excluded
        assert "error" not in parsed
        assert "message" not in parsed
        assert "metadata" not in parsed
        assert parsed["success"] is True
        assert parsed["data"] == {"count": 3}

    def test_model_dump_json_with_all_fields(self):
        """Test JSON serialization with all fields present."""
        # Given: Response with all fields
        response = ToolResponse(
            success=True,
            data={"result": "ok"},
            message="Operation completed",
            metadata={"turn_id": 5, "timestamp": "2025-01-01T00:00:00Z"},
        )

        # When: Serialize to JSON
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        # Then: All fields present
        assert parsed["success"] is True
        assert parsed["data"] == {"result": "ok"}
        assert parsed["message"] == "Operation completed"
        assert parsed["metadata"]["turn_id"] == 5

    def test_response_can_be_parsed_from_json(self):
        """Test that ToolResponse can be parsed from JSON string."""
        # Given: JSON string
        json_str = '{"success": true, "data": {"count": 10}}'

        # When: Parse from JSON
        parsed_dict = json.loads(json_str)
        response = ToolResponse(**parsed_dict)

        # Then: Valid response
        assert response.success is True
        assert response.data == {"count": 10}

    def test_success_response_with_metadata(self):
        """Test success response with optional metadata."""
        # Given: Success data with metadata
        data = {"items": [1, 2, 3]}
        metadata = {"turn_id": 3, "execution_time_ms": 150}

        # When: Create response
        response = ToolResponse.success_response(data=data, metadata=metadata)

        # Then: Metadata included
        assert response.metadata == metadata
        assert response.data == data

    def test_error_response_with_metadata(self):
        """Test error response with optional metadata."""
        # Given: Error with metadata
        error = "TIMEOUT"
        message = "Operation timed out"
        metadata = {"retry_count": 3}

        # When: Create response
        response = ToolResponse.error_response(error=error, message=message, metadata=metadata)

        # Then: Metadata included
        assert response.metadata == metadata
        assert response.error == error


class TestToolResponseSuccess:
    """Tests for ToolResponseSuccess strict variant."""

    def test_success_response_requires_data(self):
        """Test that ToolResponseSuccess requires data field."""
        # Given: Success=True but no data
        # When/Then: Should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            ToolResponseSuccess(success=True)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("data",) and e["type"] == "missing" for e in errors)

    def test_success_response_enforces_success_true(self):
        """Test that ToolResponseSuccess enforces success=True."""
        # Given: Valid data
        data = {"count": 5}

        # When: Create with success=True (explicit or default)
        response = ToolResponseSuccess(success=True, data=data)

        # Then: success is True
        assert response.success is True
        assert response.data == data

    def test_success_response_rejects_success_false(self):
        """Test that ToolResponseSuccess rejects success=False."""
        # Given: success=False
        # When/Then: Should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            ToolResponseSuccess(success=False, data={"count": 5})

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("success",) for e in errors)


class TestToolResponseError:
    """Tests for ToolResponseError strict variant."""

    def test_error_response_requires_error_field(self):
        """Test that ToolResponseError requires error field."""
        # Given: Error response without error field
        # When/Then: Should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            ToolResponseError(success=False, message="Something went wrong")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("error",) and e["type"] == "missing" for e in errors)

    def test_error_response_enforces_success_false(self):
        """Test that ToolResponseError enforces success=False."""
        # Given: Valid error data
        error = "NOT_FOUND"
        message = "Resource not found"

        # When: Create with success=False (explicit or default)
        response = ToolResponseError(success=False, error=error, message=message)

        # Then: success is False
        assert response.success is False
        assert response.error == error

    def test_error_response_rejects_success_true(self):
        """Test that ToolResponseError rejects success=True."""
        # Given: success=True
        # When/Then: Should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            ToolResponseError(success=True, error="ERROR", message="Error message")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("success",) for e in errors)

    def test_error_response_with_message(self):
        """Test error response with message."""
        # Given: Error with message
        error = "VALIDATION_ERROR"
        message = "Invalid parameter 'query'"

        # When: Create error response
        response = ToolResponseError(success=False, error=error, message=message)

        # Then: Both fields present
        assert response.error == error
        assert response.message == message


class TestToolResponseRoundTrip:
    """Tests for JSON serialization/deserialization round trips."""

    def test_success_response_round_trip(self):
        """Test success response survives JSON round trip."""
        # Given: Success response
        original = ToolResponse.success_response(
            data={"contacts": [{"name": "Jean"}]}, message="Found 1 contact"
        )

        # When: Serialize and deserialize
        json_str = original.model_dump_json()
        parsed_dict = json.loads(json_str)
        restored = ToolResponse(**parsed_dict)

        # Then: Same data
        assert restored.success == original.success
        assert restored.data == original.data
        assert restored.message == original.message

    def test_error_response_round_trip(self):
        """Test error response survives JSON round trip."""
        # Given: Error response
        original = ToolResponse.error_response(error="NOT_FOUND", message="Contact not found")

        # When: Serialize and deserialize
        json_str = original.model_dump_json()
        parsed_dict = json.loads(json_str)
        restored = ToolResponse(**parsed_dict)

        # Then: Same data
        assert restored.success == original.success
        assert restored.error == original.error
        assert restored.message == original.message

    def test_complex_nested_data_round_trip(self):
        """Test response with complex nested data."""
        # Given: Response with nested structures
        complex_data = {
            "contacts": [
                {"name": "Jean", "emails": ["jean@example.com"], "phones": [{"number": "123"}]},
                {"name": "Marie", "emails": [], "phones": []},
            ],
            "total": 2,
            "metadata": {"query": "Jean OR Marie", "execution_time_ms": 150},
        }
        original = ToolResponse.success_response(data=complex_data)

        # When: Serialize and deserialize
        json_str = original.model_dump_json()
        parsed_dict = json.loads(json_str)
        restored = ToolResponse(**parsed_dict)

        # Then: Complex data preserved
        assert restored.data == complex_data
        assert len(restored.data["contacts"]) == 2
        assert restored.data["contacts"][0]["emails"][0] == "jean@example.com"
