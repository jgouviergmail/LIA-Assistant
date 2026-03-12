"""
Unit tests for state tracking utilities.

Tests for centralized state tracking for LangGraph nodes,
including Prometheus metrics and structured logging.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.utils.state_tracking import track_state_updates

# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def mock_state() -> dict[str, Any]:
    """Create a mock MessagesState-like dict for testing."""
    return {
        "messages": [],
        "metadata": {"user_id": "user123", "session_id": "session456"},
        "routing_history": [],
        "agent_results": {},
        "current_turn_id": 1,
        "user_timezone": "Europe/Paris",
        "user_language": "fr",
    }


@pytest.fixture
def mock_metrics():
    """Patch all Prometheus metrics."""
    with (
        patch(
            "src.domains.agents.utils.state_tracking.langgraph_state_updates_total"
        ) as updates_total,
        patch("src.domains.agents.utils.state_tracking.langgraph_state_size_bytes") as size_bytes,
        patch("src.domains.agents.utils.state_tracking.calculate_state_size") as calc_size,
    ):
        calc_size.return_value = 1024  # Mock state size
        yield {
            "updates_total": updates_total,
            "size_bytes": size_bytes,
            "calc_size": calc_size,
        }


# ============================================================================
# Tests for basic track_state_updates functionality
# ============================================================================


class TestTrackStateUpdatesBasic:
    """Tests for basic state tracking functionality."""

    def test_tracks_single_key_update(self, mock_state, mock_metrics):
        """Test tracking a single key update."""
        updated_state = {"agent_results": {"1:contacts_agent": {"data": "test"}}}

        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="test_node",
        )

        # Should track one key update
        mock_metrics["updates_total"].labels.assert_called_once_with(
            node_name="test_node",
            key="agent_results",
        )
        mock_metrics["updates_total"].labels().inc.assert_called_once()

    def test_tracks_multiple_key_updates(self, mock_state, mock_metrics):
        """Test tracking multiple key updates."""
        updated_state = {
            "agent_results": {"1:contacts_agent": {"data": "test"}},
            "routing_history": [{"decision": "planner"}],
            "current_turn_id": 2,
        }

        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="orchestrator",
        )

        # Should track three key updates
        assert mock_metrics["updates_total"].labels.call_count == 3

    def test_calculates_merged_state_size(self, mock_state, mock_metrics):
        """Test that merged state size is calculated."""
        updated_state = {"new_key": "new_value"}

        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="test_node",
        )

        # Should calculate size of merged state
        mock_metrics["calc_size"].assert_called_once()
        call_args = mock_metrics["calc_size"].call_args[0][0]
        # Merged state should have both old and new keys
        assert "new_key" in call_args
        assert "messages" in call_args

    def test_observes_state_size_metric(self, mock_state, mock_metrics):
        """Test that state size is observed in histogram."""
        updated_state = {"key": "value"}

        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="approval_gate",
        )

        mock_metrics["size_bytes"].labels.assert_called_once_with(node_name="approval_gate")
        mock_metrics["size_bytes"].labels().observe.assert_called_once_with(1024)


class TestTrackStateUpdatesWithContext:
    """Tests for state tracking with context parameters."""

    def test_with_context_id(self, mock_state, mock_metrics):
        """Test tracking with context_id parameter."""
        updated_state = {"key": "value"}

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state=updated_state,
                node_name="test_node",
                context_id="run_123",
            )

            # Check logger was called with context_id
            mock_logger.debug.assert_called_once()
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["context_id"] == "run_123"

    def test_with_plan_id(self, mock_state, mock_metrics):
        """Test tracking with plan_id parameter."""
        updated_state = {"execution_plan": {"steps": []}}

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state=updated_state,
                node_name="approval_gate",
                plan_id="plan_456",
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["plan_id"] == "plan_456"

    def test_with_additional_context(self, mock_state, mock_metrics):
        """Test tracking with additional_context parameter."""
        updated_state = {"key": "value"}
        additional = {"step_count": 5, "execution_mode": "parallel"}

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state=updated_state,
                node_name="orchestrator",
                additional_context=additional,
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["step_count"] == 5
            assert call_kwargs["execution_mode"] == "parallel"

    def test_with_all_context_parameters(self, mock_state, mock_metrics):
        """Test tracking with all context parameters."""
        updated_state = {"result": "success"}

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state=updated_state,
                node_name="complete_node",
                context_id="ctx_789",
                plan_id="plan_abc",
                additional_context={"extra": "info"},
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["context_id"] == "ctx_789"
            assert call_kwargs["plan_id"] == "plan_abc"
            assert call_kwargs["extra"] == "info"


class TestTrackStateUpdatesLogging:
    """Tests for structured logging in state tracking."""

    def test_logs_node_name_in_event(self, mock_state, mock_metrics):
        """Test that node name appears in log event name."""
        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state={"key": "value"},
                node_name="my_custom_node",
            )

            # Event name should be "{node_name}_state_updated"
            call_args = mock_logger.debug.call_args[0]
            assert call_args[0] == "my_custom_node_state_updated"

    def test_logs_state_size_bytes(self, mock_state, mock_metrics):
        """Test that state size is logged."""
        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state={"key": "value"},
                node_name="test",
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert "state_size_bytes" in call_kwargs
            assert call_kwargs["state_size_bytes"] == 1024

    def test_logs_updated_keys(self, mock_state, mock_metrics):
        """Test that updated keys are logged."""
        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state={"key1": "v1", "key2": "v2"},
                node_name="test",
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert "updated_keys" in call_kwargs
            assert set(call_kwargs["updated_keys"]) == {"key1", "key2"}

    def test_no_context_id_when_none(self, mock_state, mock_metrics):
        """Test that context_id is not logged when None."""
        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state={"key": "value"},
                node_name="test",
                context_id=None,
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert "context_id" not in call_kwargs

    def test_no_plan_id_when_none(self, mock_state, mock_metrics):
        """Test that plan_id is not logged when None."""
        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state={"key": "value"},
                node_name="test",
                plan_id=None,
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert "plan_id" not in call_kwargs


class TestTrackStateUpdatesEdgeCases:
    """Tests for edge cases in state tracking."""

    def test_empty_updated_state(self, mock_state, mock_metrics):
        """Test tracking with empty updated state."""
        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state={},
                node_name="empty_node",
            )

            # No key updates should be tracked
            mock_metrics["updates_total"].labels.assert_not_called()

            # But logging should still occur
            mock_logger.debug.assert_called_once()
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["updated_keys"] == []

    def test_empty_state(self, mock_metrics):
        """Test tracking with empty initial state."""
        empty_state: dict[str, Any] = {}
        updated_state = {"new_key": "new_value"}

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=empty_state,
                updated_state=updated_state,
                node_name="init_node",
            )

            # Should work and track the new key
            mock_metrics["updates_total"].labels.assert_called_once()
            mock_logger.debug.assert_called_once()

    def test_large_updated_state(self, mock_state, mock_metrics):
        """Test tracking with many keys in updated state."""
        # Create 100 key updates
        updated_state = {f"key_{i}": f"value_{i}" for i in range(100)}

        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="bulk_node",
        )

        # Should track all 100 key updates
        assert mock_metrics["updates_total"].labels.call_count == 100

    def test_overwriting_existing_keys(self, mock_state, mock_metrics):
        """Test tracking when overwriting existing state keys."""
        # Update existing keys
        updated_state = {
            "messages": ["new", "messages"],
            "current_turn_id": 10,
        }

        with patch("src.domains.agents.utils.state_tracking.logger"):
            track_state_updates(
                state=mock_state,
                updated_state=updated_state,
                node_name="update_node",
            )

            # Should track both key updates
            assert mock_metrics["updates_total"].labels.call_count == 2

            # Merged state should have new values
            call_args = mock_metrics["calc_size"].call_args[0][0]
            assert call_args["messages"] == ["new", "messages"]
            assert call_args["current_turn_id"] == 10


class TestTrackStateUpdatesNodeNames:
    """Tests for different node names used in tracking."""

    @pytest.mark.parametrize(
        "node_name",
        [
            "router_node_v3",
            "planner_node_v3",
            "approval_gate_node",
            "task_orchestrator_node",
            "response_node",
            "semantic_validator_node",
            "hitl_dispatch_node",
        ],
    )
    def test_various_node_names(self, node_name, mock_state, mock_metrics):
        """Test tracking with various real node names."""
        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state={"key": "value"},
                node_name=node_name,
            )

            # Check metrics use correct node name
            mock_metrics["updates_total"].labels.assert_called_with(
                node_name=node_name,
                key="key",
            )
            mock_metrics["size_bytes"].labels.assert_called_with(node_name=node_name)

            # Check log event uses correct node name
            call_args = mock_logger.debug.call_args[0]
            assert call_args[0] == f"{node_name}_state_updated"


class TestTrackStateUpdatesMetricInteraction:
    """Tests for proper interaction with Prometheus metrics."""

    def test_metrics_called_in_correct_order(self, mock_state, mock_metrics):
        """Test that metrics are updated before logging."""
        call_order = []

        def track_updates_call(*args, **kwargs):
            call_order.append("updates")
            return MagicMock()

        def track_size_call(*args, **kwargs):
            call_order.append("size")
            return MagicMock()

        mock_metrics["updates_total"].labels.side_effect = track_updates_call
        mock_metrics["size_bytes"].labels.side_effect = track_size_call

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:

            def track_log(*args, **kwargs):
                call_order.append("log")

            mock_logger.debug.side_effect = track_log

            track_state_updates(
                state=mock_state,
                updated_state={"key": "value"},
                node_name="test",
            )

        # Updates should come first, then size, then log
        assert call_order[0] == "updates"
        assert "size" in call_order
        assert call_order[-1] == "log"

    def test_each_key_gets_separate_metric(self, mock_state, mock_metrics):
        """Test that each key update gets its own metric call."""
        updated_state = {"a": 1, "b": 2, "c": 3}

        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="multi_key",
        )

        # Verify each key was tracked
        calls = mock_metrics["updates_total"].labels.call_args_list
        keys_tracked = {call.kwargs["key"] for call in calls}
        assert keys_tracked == {"a", "b", "c"}


class TestTrackStateUpdatesComplexTypes:
    """Tests for tracking with complex value types."""

    def test_with_nested_dict_values(self, mock_state, mock_metrics):
        """Test tracking with deeply nested dictionary values."""
        updated_state = {
            "agent_results": {
                "1:contacts_agent": {
                    "data": {
                        "contacts": [
                            {"name": "John", "email": "john@example.com"},
                            {"name": "Jane", "email": "jane@example.com"},
                        ]
                    }
                }
            }
        }

        # Should not raise any errors
        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="nested",
        )

        mock_metrics["updates_total"].labels.assert_called()

    def test_with_list_values(self, mock_state, mock_metrics):
        """Test tracking with list values."""
        updated_state = {
            "routing_history": [
                {"decision": "chat", "turn": 1},
                {"decision": "planner", "turn": 2},
            ]
        }

        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="list_test",
        )

        mock_metrics["updates_total"].labels.assert_called()

    def test_with_none_value(self, mock_state, mock_metrics):
        """Test tracking with None as a value."""
        updated_state = {"execution_plan": None}

        track_state_updates(
            state=mock_state,
            updated_state=updated_state,
            node_name="none_test",
        )

        mock_metrics["updates_total"].labels.assert_called_with(
            node_name="none_test",
            key="execution_plan",
        )


class TestTrackStateUpdatesRealUsageScenarios:
    """Tests simulating real usage scenarios from nodes."""

    def test_router_node_scenario(self, mock_state, mock_metrics):
        """Test tracking as used by router_node_v3."""
        updated_state = {
            "routing_history": [{"decision": "planner", "confidence": 0.95}],
        }

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state=updated_state,
                node_name="router_node_v3",
                context_id="run_abc123",
            )

            mock_logger.debug.assert_called_once()
            assert "run_abc123" in str(mock_logger.debug.call_args)

    def test_task_orchestrator_scenario(self, mock_state, mock_metrics):
        """Test tracking as used by task_orchestrator_node."""
        updated_state = {
            "agent_results": {
                "2:contacts_agent": {"contacts": []},
                "2:emails_agent": {"emails": []},
            },
            "current_turn_id": 2,
        }

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state=updated_state,
                node_name="task_orchestrator",
                context_id="orchestration_xyz",
                additional_context={"steps_executed": 2},
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["steps_executed"] == 2

    def test_approval_gate_scenario(self, mock_state, mock_metrics):
        """Test tracking as used by approval_gate_node."""
        updated_state = {
            "execution_plan": {
                "plan_id": "plan_999",
                "steps": [{"tool": "send_email", "params": {}}],
            }
        }

        with patch("src.domains.agents.utils.state_tracking.logger") as mock_logger:
            track_state_updates(
                state=mock_state,
                updated_state=updated_state,
                node_name="approval_gate",
                plan_id="plan_999",
            )

            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["plan_id"] == "plan_999"
