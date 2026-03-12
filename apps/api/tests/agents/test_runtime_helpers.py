"""
Unit tests for runtime helpers.

Phase 3.2.8: Tests for helper functions that eliminate code duplication.
Migrated to UnifiedToolOutput (2025-12-29)
"""

from unittest.mock import Mock

import pytest

from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    ValidatedRuntimeConfig,
    handle_tool_exception,
    validate_runtime_config,
)


class TestValidateRuntimeConfig:
    """Tests for validate_runtime_config helper."""

    def test_valid_runtime_config(self):
        """Test successful validation with all required fields."""
        # Given: Valid runtime with all fields (using LangGraph v1.0 standard: thread_id)
        runtime = Mock()
        runtime.config = {
            "configurable": {
                "user_id": "user123",
                "thread_id": "sess456",  # LangGraph v1.0 uses thread_id
            }
        }
        runtime.store = Mock()

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns ValidatedRuntimeConfig
        assert isinstance(result, ValidatedRuntimeConfig)
        assert result.user_id == "user123"
        assert result.session_id == "sess456"  # Normalized internally to session_id
        assert result.store is runtime.store

    def test_missing_user_id(self):
        """Test validation fails when user_id is missing."""
        # Given: Runtime without user_id
        runtime = Mock()
        runtime.config = {"configurable": {"session_id": "sess456"}}
        runtime.store = Mock()

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns error UnifiedToolOutput
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
        assert "user_id" in result.message

    def test_missing_session_id(self):
        """Test validation fails when thread_id (session_id) is missing."""
        # Given: Runtime without thread_id
        runtime = Mock()
        runtime.config = {"configurable": {"user_id": "user123"}}
        runtime.store = Mock()

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns error UnifiedToolOutput
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
        assert "thread_id" in result.message  # Updated to match new error message

    def test_missing_store(self):
        """Test validation fails when store is None."""
        # Given: Runtime without store
        runtime = Mock()
        runtime.config = {
            "configurable": {
                "user_id": "user123",
                "thread_id": "sess456",  # Using thread_id (LangGraph v1.0)
            }
        }
        runtime.store = None

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns error UnifiedToolOutput
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
        assert "Store" in result.message

    def test_missing_configurable_dict(self):
        """Test validation fails when config.configurable is None."""
        # Given: Runtime with None configurable
        runtime = Mock()
        runtime.config = {"configurable": None}
        runtime.store = Mock()

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns error UnifiedToolOutput (user_id missing)
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"


class TestHandleToolException:
    """Tests for handle_tool_exception helper."""

    def test_handle_exception_without_context(self):
        """Test exception handling without context."""
        # Given: An exception
        exception = ValueError("Invalid input")

        # When: Handle exception
        result = handle_tool_exception(exception, "test_tool")

        # Then: Returns error UnifiedToolOutput
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "internal_error"
        assert "ValueError" in result.message
        assert result.metadata["error_type"] == "ValueError"
        assert result.metadata["error_message"] == "Invalid input"

    def test_handle_exception_with_context(self):
        """Test exception handling with context."""
        # Given: An exception with context
        exception = ConnectionError("Timeout")
        context = {"query": "john", "max_results": 10}

        # When: Handle exception
        result = handle_tool_exception(exception, "search_tool", context)

        # Then: Returns error UnifiedToolOutput with metadata
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "internal_error"
        assert "ConnectionError" in result.message
        assert result.metadata["error_type"] == "ConnectionError"

    def test_handle_different_exception_types(self):
        """Test handling different exception types."""
        exceptions = [
            ValueError("Bad value"),
            KeyError("Missing key"),
            TypeError("Wrong type"),
            RuntimeError("Runtime issue"),
        ]

        for exc in exceptions:
            # When: Handle each exception
            result = handle_tool_exception(exc, "test_tool")

            # Then: Error type is captured
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is False
            assert result.metadata["error_type"] == type(exc).__name__
            assert result.metadata["error_message"] == str(exc)


class TestHelperIntegration:
    """Integration tests showing helper usage in realistic scenarios."""

    def test_typical_tool_workflow(self):
        """Test typical workflow: validate config → use it → handle errors."""
        # Given: Valid runtime
        runtime = Mock()
        runtime.config = {
            "configurable": {
                "user_id": "user123",
                "thread_id": "sess456",  # Using thread_id (LangGraph v1.0)
            }
        }
        runtime.store = Mock()

        # Step 1: Validate runtime config
        config = validate_runtime_config(runtime, "my_tool")

        # Then: Should succeed
        assert isinstance(config, ValidatedRuntimeConfig)

        # Step 2: Simulate using the config
        user_id = config.user_id
        session_id = config.session_id
        store = config.store

        assert user_id == "user123"
        assert session_id == "sess456"
        assert store is runtime.store

    def test_early_return_on_validation_error(self):
        """Test early return pattern when validation fails."""
        # Given: Invalid runtime (missing user_id)
        runtime = Mock()
        runtime.config = {"configurable": {"thread_id": "sess456"}}  # Using thread_id
        runtime.store = Mock()

        # When: Validate (would be in tool code)
        config = validate_runtime_config(runtime, "my_tool")

        # Then: Can immediately return error response
        if isinstance(config, UnifiedToolOutput):
            # Early return pattern - UnifiedToolOutput can be returned directly
            assert config.success is False
            assert config.error_code == "configuration_error"
            assert "user_id" in config.message
            # In real tool code: return config

    def test_exception_handling_in_tool(self):
        """Test exception handling pattern in tool."""

        # Given: Simulated tool execution that raises exception
        def simulated_tool_logic():
            raise ConnectionError("API timeout")

        # When: Tool executes and catches exception
        try:
            simulated_tool_logic()
        except Exception as e:
            result = handle_tool_exception(e, "my_tool", {"query": "test"})

        # Then: Returns proper error response
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "internal_error"
        assert "ConnectionError" in result.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
