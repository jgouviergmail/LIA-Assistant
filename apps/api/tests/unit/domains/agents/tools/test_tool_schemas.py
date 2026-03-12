"""
Unit tests for tools/schemas.py.

Phase: Session 17 - Tools Modules (tools/schemas)
Created: 2025-11-20

Focus: ToolResponse Pydantic model and helper methods
Target Coverage: 83% → 100% (4 missing lines: 107-108, 136, 161)
"""

import json

import pytest
from pydantic import ValidationError

from src.domains.agents.tools.schemas import (
    ToolResponse,
    ToolResponseError,
    ToolResponseSuccess,
)


class TestToolResponse:
    """Tests for ToolResponse base model."""

    def test_tool_response_success_basic(self):
        """Test ToolResponse with success=True and data."""
        response = ToolResponse(success=True, data={"count": 5, "items": []})

        assert response.success is True
        assert response.data == {"count": 5, "items": []}
        assert response.error is None
        assert response.message is None
        assert response.metadata is None

    def test_tool_response_success_with_message(self):
        """Test ToolResponse success with optional message."""
        response = ToolResponse(
            success=True, data={"result": "OK"}, message="Operation completed successfully"
        )

        assert response.success is True
        assert response.data == {"result": "OK"}
        assert response.message == "Operation completed successfully"
        assert response.error is None

    def test_tool_response_success_with_metadata(self):
        """Test ToolResponse success with optional metadata."""
        metadata = {"turn_id": "turn_123", "timestamp": "2025-01-20T12:00:00Z"}
        response = ToolResponse(success=True, data={"result": "OK"}, metadata=metadata)

        assert response.success is True
        assert response.metadata == metadata

    def test_tool_response_error_basic(self):
        """Test ToolResponse with success=False and error."""
        response = ToolResponse(success=False, error="NOT_FOUND", message="Resource not found")

        assert response.success is False
        assert response.error == "NOT_FOUND"
        assert response.message == "Resource not found"
        assert response.data is None
        assert response.metadata is None

    def test_tool_response_error_with_metadata(self):
        """Test ToolResponse error with optional metadata."""
        metadata = {"stack_trace": "...", "request_id": "req_456"}
        response = ToolResponse(
            success=False, error="INTERNAL_ERROR", message="Server error", metadata=metadata
        )

        assert response.success is False
        assert response.error == "INTERNAL_ERROR"
        assert response.metadata == metadata

    def test_model_dump_json_excludes_none_by_default(self):
        """Test that model_dump_json excludes None fields by default (Lines 107-108)."""
        response = ToolResponse(success=True, data={"count": 5})

        # Call model_dump_json (covers lines 107-108)
        json_str = response.model_dump_json()

        # Parse JSON to verify structure
        parsed = json.loads(json_str)

        # None fields should be excluded from JSON
        assert "success" in parsed
        assert parsed["success"] is True
        assert "data" in parsed
        assert parsed["data"] == {"count": 5}
        # None fields should NOT be in JSON
        assert "error" not in parsed
        assert "message" not in parsed
        assert "metadata" not in parsed

    def test_model_dump_json_includes_none_when_override(self):
        """Test that model_dump_json can include None when exclude_none=False."""
        response = ToolResponse(success=True, data={"count": 5})

        # Override exclude_none behavior
        json_str = response.model_dump_json(exclude_none=False)
        parsed = json.loads(json_str)

        # None fields should be included when exclude_none=False
        assert "error" in parsed
        assert parsed["error"] is None
        assert "message" in parsed
        assert parsed["message"] is None
        assert "metadata" in parsed
        assert parsed["metadata"] is None

    def test_model_dump_json_with_all_fields(self):
        """Test model_dump_json when all fields are populated."""
        response = ToolResponse(
            success=True,
            data={"result": "OK"},
            message="Success",
            metadata={"time": "12:00"},
        )

        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        # All non-None fields should be present
        assert parsed["success"] is True
        assert parsed["data"] == {"result": "OK"}
        assert parsed["message"] == "Success"
        assert parsed["metadata"] == {"time": "12:00"}
        # error is None, should be excluded
        assert "error" not in parsed


class TestToolResponseSuccessResponse:
    """Tests for ToolResponse.success_response() class method."""

    def test_success_response_basic(self):
        """Test success_response() creates success ToolResponse (Line 136)."""
        # Call success_response class method (covers line 136)
        response = ToolResponse.success_response(data={"contacts": [{"name": "Jean"}]})

        assert isinstance(response, ToolResponse)
        assert response.success is True
        assert response.data == {"contacts": [{"name": "Jean"}]}
        assert response.error is None
        assert response.message is None
        assert response.metadata is None

    def test_success_response_with_message(self):
        """Test success_response() with optional message."""
        response = ToolResponse.success_response(data={"count": 10}, message="Found 10 contacts")

        assert response.success is True
        assert response.data == {"count": 10}
        assert response.message == "Found 10 contacts"
        assert response.error is None

    def test_success_response_with_metadata(self):
        """Test success_response() with optional metadata."""
        metadata = {"source": "cache", "cache_age": 120}
        response = ToolResponse.success_response(
            data={"result": "OK"}, message="Cache hit", metadata=metadata
        )

        assert response.success is True
        assert response.data == {"result": "OK"}
        assert response.message == "Cache hit"
        assert response.metadata == metadata

    def test_success_response_with_all_fields(self):
        """Test success_response() with all optional fields."""
        response = ToolResponse.success_response(
            data={"emails": []},
            message="No emails found",
            metadata={"query": "label:inbox"},
        )

        assert response.success is True
        assert response.data == {"emails": []}
        assert response.message == "No emails found"
        assert response.metadata == {"query": "label:inbox"}

    def test_success_response_serialization(self):
        """Test that success_response() result serializes correctly."""
        response = ToolResponse.success_response(data={"count": 5})

        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["success"] is True
        assert parsed["data"] == {"count": 5}
        # None fields excluded
        assert "error" not in parsed


class TestToolResponseErrorResponse:
    """Tests for ToolResponse.error_response() class method."""

    def test_error_response_basic(self):
        """Test error_response() creates error ToolResponse (Line 161)."""
        # Call error_response class method (covers line 161)
        response = ToolResponse.error_response(
            error="NOT_FOUND", message="Contact 'Jean' not found"
        )

        assert isinstance(response, ToolResponse)
        assert response.success is False
        assert response.error == "NOT_FOUND"
        assert response.message == "Contact 'Jean' not found"
        assert response.data is None
        assert response.metadata is None

    def test_error_response_with_metadata(self):
        """Test error_response() with optional metadata."""
        metadata = {"request_id": "req_789", "trace_id": "trace_abc"}
        response = ToolResponse.error_response(
            error="RATE_LIMIT_EXCEEDED",
            message="Too many requests",
            metadata=metadata,
        )

        assert response.success is False
        assert response.error == "RATE_LIMIT_EXCEEDED"
        assert response.message == "Too many requests"
        assert response.metadata == metadata

    def test_error_response_different_error_codes(self):
        """Test error_response() with various error codes."""
        # Test multiple error code patterns
        errors = [
            ("VALIDATION_ERROR", "Invalid input parameters"),
            ("CONNECTOR_DISABLED", "Google connector not enabled"),
            ("INTERNAL_ERROR", "Unexpected server error"),
            ("UNAUTHORIZED", "Authentication required"),
        ]

        for error_code, msg in errors:
            response = ToolResponse.error_response(error=error_code, message=msg)

            assert response.success is False
            assert response.error == error_code
            assert response.message == msg
            assert response.data is None

    def test_error_response_serialization(self):
        """Test that error_response() result serializes correctly."""
        response = ToolResponse.error_response(error="NOT_FOUND", message="Resource not found")

        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["success"] is False
        assert parsed["error"] == "NOT_FOUND"
        assert parsed["message"] == "Resource not found"
        # data is None, should be excluded
        assert "data" not in parsed


class TestToolResponseSuccess:
    """Tests for ToolResponseSuccess variant."""

    def test_tool_response_success_variant(self):
        """Test ToolResponseSuccess enforces success=True."""
        response = ToolResponseSuccess(success=True, data={"result": "OK"})

        assert response.success is True
        assert response.data == {"result": "OK"}
        assert isinstance(response, ToolResponse)

    def test_tool_response_success_default_success_true(self):
        """Test ToolResponseSuccess defaults success to True."""
        response = ToolResponseSuccess(data={"count": 5})

        assert response.success is True
        assert response.data == {"count": 5}

    def test_tool_response_success_requires_data(self):
        """Test ToolResponseSuccess requires data field."""
        # data is required (no default)
        with pytest.raises(ValidationError):
            ToolResponseSuccess(success=True)


class TestToolResponseError:
    """Tests for ToolResponseError variant."""

    def test_tool_response_error_variant(self):
        """Test ToolResponseError enforces success=False."""
        response = ToolResponseError(success=False, error="NOT_FOUND", message="Resource not found")

        assert response.success is False
        assert response.error == "NOT_FOUND"
        assert response.message == "Resource not found"
        assert isinstance(response, ToolResponse)

    def test_tool_response_error_default_success_false(self):
        """Test ToolResponseError defaults success to False."""
        response = ToolResponseError(error="INTERNAL_ERROR", message="Server error")

        assert response.success is False
        assert response.error == "INTERNAL_ERROR"

    def test_tool_response_error_requires_error_field(self):
        """Test ToolResponseError requires error field."""
        # error is required (no default)
        with pytest.raises(ValidationError):
            ToolResponseError(success=False, message="Some error")


class TestToolResponseIntegration:
    """Integration tests for ToolResponse usage patterns."""

    def test_success_to_json_workflow(self):
        """Test typical success workflow: create → serialize → parse."""
        # Create success response
        response = ToolResponse.success_response(
            data={"contacts": [{"name": "Jean", "email": "jean@example.com"}]},
            message="Found 1 contact",
        )

        # Serialize to JSON
        json_str = response.model_dump_json()

        # Parse back
        parsed = json.loads(json_str)

        # Verify structure
        assert parsed["success"] is True
        assert parsed["message"] == "Found 1 contact"
        assert len(parsed["data"]["contacts"]) == 1
        assert parsed["data"]["contacts"][0]["name"] == "Jean"

    def test_error_to_json_workflow(self):
        """Test typical error workflow: create → serialize → parse."""
        # Create error response
        response = ToolResponse.error_response(
            error="NOT_FOUND", message="Contact 'Jean' not found"
        )

        # Serialize to JSON
        json_str = response.model_dump_json()

        # Parse back
        parsed = json.loads(json_str)

        # Verify structure
        assert parsed["success"] is False
        assert parsed["error"] == "NOT_FOUND"
        assert parsed["message"] == "Contact 'Jean' not found"
        assert "data" not in parsed

    def test_response_in_tool_pattern(self):
        """Test ToolResponse usage pattern in tools."""

        def mock_tool_success():
            """Simulate successful tool execution."""
            result = {"count": 5, "items": ["a", "b", "c"]}
            response = ToolResponse.success_response(data=result)
            return response.model_dump_json()

        def mock_tool_error():
            """Simulate failed tool execution."""
            response = ToolResponse.error_response(
                error="VALIDATION_ERROR", message="Invalid query parameter"
            )
            return response.model_dump_json()

        # Test success path
        success_json = mock_tool_success()
        success_parsed = json.loads(success_json)
        assert success_parsed["success"] is True
        assert success_parsed["data"]["count"] == 5

        # Test error path
        error_json = mock_tool_error()
        error_parsed = json.loads(error_json)
        assert error_parsed["success"] is False
        assert error_parsed["error"] == "VALIDATION_ERROR"
