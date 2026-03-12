"""
Unit tests for state mutation utilities.

Tests for StateMutationContext class which provides atomic state mutations
with automatic rollback support for LangGraph nodes.
"""

from unittest.mock import patch

import pytest

from src.domains.agents.utils.state_mutation import (
    MUTABLE_FIELDS_TO_BACKUP,
    REDUCER_MANAGED_FIELDS,
    StateMutationContext,
)

# ============================================================================
# Tests for REDUCER_MANAGED_FIELDS constant
# ============================================================================


class TestReducerManagedFields:
    """Tests for REDUCER_MANAGED_FIELDS constant."""

    def test_reducer_managed_fields_contains_messages(self):
        """Test that messages field is marked as reducer-managed."""
        assert "messages" in REDUCER_MANAGED_FIELDS

    def test_reducer_managed_fields_contains_registry(self):
        """Test that registry field is marked as reducer-managed."""
        assert "registry" in REDUCER_MANAGED_FIELDS

    def test_reducer_managed_fields_contains_current_turn_registry(self):
        """Test that current_turn_registry field is marked as reducer-managed."""
        assert "current_turn_registry" in REDUCER_MANAGED_FIELDS

    def test_reducer_managed_fields_is_set(self):
        """Test that REDUCER_MANAGED_FIELDS is a set."""
        assert isinstance(REDUCER_MANAGED_FIELDS, set)

    def test_reducer_managed_fields_count(self):
        """Test expected count of reducer-managed fields."""
        assert len(REDUCER_MANAGED_FIELDS) == 3


# ============================================================================
# Tests for MUTABLE_FIELDS_TO_BACKUP constant
# ============================================================================


class TestMutableFieldsToBackup:
    """Tests for MUTABLE_FIELDS_TO_BACKUP constant."""

    def test_mutable_fields_contains_agent_results(self):
        """Test that agent_results is in mutable fields."""
        assert "agent_results" in MUTABLE_FIELDS_TO_BACKUP

    def test_mutable_fields_contains_routing_history(self):
        """Test that routing_history is in mutable fields."""
        assert "routing_history" in MUTABLE_FIELDS_TO_BACKUP

    def test_mutable_fields_contains_execution_plan(self):
        """Test that execution_plan is in mutable fields."""
        assert "execution_plan" in MUTABLE_FIELDS_TO_BACKUP

    def test_mutable_fields_contains_orchestration_plan(self):
        """Test that orchestration_plan is in mutable fields."""
        assert "orchestration_plan" in MUTABLE_FIELDS_TO_BACKUP

    def test_mutable_fields_contains_metadata(self):
        """Test that metadata is in mutable fields."""
        assert "metadata" in MUTABLE_FIELDS_TO_BACKUP

    def test_mutable_fields_contains_completed_steps(self):
        """Test that completed_steps is in mutable fields."""
        assert "completed_steps" in MUTABLE_FIELDS_TO_BACKUP

    def test_mutable_fields_contains_disambiguation_context(self):
        """Test that disambiguation_context is in mutable fields."""
        assert "disambiguation_context" in MUTABLE_FIELDS_TO_BACKUP

    def test_mutable_fields_contains_draft_context(self):
        """Test that draft_context is in mutable fields."""
        assert "draft_context" in MUTABLE_FIELDS_TO_BACKUP

    def test_mutable_fields_is_set(self):
        """Test that MUTABLE_FIELDS_TO_BACKUP is a set."""
        assert isinstance(MUTABLE_FIELDS_TO_BACKUP, set)

    def test_mutable_fields_no_overlap_with_reducer_managed(self):
        """Test that mutable fields don't overlap with reducer-managed fields."""
        overlap = MUTABLE_FIELDS_TO_BACKUP & REDUCER_MANAGED_FIELDS
        assert len(overlap) == 0, f"Overlap detected: {overlap}"

    def test_mutable_fields_count(self):
        """Test expected count of mutable fields."""
        assert len(MUTABLE_FIELDS_TO_BACKUP) == 8


# ============================================================================
# Tests for StateMutationContext.__init__
# ============================================================================


class TestStateMutationContextInit:
    """Tests for StateMutationContext initialization."""

    def test_init_sets_state(self):
        """Test that __init__ stores the state."""
        state = {"key": "value"}
        ctx = StateMutationContext(state, "test_node")
        assert ctx.state is state

    def test_init_sets_node_name(self):
        """Test that __init__ stores the node name."""
        ctx = StateMutationContext({}, "my_node")
        assert ctx.node_name == "my_node"

    def test_init_uses_default_fields_to_modify(self):
        """Test that __init__ uses MUTABLE_FIELDS_TO_BACKUP by default."""
        ctx = StateMutationContext({}, "test_node")
        assert ctx.fields_to_modify == MUTABLE_FIELDS_TO_BACKUP

    def test_init_accepts_custom_fields_to_modify(self):
        """Test that __init__ accepts custom fields_to_modify."""
        custom_fields = {"field1", "field2"}
        ctx = StateMutationContext({}, "test_node", fields_to_modify=custom_fields)
        assert ctx.fields_to_modify == custom_fields

    def test_init_creates_empty_backup(self):
        """Test that __init__ creates empty backup dict."""
        ctx = StateMutationContext({}, "test_node")
        assert ctx.backup == {}

    def test_init_creates_empty_result(self):
        """Test that __init__ creates empty result dict."""
        ctx = StateMutationContext({}, "test_node")
        assert ctx.result == {}

    def test_init_sets_entered_to_false(self):
        """Test that __init__ sets _entered flag to False."""
        ctx = StateMutationContext({}, "test_node")
        assert ctx._entered is False

    def test_init_accepts_none_fields_to_modify(self):
        """Test that __init__ treats None as default fields."""
        ctx = StateMutationContext({}, "test_node", fields_to_modify=None)
        assert ctx.fields_to_modify == MUTABLE_FIELDS_TO_BACKUP

    def test_init_treats_empty_set_as_falsy(self):
        """Test that __init__ treats empty set as falsy (uses defaults).

        Note: Python's `or` operator treats empty set as falsy,
        so `set() or MUTABLE_FIELDS_TO_BACKUP` returns the defaults.
        """
        ctx = StateMutationContext({}, "test_node", fields_to_modify=set())
        # Empty set is falsy, so defaults are used
        assert ctx.fields_to_modify == MUTABLE_FIELDS_TO_BACKUP


# ============================================================================
# Tests for StateMutationContext.__enter__
# ============================================================================


class TestStateMutationContextEnter:
    """Tests for StateMutationContext.__enter__()."""

    def test_enter_returns_self(self):
        """Test that __enter__ returns the context itself."""
        ctx = StateMutationContext({}, "test_node")
        result = ctx.__enter__()
        assert result is ctx

    def test_enter_sets_entered_to_true(self):
        """Test that __enter__ sets _entered flag to True."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()
        assert ctx._entered is True

    def test_enter_backs_up_existing_mutable_fields(self):
        """Test that __enter__ creates deep copies of existing mutable fields."""
        original_data = {"key": "value", "nested": {"inner": "data"}}
        state = {"agent_results": original_data}
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"agent_results"})
        ctx.__enter__()

        # Verify backup was created
        assert "agent_results" in ctx.backup
        assert ctx.backup["agent_results"] == original_data
        # Verify it's a deep copy (not same object)
        assert ctx.backup["agent_results"] is not original_data
        # Verify nested objects are also copied
        assert ctx.backup["agent_results"]["nested"] is not original_data["nested"]

    def test_enter_skips_reducer_managed_fields(self):
        """Test that __enter__ skips reducer-managed fields even if in fields_to_modify."""
        state = {"messages": ["msg1"], "registry": {"data": "value"}}
        # Include reducer-managed fields in fields_to_modify
        fields = {"messages", "registry", "agent_results"}
        ctx = StateMutationContext(state, "test_node", fields_to_modify=fields)

        with patch("src.domains.agents.utils.state_mutation.logger"):
            ctx.__enter__()

        # Verify reducer-managed fields are not backed up
        assert "messages" not in ctx.backup
        assert "registry" not in ctx.backup

    def test_enter_logs_skipped_reducer_fields(self):
        """Test that __enter__ logs when skipping reducer-managed fields."""
        state = {"messages": ["msg"]}
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"messages"})

        with patch("src.domains.agents.utils.state_mutation.logger") as mock_logger:
            ctx.__enter__()

        mock_logger.debug.assert_called_once()
        call_args = mock_logger.debug.call_args
        assert "skip_reducer_field" in str(call_args)

    def test_enter_skips_none_fields(self):
        """Test that __enter__ skips fields with None values."""
        state = {"agent_results": None}
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"agent_results"})
        ctx.__enter__()
        assert "agent_results" not in ctx.backup

    def test_enter_skips_missing_fields(self):
        """Test that __enter__ skips fields not present in state."""
        state = {}
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"agent_results"})
        ctx.__enter__()
        assert "agent_results" not in ctx.backup

    def test_enter_handles_list_fields(self):
        """Test that __enter__ properly backs up list fields."""
        original_list = [1, 2, {"nested": "value"}]
        state = {"completed_steps": original_list}
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"completed_steps"})
        ctx.__enter__()

        assert "completed_steps" in ctx.backup
        assert ctx.backup["completed_steps"] == original_list
        assert ctx.backup["completed_steps"] is not original_list
        # Verify nested dict in list is also copied
        assert ctx.backup["completed_steps"][2] is not original_list[2]

    def test_enter_backs_up_multiple_fields(self):
        """Test that __enter__ backs up multiple fields."""
        state = {
            "agent_results": {"a": 1},
            "metadata": {"b": 2},
            "execution_plan": {"c": 3},
        }
        fields = {"agent_results", "metadata", "execution_plan"}
        ctx = StateMutationContext(state, "test_node", fields_to_modify=fields)
        ctx.__enter__()

        assert len(ctx.backup) == 3
        assert "agent_results" in ctx.backup
        assert "metadata" in ctx.backup
        assert "execution_plan" in ctx.backup

    def test_enter_with_explicit_single_field(self):
        """Test that __enter__ with explicit single field only backs up that field."""
        state = {
            "agent_results": {"data": "value"},
            "metadata": {"other": "data"},
        }
        # Explicitly specify only one field
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"metadata"})
        ctx.__enter__()
        # Only the specified field should be backed up
        assert "metadata" in ctx.backup
        assert "agent_results" not in ctx.backup


# ============================================================================
# Tests for StateMutationContext.__exit__
# ============================================================================


class TestStateMutationContextExit:
    """Tests for StateMutationContext.__exit__()."""

    def test_exit_with_no_exception_does_not_log(self):
        """Test that __exit__ doesn't log when no exception occurred."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()

        with patch("src.domains.agents.utils.state_mutation.logger") as mock_logger:
            ctx.__exit__(None, None, None)
            mock_logger.warning.assert_not_called()

    def test_exit_with_exception_logs_warning(self):
        """Test that __exit__ logs warning when exception occurred."""
        state = {"agent_results": {"data": "value"}}
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"agent_results"})
        ctx.__enter__()
        ctx.update("agent_results", {"new": "data"})

        with patch("src.domains.agents.utils.state_mutation.logger") as mock_logger:
            ctx.__exit__(ValueError, ValueError("test error"), None)
            mock_logger.warning.assert_called_once()

            # Verify log message contains useful info
            call_args = mock_logger.warning.call_args
            assert "test_node_mutation_error" in str(call_args)

    def test_exit_does_not_suppress_exception(self):
        """Test that __exit__ returns None (doesn't suppress exception)."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()
        result = ctx.__exit__(ValueError, ValueError("test"), None)
        assert result is None

    def test_exit_logs_error_type(self):
        """Test that __exit__ logs the exception type."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()

        with patch("src.domains.agents.utils.state_mutation.logger") as mock_logger:
            ctx.__exit__(TypeError, TypeError("type error"), None)

        call_kwargs = mock_logger.warning.call_args[1]
        assert call_kwargs["error_type"] == "TypeError"

    def test_exit_logs_attempted_updates(self):
        """Test that __exit__ logs attempted updates."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()
        ctx.update("field1", "value1")
        ctx.update("field2", "value2")

        with patch("src.domains.agents.utils.state_mutation.logger") as mock_logger:
            ctx.__exit__(RuntimeError, RuntimeError("error"), None)

        call_kwargs = mock_logger.warning.call_args[1]
        assert "field1" in call_kwargs["attempted_updates"]
        assert "field2" in call_kwargs["attempted_updates"]

    def test_exit_logs_rolled_back_keys(self):
        """Test that __exit__ logs keys that would be rolled back."""
        state = {"agent_results": {"data": "value"}}
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"agent_results"})
        ctx.__enter__()
        ctx.update("agent_results", {"new": "data"})

        with patch("src.domains.agents.utils.state_mutation.logger") as mock_logger:
            ctx.__exit__(ValueError, ValueError("error"), None)

        call_kwargs = mock_logger.warning.call_args[1]
        assert "agent_results" in call_kwargs["rolled_back_keys"]


# ============================================================================
# Tests for StateMutationContext.update
# ============================================================================


class TestStateMutationContextUpdate:
    """Tests for StateMutationContext.update()."""

    def test_update_stores_value_in_result(self):
        """Test that update() stores value in result dict."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()
        ctx.update("new_field", "new_value")
        assert ctx.result["new_field"] == "new_value"

    def test_update_allows_multiple_updates(self):
        """Test that update() can be called multiple times."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()
        ctx.update("field1", "value1")
        ctx.update("field2", "value2")
        ctx.update("field3", "value3")
        assert ctx.result == {"field1": "value1", "field2": "value2", "field3": "value3"}

    def test_update_overwrites_previous_update(self):
        """Test that update() overwrites previous value for same key."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()
        ctx.update("field", "old_value")
        ctx.update("field", "new_value")
        assert ctx.result["field"] == "new_value"

    def test_update_raises_if_not_entered(self):
        """Test that update() raises RuntimeError if called outside context."""
        ctx = StateMutationContext({}, "test_node")
        with pytest.raises(RuntimeError) as exc_info:
            ctx.update("field", "value")
        assert "must be called within a 'with' block" in str(exc_info.value)

    def test_update_warns_on_reducer_managed_field(self):
        """Test that update() warns when updating reducer-managed field."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()

        with patch("src.domains.agents.utils.state_mutation.logger") as mock_logger:
            ctx.update("messages", ["new_message"])
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "reducer_field_bypass" in str(call_args)

    def test_update_warns_for_all_reducer_fields(self):
        """Test that update() warns for all reducer-managed fields."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()

        with patch("src.domains.agents.utils.state_mutation.logger") as mock_logger:
            for field in REDUCER_MANAGED_FIELDS:
                mock_logger.reset_mock()
                ctx.update(field, "value")
                mock_logger.warning.assert_called_once()

    def test_update_accepts_any_value_type(self):
        """Test that update() accepts any value type."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()
        ctx.update("string", "value")
        ctx.update("int", 42)
        ctx.update("list", [1, 2, 3])
        ctx.update("dict", {"key": "value"})
        ctx.update("none", None)
        ctx.update("bool", True)

        assert ctx.result["string"] == "value"
        assert ctx.result["int"] == 42
        assert ctx.result["list"] == [1, 2, 3]
        assert ctx.result["dict"] == {"key": "value"}
        assert ctx.result["none"] is None
        assert ctx.result["bool"] is True

    def test_update_still_stores_reducer_managed_field_in_result(self):
        """Test that update() stores reducer field in result despite warning."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()

        with patch("src.domains.agents.utils.state_mutation.logger"):
            ctx.update("messages", ["msg"])

        assert ctx.result["messages"] == ["msg"]


# ============================================================================
# Tests for StateMutationContext.get_rollback_state
# ============================================================================


class TestStateMutationContextGetRollbackState:
    """Tests for StateMutationContext.get_rollback_state()."""

    def test_get_rollback_state_returns_backup_copy(self):
        """Test that get_rollback_state() returns a copy of backup."""
        state = {"agent_results": {"data": "value"}}
        ctx = StateMutationContext(state, "test_node", fields_to_modify={"agent_results"})
        ctx.__enter__()

        rollback = ctx.get_rollback_state()
        assert rollback == ctx.backup
        # Verify it's a copy
        rollback["new_key"] = "value"
        assert "new_key" not in ctx.backup

    def test_get_rollback_state_returns_empty_dict_if_no_backup(self):
        """Test that get_rollback_state() returns empty dict if no backup."""
        ctx = StateMutationContext({}, "test_node")
        ctx.__enter__()
        assert ctx.get_rollback_state() == {}

    def test_get_rollback_state_preserves_original_values(self):
        """Test that rollback state contains original values."""
        state = {
            "agent_results": {"original": "data1"},
            "metadata": {"original": "data2"},
        }
        fields = {"agent_results", "metadata"}
        ctx = StateMutationContext(state, "test_node", fields_to_modify=fields)
        ctx.__enter__()

        # Modify the result
        ctx.update("agent_results", {"modified": "data"})
        ctx.update("metadata", {"modified": "data"})

        # Rollback should have originals
        rollback = ctx.get_rollback_state()
        assert rollback["agent_results"]["original"] == "data1"
        assert rollback["metadata"]["original"] == "data2"

    def test_get_rollback_state_callable_without_enter(self):
        """Test that get_rollback_state() works even before __enter__."""
        ctx = StateMutationContext({}, "test_node")
        # Should return empty dict (no backup yet)
        assert ctx.get_rollback_state() == {}


# ============================================================================
# Integration tests
# ============================================================================


class TestStateMutationContextIntegration:
    """Integration tests for StateMutationContext with 'with' statement."""

    def test_context_manager_basic_usage(self):
        """Test basic context manager usage pattern."""
        state = {"existing": "data"}
        with StateMutationContext(state, "test_node") as ctx:
            ctx.update("new_field", "new_value")
            ctx.update("another", 123)

        assert ctx.result == {"new_field": "new_value", "another": 123}

    def test_context_manager_with_exception(self):
        """Test context manager behavior when exception is raised."""
        state = {"agent_results": {"original": "data"}}

        try:
            with StateMutationContext(
                state, "test_node", fields_to_modify={"agent_results"}
            ) as ctx:
                ctx.update("agent_results", {"modified": "data"})
                raise ValueError("Test error")
        except ValueError:
            pass

        # Result should still contain the update
        assert ctx.result == {"agent_results": {"modified": "data"}}
        # Backup should contain original data for rollback
        assert ctx.backup == {"agent_results": {"original": "data"}}

    def test_context_manager_rollback_pattern(self):
        """Test the rollback pattern when exception occurs."""
        state = {"agent_results": {"original": "data"}, "metadata": {"version": 1}}
        fields = {"agent_results", "metadata"}

        try:
            with StateMutationContext(state, "test_node", fields_to_modify=fields) as ctx:
                ctx.update("agent_results", {"new": "data"})
                ctx.update("metadata", {"version": 2})
                # Simulate error
                raise RuntimeError("Something went wrong")
        except RuntimeError:
            # In real usage, caller would return ctx.backup instead of ctx.result
            rollback = ctx.get_rollback_state()

        assert rollback["agent_results"] == {"original": "data"}
        assert rollback["metadata"] == {"version": 1}

    def test_context_preserves_unmodified_state(self):
        """Test that context doesn't modify original state."""
        original_data = {"nested": {"deep": "value"}}
        state = {"agent_results": original_data}

        with StateMutationContext(state, "test_node", fields_to_modify={"agent_results"}) as ctx:
            ctx.update("agent_results", {"completely": "different"})

        # Original state should be unchanged
        assert state["agent_results"] is original_data
        assert state["agent_results"]["nested"]["deep"] == "value"

    def test_context_with_empty_state(self):
        """Test context manager with empty state."""
        with StateMutationContext({}, "test_node") as ctx:
            ctx.update("new_key", "new_value")

        assert ctx.result == {"new_key": "new_value"}
        assert ctx.backup == {}

    def test_context_with_nested_context_managers(self):
        """Test nested context managers (simulating node calling helper)."""
        state = {"outer": {"data": "value"}, "inner": {"data": "value"}}

        with StateMutationContext(state, "outer_node", fields_to_modify={"outer"}) as outer_ctx:
            outer_ctx.update("outer", {"modified": "outer"})

            with StateMutationContext(state, "inner_node", fields_to_modify={"inner"}) as inner_ctx:
                inner_ctx.update("inner", {"modified": "inner"})

        # Both contexts should have their updates
        assert outer_ctx.result == {"outer": {"modified": "outer"}}
        assert inner_ctx.result == {"inner": {"modified": "inner"}}

    def test_context_multiple_sequential_uses(self):
        """Test using context manager multiple times sequentially."""
        state = {"counter": {"value": 0}}

        for i in range(3):
            with StateMutationContext(state, f"node_{i}", fields_to_modify={"counter"}) as ctx:
                ctx.update("counter", {"value": i + 1})
            # Simulate applying the result
            state["counter"] = ctx.result["counter"]

        # Final state should reflect last update
        assert state["counter"]["value"] == 3

    def test_real_world_task_orchestrator_pattern(self):
        """Test real-world pattern from task orchestrator."""
        state = {
            "execution_plan": {"steps": [{"id": 1, "status": "pending"}]},
            "agent_results": {},
            "completed_steps": [],
        }
        fields = {"execution_plan", "agent_results", "completed_steps"}

        with StateMutationContext(state, "task_orchestrator", fields_to_modify=fields) as ctx:
            # Update plan
            new_plan = {"steps": [{"id": 1, "status": "completed"}]}
            ctx.update("execution_plan", new_plan)

            # Add result
            ctx.update("agent_results", {"step_1": {"success": True}})

            # Track completion
            ctx.update("completed_steps", [1])

        assert ctx.result["execution_plan"]["steps"][0]["status"] == "completed"
        assert ctx.result["agent_results"]["step_1"]["success"] is True
        assert ctx.result["completed_steps"] == [1]

    def test_immutability_of_backup_after_context_exit(self):
        """Test that backup remains unchanged after context operations."""
        state = {"data": {"value": 1, "nested": {"inner": 2}}}

        with StateMutationContext(state, "test_node", fields_to_modify={"data"}) as ctx:
            ctx.update("data", {"value": 99, "nested": {"inner": 99}})

        # Modify the result
        ctx.result["data"]["value"] = 100

        # Backup should be unaffected
        assert ctx.backup["data"]["value"] == 1
        assert ctx.backup["data"]["nested"]["inner"] == 2

    def test_realistic_error_recovery_pattern(self):
        """Test realistic error recovery pattern in node."""
        state = {
            "agent_results": {"existing": "data"},
            "metadata": {"attempt": 0},
        }
        fields = {"agent_results", "metadata"}

        result_to_return = None

        try:
            with StateMutationContext(state, "error_prone_node", fields_to_modify=fields) as ctx:
                ctx.update("metadata", {"attempt": 1})
                ctx.update("agent_results", {"partial": "data"})
                # Simulate error during processing
                raise ConnectionError("External API failed")
        except ConnectionError:
            # Use rollback state instead of partial result
            result_to_return = ctx.get_rollback_state()

        # Should get original state back
        assert result_to_return["agent_results"] == {"existing": "data"}
        assert result_to_return["metadata"] == {"attempt": 0}
