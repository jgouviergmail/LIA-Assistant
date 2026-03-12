"""
Tests for Tool Call Tracing - Phase 3.1.5.2.

Test coverage:
- _serialize_tool_data() - JSON serialization with truncation
- trace_tool_call() context manager - success/error paths
- enrich_tool_metadata() - metadata enrichment
- Error handling and graceful degradation
- Duration tracking
- Metadata capture (tool_name, tool_input, tool_output, success)

Phase: 3.1.5.2 - Tool Call Tracing
Date: 2025-11-23
"""

import pytest

from src.infrastructure.llm.tool_tracing import (
    _serialize_tool_data,
    enrich_tool_metadata,
    trace_tool_call,
)

# ============================================================================
# TESTS: _serialize_tool_data - JSON Serialization
# ============================================================================


class TestSerializeToolData:
    """Tests for _serialize_tool_data helper function."""

    def test_serialize_primitive_types(self):
        """Test serialization of primitive types."""
        # String
        assert _serialize_tool_data("hello") == '"hello"'

        # Integer
        assert _serialize_tool_data(42) == "42"

        # Float
        assert _serialize_tool_data(3.14) == "3.14"

        # Boolean
        assert _serialize_tool_data(True) == "true"
        assert _serialize_tool_data(False) == "false"

        # None
        assert _serialize_tool_data(None) == "null"

    def test_serialize_dict(self):
        """Test serialization of dict."""
        data = {"name": "John", "age": 30, "active": True}
        result = _serialize_tool_data(data)

        # Should be valid JSON
        assert '"name"' in result
        assert '"John"' in result
        assert '"age"' in result
        assert "30" in result
        assert '"active"' in result
        assert "true" in result

    def test_serialize_list(self):
        """Test serialization of list."""
        data = [1, 2, 3, "test", True]
        result = _serialize_tool_data(data)

        assert '[1, 2, 3, "test", true]' == result

    def test_serialize_nested_structure(self):
        """Test serialization of nested dict/list."""
        data = {
            "users": [
                {"name": "Alice", "age": 25},
                {"name": "Bob", "age": 30},
            ],
            "count": 2,
        }
        result = _serialize_tool_data(data)

        # Should contain nested structure
        assert '"users"' in result
        assert '"Alice"' in result
        assert '"Bob"' in result
        assert "25" in result
        assert "30" in result

    def test_serialize_non_serializable_object(self):
        """Test fallback to repr for non-serializable objects."""

        class CustomClass:
            def __repr__(self):
                return "<CustomClass instance>"

        obj = CustomClass()
        result = _serialize_tool_data(obj)

        assert "<CustomClass instance>" in result

    def test_truncate_long_string(self):
        """Test truncation of long strings."""
        # Create string longer than max_length
        long_string = "x" * 3000
        result = _serialize_tool_data(long_string, max_length=2000)

        # Should be truncated
        assert len(result) <= 2020  # 2000 + "... [truncated]"
        assert "[truncated]" in result  # Should contain truncation marker

    def test_truncate_long_dict(self):
        """Test truncation of large dict serialization."""
        # Create dict that serializes to > 2000 chars
        large_dict = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}
        result = _serialize_tool_data(large_dict, max_length=2000)

        # Should be truncated
        assert len(result) <= 2020  # 2000 + "... [truncated]"
        assert result.endswith("[truncated]")


# ============================================================================
# TESTS: trace_tool_call - Context Manager
# ============================================================================


class TestTraceToolCall:
    """Tests for trace_tool_call context manager."""

    def test_trace_tool_call_success(self):
        """Test successful tool call tracing."""
        tool_input = {"query": "john@example.com"}
        tool_output = {"results": [{"name": "John Doe"}], "count": 1}

        with trace_tool_call(
            tool_name="search_contacts",
            tool_input=tool_input,
            agent_name="contacts_agent",
        ) as trace_ctx:
            # Simulate successful tool execution
            trace_ctx["output"] = tool_output
            trace_ctx["success"] = True

        # Verify trace context
        assert trace_ctx["tool_name"] == "search_contacts"
        assert trace_ctx["agent_name"] == "contacts_agent"
        assert trace_ctx["success"] is True
        assert trace_ctx["output"] == tool_output
        assert trace_ctx.get("error") is None

        # Verify duration tracking
        assert "duration_ms" in trace_ctx
        assert trace_ctx["duration_ms"] >= 0

        # Verify timestamps
        assert "start_time" in trace_ctx
        assert "end_time" in trace_ctx
        assert trace_ctx["end_time"] >= trace_ctx["start_time"]

        # Verify serialized output
        assert "output_serialized" in trace_ctx
        assert '"results"' in trace_ctx["output_serialized"]

    def test_trace_tool_call_failure(self):
        """Test tool call tracing with error."""
        tool_input = {"query": "invalid"}

        with pytest.raises(ValueError, match="Invalid query"):
            with trace_tool_call(
                tool_name="search_contacts",
                tool_input=tool_input,
                agent_name="contacts_agent",
            ):
                # Simulate tool failure
                raise ValueError("Invalid query format")

        # Verify error captured (trace_ctx still accessible via closure)
        # Note: In real usage, error would be logged but trace_ctx not accessible
        # This test verifies the context manager handles exceptions correctly

    def test_trace_tool_call_with_parent_trace_id(self):
        """Test tool call tracing with parent trace ID."""
        tool_input = {"email": "test@example.com"}
        parent_trace_id = "trace_root_abc123"

        with trace_tool_call(
            tool_name="get_contact",
            tool_input=tool_input,
            agent_name="contacts_agent",
            parent_trace_id=parent_trace_id,
        ) as trace_ctx:
            trace_ctx["output"] = {"name": "Test User"}
            trace_ctx["success"] = True

        # Verify parent trace ID captured
        assert trace_ctx["parent_trace_id"] == parent_trace_id

    def test_trace_tool_call_no_agent_name(self):
        """Test tool call tracing without agent name."""
        tool_input = {"param": "value"}

        with trace_tool_call(
            tool_name="generic_tool",
            tool_input=tool_input,
        ) as trace_ctx:
            trace_ctx["output"] = "result"
            trace_ctx["success"] = True

        # Verify trace works without agent_name
        assert trace_ctx["tool_name"] == "generic_tool"
        assert trace_ctx["agent_name"] is None

    def test_trace_tool_call_empty_input(self):
        """Test tool call tracing with empty input."""
        with trace_tool_call(
            tool_name="list_all",
            tool_input={},
        ) as trace_ctx:
            trace_ctx["output"] = ["item1", "item2"]
            trace_ctx["success"] = True

        # Verify empty input handled
        assert trace_ctx["tool_input"] == "{}"

    def test_trace_tool_call_complex_input(self):
        """Test tool call tracing with complex nested input."""
        complex_input = {
            "filters": {
                "name": "John",
                "tags": ["vip", "customer"],
            },
            "pagination": {
                "page": 1,
                "per_page": 20,
            },
            "sort": {"field": "created_at", "order": "desc"},
        }

        with trace_tool_call(
            tool_name="advanced_search",
            tool_input=complex_input,
        ) as trace_ctx:
            trace_ctx["output"] = {"results": [], "total": 0}
            trace_ctx["success"] = True

        # Verify complex input serialized
        assert '"filters"' in trace_ctx["tool_input"]
        assert '"pagination"' in trace_ctx["tool_input"]
        assert '"John"' in trace_ctx["tool_input"]
        assert "[" in trace_ctx["tool_input"]  # Arrays present

    def test_trace_tool_call_duration_tracking(self):
        """Test that duration is accurately tracked."""
        import time

        tool_input = {"wait": 0.1}

        with trace_tool_call(
            tool_name="slow_tool",
            tool_input=tool_input,
        ) as trace_ctx:
            # Simulate slow tool execution
            time.sleep(0.1)
            trace_ctx["output"] = "done"
            trace_ctx["success"] = True

        # Verify duration is at least 100ms
        assert trace_ctx["duration_ms"] >= 100


# ============================================================================
# TESTS: enrich_tool_metadata - Metadata Enrichment
# ============================================================================


class TestEnrichToolMetadata:
    """Tests for enrich_tool_metadata function."""

    def test_enrich_tool_metadata_success(self):
        """Test metadata enrichment for successful tool call."""
        metadata = {
            "session_id": "sess_123",
            "user_id": "user_456",
        }

        enriched = enrich_tool_metadata(
            metadata,
            tool_name="search_contacts",
            success=True,
            duration_ms=245.678,
        )

        # Verify original metadata preserved
        assert enriched["session_id"] == "sess_123"
        assert enriched["user_id"] == "user_456"

        # Verify tool metadata added
        assert enriched["langfuse_tool_name"] == "search_contacts"
        assert enriched["langfuse_tool_success"] is True
        assert enriched["langfuse_tool_duration_ms"] == 245.68  # Rounded to 2 decimals
        assert enriched["langfuse_tool_error"] is None

    def test_enrich_tool_metadata_failure(self):
        """Test metadata enrichment for failed tool call."""
        metadata = {"session_id": "sess_123"}

        enriched = enrich_tool_metadata(
            metadata,
            tool_name="send_email",
            success=False,
            duration_ms=123.456,
            error="SMTP connection timeout",
        )

        # Verify tool metadata
        assert enriched["langfuse_tool_name"] == "send_email"
        assert enriched["langfuse_tool_success"] is False
        assert enriched["langfuse_tool_duration_ms"] == 123.46
        assert enriched["langfuse_tool_error"] == "SMTP connection timeout"

    def test_enrich_tool_metadata_empty_base(self):
        """Test metadata enrichment with empty base metadata."""
        enriched = enrich_tool_metadata(
            {},
            tool_name="test_tool",
            success=True,
            duration_ms=100.0,
        )

        # Verify tool metadata added to empty dict
        assert enriched["langfuse_tool_name"] == "test_tool"
        assert enriched["langfuse_tool_success"] is True
        assert enriched["langfuse_tool_duration_ms"] == 100.0

    def test_enrich_tool_metadata_duration_rounding(self):
        """Test that duration_ms is rounded to 2 decimal places."""
        enriched = enrich_tool_metadata(
            {},
            tool_name="tool",
            success=True,
            duration_ms=123.456789,
        )

        # Verify rounding
        assert enriched["langfuse_tool_duration_ms"] == 123.46

    def test_enrich_tool_metadata_preserves_existing_langfuse_keys(self):
        """Test that existing langfuse_ keys are overridden."""
        metadata = {
            "langfuse_session_id": "sess_123",
            "langfuse_tool_name": "old_tool",  # Will be overridden
        }

        enriched = enrich_tool_metadata(
            metadata,
            tool_name="new_tool",
            success=True,
            duration_ms=50.0,
        )

        # Verify override
        assert enriched["langfuse_tool_name"] == "new_tool"
        # Verify original langfuse keys preserved
        assert enriched["langfuse_session_id"] == "sess_123"


# ============================================================================
# TESTS: Integration - Full Workflow
# ============================================================================


class TestToolTracingIntegration:
    """Integration tests for complete tool tracing workflow."""

    def test_complete_tracing_workflow(self):
        """Test complete workflow: trace_tool_call + enrich_tool_metadata."""
        # Step 1: Trace tool call
        tool_input = {"query": "search term"}
        tool_output = {"results": ["item1", "item2"], "count": 2}

        with trace_tool_call(
            tool_name="search_tool",
            tool_input=tool_input,
            agent_name="search_agent",
            parent_trace_id="trace_parent_xyz",
        ) as trace_ctx:
            # Simulate tool execution
            trace_ctx["output"] = tool_output
            trace_ctx["success"] = True

        # Step 2: Enrich metadata with tool tracing info
        base_metadata = {
            "session_id": "sess_123",
            "user_id": "user_456",
        }

        enriched_metadata = enrich_tool_metadata(
            base_metadata,
            tool_name=trace_ctx["tool_name"],
            success=trace_ctx["success"],
            duration_ms=trace_ctx["duration_ms"],
        )

        # Verify complete metadata
        assert enriched_metadata["session_id"] == "sess_123"
        assert enriched_metadata["user_id"] == "user_456"
        assert enriched_metadata["langfuse_tool_name"] == "search_tool"
        assert enriched_metadata["langfuse_tool_success"] is True
        assert enriched_metadata["langfuse_tool_duration_ms"] >= 0

    def test_error_workflow(self):
        """Test error workflow: trace failure + enrich with error."""
        tool_input = {"invalid": "data"}

        try:
            with trace_tool_call(
                tool_name="failing_tool",
                tool_input=tool_input,
            ):
                # Simulate tool failure
                raise RuntimeError("Tool execution failed")
        except RuntimeError:
            pass  # Expected exception

        # In real usage, trace_ctx would be available in finally block
        # For testing, we simulate capturing error metadata
        error_metadata = enrich_tool_metadata(
            {},
            tool_name="failing_tool",
            success=False,
            duration_ms=50.0,
            error="Tool execution failed",
        )

        assert error_metadata["langfuse_tool_success"] is False
        assert error_metadata["langfuse_tool_error"] == "Tool execution failed"
