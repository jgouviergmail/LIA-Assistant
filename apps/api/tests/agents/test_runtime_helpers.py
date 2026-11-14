"""
Unit tests for runtime helpers.

Phase 3.2.8: Tests for helper functions that eliminate code duplication.
Migrated to UnifiedToolOutput (2025-12-29)
"""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.core.i18n_api_messages import APIMessages
from src.core.tool_context_scope import ChildToolContextScope
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    ValidatedRuntimeConfig,
    handle_tool_exception,
    validate_runtime_config,
)
from tests.helpers.runtime_context import (
    DEFAULT_TEST_USER_ID,
    make_contextless_tool_runtime,
    make_tool_runtime,
)


class TestValidateRuntimeConfig:
    """Tests for validate_runtime_config helper."""

    def test_valid_runtime_config(self):
        """Test successful validation with all required fields."""
        # Given: the runtime the graph injects — identity AND thread in the TYPED
        # context (ADR-231). The bag is made to DISAGREE on purpose: with the same
        # thread on both planes this would pass against a reader of either.
        store = Mock()
        runtime = make_tool_runtime(
            thread_id="sess456",
            configurable={"thread_id": "stale-thread-from-the-bag"},
            store=store,
        )

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns ValidatedRuntimeConfig
        assert isinstance(result, ValidatedRuntimeConfig)
        assert result.user_id == str(DEFAULT_TEST_USER_ID)
        assert result.session_id == "sess456"  # The context's thread, as the tool-context scope
        assert result.store is store

    def test_a_root_run_is_scoped_by_its_thread_and_a_child_under_its_parent(self):
        """The scope a tool's context is filed under says whose run it is.

        A root run's thread IS its runtime: the scope is the thread itself. A
        synthetic child thread (a sub-agent's) is filed under the runtime that
        spawned it, so the parent's cleanup finds it — never guessed from the
        thread's shape.
        """
        # Given: a root run, then a child thread of the same runtime
        parent = uuid4()
        root = make_tool_runtime(thread_id=str(parent), runtime_id=parent, store=Mock())
        child = make_tool_runtime(thread_id="child-thread", runtime_id=parent, store=Mock())

        # When: Validate both
        root_config = validate_runtime_config(root, "test_tool")
        child_config = validate_runtime_config(child, "test_tool")

        # Then
        assert isinstance(root_config, ValidatedRuntimeConfig)
        assert root_config.session_id == str(parent)
        assert isinstance(child_config, ValidatedRuntimeConfig)
        assert child_config.session_id == ChildToolContextScope(parent, "child-thread")

    def test_missing_run_context(self):
        """A tool invoked outside a run has no identity at all.

        Since ADR-231 the acting user lives in a typed context whose ``user_id``
        is mandatory, so "no user" is not a missing key any more — it is the
        absence of the context itself. That is the case this test now names.
        """
        # Given: a runtime with no run context
        runtime = make_contextless_tool_runtime(configurable={"thread_id": "sess456"}, store=Mock())

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns error UnifiedToolOutput
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
        assert "context" in result.message

    def test_missing_session_id(self):
        """Test validation fails when thread_id (session_id) is missing."""
        # Given: a context that names no thread. The identity is present — this
        # is about the run's thread, which the context carries; a thread left in
        # the bag does not stand in for it.
        runtime = make_tool_runtime(
            thread_id="", configurable={"thread_id": "sess456"}, store=Mock()
        )

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns error UnifiedToolOutput
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
        assert "thread_id" in result.message
        # The message names where the thread is read. The bag HOLDS one here, so
        # advice to put it there would send the reader nowhere.
        assert "LiaRuntimeContext.thread_id" in result.message
        assert "configurable={" not in result.message

    def test_missing_store(self):
        """Test validation fails when store is None."""
        # Given: Runtime without store
        runtime = make_tool_runtime(configurable={"thread_id": "sess456"}, store=None)

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns error UnifiedToolOutput
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
        assert "Store" in result.message

    def test_missing_configurable_dict_is_not_read(self):
        """Nothing is taken from config.configurable: the context alone decides."""
        # Given: Runtime with None configurable — the context is there, the
        # plumbing is not. Identity and thread both come from the context, so
        # there is no lookup left to fail.
        store = Mock()
        runtime = make_tool_runtime(thread_id="sess456", store=store)
        runtime.config["configurable"] = None

        # When: Validate config
        result = validate_runtime_config(runtime, "test_tool")

        # Then: Returns ValidatedRuntimeConfig, read from the context
        assert isinstance(result, ValidatedRuntimeConfig)
        assert result.user_id == str(DEFAULT_TEST_USER_ID)
        assert result.session_id == "sess456"
        assert result.store is store


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
        assert result.error_code == ToolErrorCode.INTERNAL_ERROR
        assert "ValueError" in result.message
        assert result.metadata["error_type"] == "ValueError"
        # An exception's text may quote a provider, a URL or a mailbox: the
        # output names its type, never its words (test_tool_failure_privacy).
        assert result.metadata["error_message"] == APIMessages.internal_error("ValueError")
        assert "Invalid input" not in result.model_dump_json()

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
        assert result.error_code == ToolErrorCode.INTERNAL_ERROR
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
            assert result.metadata["error_message"] == APIMessages.internal_error(
                type(exc).__name__
            )
            assert str(exc) not in result.model_dump_json()


class TestHelperIntegration:
    """Integration tests showing helper usage in realistic scenarios."""

    def test_typical_tool_workflow(self):
        """Test typical workflow: validate config → use it → handle errors."""
        # Given: Valid runtime, its thread carried by the typed context
        store = Mock()
        runtime = make_tool_runtime(thread_id="sess456", store=store)

        # Step 1: Validate runtime config
        config = validate_runtime_config(runtime, "my_tool")

        # Then: Should succeed
        assert isinstance(config, ValidatedRuntimeConfig)

        # Step 2: Simulate using the config
        user_id = config.user_id
        session_id = config.session_id
        store = config.store

        assert user_id == str(DEFAULT_TEST_USER_ID)
        assert session_id == "sess456"
        assert store is runtime.store

    def test_early_return_on_validation_error(self):
        """Test early return pattern when validation fails."""
        # Given: Invalid runtime (no run context, hence no identity)
        runtime = make_contextless_tool_runtime(configurable={"thread_id": "sess456"}, store=Mock())

        # When: Validate (would be in tool code)
        config = validate_runtime_config(runtime, "my_tool")

        # Then: Can immediately return error response. Asserted OUTSIDE the
        # isinstance guard: written inside it, the whole block was skipped the
        # day validation started succeeding, and the test passed vacuously.
        assert isinstance(config, UnifiedToolOutput)
        assert config.success is False
        assert config.error_code == "configuration_error"
        assert "context" in config.message

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
        assert result.error_code == ToolErrorCode.INTERNAL_ERROR
        assert "ConnectionError" in result.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
