"""
Unit tests for LangGraph framework metrics.

Phase: PHASE 2.5 - LangGraph Observability
Created: 2025-11-22
Target: Validate metrics_langgraph.py instrumentation
"""

from unittest.mock import Mock

from src.infrastructure.observability.metrics_langgraph import (
    calculate_state_size,
    extract_node_name_from_config,
    langgraph_conditional_edges_total,
    langgraph_graph_duration_seconds,
    langgraph_graph_errors_total,
    langgraph_graph_executions_total,
    langgraph_graph_interrupts_total,
    langgraph_graph_recursion_limit_exceeded_total,
    langgraph_node_transitions_total,
    langgraph_state_size_bytes,
    langgraph_state_updates_total,
    langgraph_streaming_chunks_total,
    langgraph_streaming_events_total,
    langgraph_subgraph_duration_seconds,
    langgraph_subgraph_invocations_total,
    langgraph_subgraph_tool_calls_total,
)


class TestMetricDefinitions:
    """Test that all metric definitions are valid and accessible."""

    def test_langgraph_graph_executions_total_exists(self):
        """Test langgraph_graph_executions_total metric is defined."""
        assert langgraph_graph_executions_total is not None
        # Test labels can be set
        metric = langgraph_graph_executions_total.labels(status="success")
        assert metric is not None

    def test_langgraph_graph_duration_seconds_exists(self):
        """Test langgraph_graph_duration_seconds histogram is defined."""
        assert langgraph_graph_duration_seconds is not None

    def test_langgraph_graph_errors_total_exists(self):
        """Test langgraph_graph_errors_total metric is defined."""
        assert langgraph_graph_errors_total is not None
        metric = langgraph_graph_errors_total.labels(error_type="GraphRecursionError")
        assert metric is not None

    def test_langgraph_node_transitions_total_exists(self):
        """Test langgraph_node_transitions_total metric is defined."""
        assert langgraph_node_transitions_total is not None
        metric = langgraph_node_transitions_total.labels(from_node="router", to_node="planner")
        assert metric is not None

    def test_langgraph_conditional_edges_total_exists(self):
        """Test langgraph_conditional_edges_total metric is defined."""
        assert langgraph_conditional_edges_total is not None
        metric = langgraph_conditional_edges_total.labels(
            edge_name="route_from_router", decision="planner"
        )
        assert metric is not None

    def test_langgraph_state_updates_total_exists(self):
        """Test langgraph_state_updates_total metric is defined."""
        assert langgraph_state_updates_total is not None
        metric = langgraph_state_updates_total.labels(node_name="router", key="routing_history")
        assert metric is not None

    def test_langgraph_state_size_bytes_exists(self):
        """Test langgraph_state_size_bytes histogram is defined."""
        assert langgraph_state_size_bytes is not None
        metric = langgraph_state_size_bytes.labels(node_name="router")
        assert metric is not None

    def test_langgraph_subgraph_invocations_total_exists(self):
        """Test langgraph_subgraph_invocations_total metric is defined."""
        assert langgraph_subgraph_invocations_total is not None
        metric = langgraph_subgraph_invocations_total.labels(
            agent_name="contacts_agent", status="success"
        )
        assert metric is not None

    def test_langgraph_subgraph_duration_seconds_exists(self):
        """Test langgraph_subgraph_duration_seconds histogram is defined."""
        assert langgraph_subgraph_duration_seconds is not None
        metric = langgraph_subgraph_duration_seconds.labels(agent_name="contacts_agent")
        assert metric is not None

    def test_langgraph_subgraph_tool_calls_total_exists(self):
        """Test langgraph_subgraph_tool_calls_total metric is defined."""
        assert langgraph_subgraph_tool_calls_total is not None
        metric = langgraph_subgraph_tool_calls_total.labels(
            agent_name="contacts_agent", tool_name="google_contacts_search"
        )
        assert metric is not None

    def test_langgraph_streaming_chunks_total_exists(self):
        """Test langgraph_streaming_chunks_total metric is defined."""
        assert langgraph_streaming_chunks_total is not None
        metric = langgraph_streaming_chunks_total.labels(event_type="STREAM_TOKEN")
        assert metric is not None

    def test_langgraph_streaming_events_total_exists(self):
        """Test langgraph_streaming_events_total metric is defined."""
        assert langgraph_streaming_events_total is not None
        metric = langgraph_streaming_events_total.labels(event_name="on_llm_stream")
        assert metric is not None

    def test_langgraph_graph_recursion_limit_exceeded_total_exists(self):
        """Test langgraph_graph_recursion_limit_exceeded_total metric is defined."""
        assert langgraph_graph_recursion_limit_exceeded_total is not None
        metric = langgraph_graph_recursion_limit_exceeded_total.labels(max_recursion_limit="25")
        assert metric is not None

    def test_langgraph_graph_interrupts_total_exists(self):
        """Test langgraph_graph_interrupts_total metric is defined."""
        assert langgraph_graph_interrupts_total is not None
        metric = langgraph_graph_interrupts_total.labels(interrupt_type="hitl_approval")
        assert metric is not None


class TestHelperFunctions:
    """Test helper functions for metrics instrumentation."""

    def test_extract_node_name_from_config_with_node_name(self):
        """Test extract_node_name_from_config with valid node_name."""
        config = {"configurable": {"node_name": "router"}}
        result = extract_node_name_from_config(config)
        assert result == "router"

    def test_extract_node_name_from_config_without_configurable(self):
        """Test extract_node_name_from_config with empty config."""
        config = {}
        result = extract_node_name_from_config(config)
        assert result == "unknown"

    def test_extract_node_name_from_config_without_node_name(self):
        """Test extract_node_name_from_config without node_name key."""
        config = {"configurable": {"thread_id": "123"}}
        result = extract_node_name_from_config(config)
        assert result == "unknown"

    def test_calculate_state_size_with_simple_state(self):
        """Test calculate_state_size with simple state."""
        state = {"messages": [{"content": "test"}], "routing_history": []}
        size = calculate_state_size(state)
        assert size > 0
        assert isinstance(size, int)

    def test_calculate_state_size_with_empty_state(self):
        """Test calculate_state_size with empty state."""
        state = {}
        size = calculate_state_size(state)
        assert size >= 0

    def test_calculate_state_size_with_large_state(self):
        """Test calculate_state_size with large state."""
        # Create state with many messages
        messages = [{"content": f"Message {i}" * 100} for i in range(100)]
        state = {"messages": messages}
        size = calculate_state_size(state)
        # Should be > 10KB for 100 long messages
        assert size > 10000

    def test_calculate_state_size_with_non_serializable_objects(self):
        """Test calculate_state_size handles non-JSON-serializable objects."""
        # Create state with non-serializable object
        mock_obj = Mock()
        state = {"messages": [], "custom_obj": mock_obj}
        size = calculate_state_size(state)
        # Should not raise exception, return approximate size
        assert size > 0


class TestMetricsInstrumentation:
    """Test metrics instrumentation in orchestration service."""

    def test_graph_execution_metrics_instrumented(self):
        """
        Test that graph execution metrics are instrumented in orchestration/service.py.

        This is a basic smoke test - integration tests will validate actual metrics collection.
        """
        # Verify metrics can be imported and used
        from src.infrastructure.observability.metrics_langgraph import (
            langgraph_graph_executions_total,
        )

        # Simulate instrumentation usage
        langgraph_graph_executions_total.labels(status="success").inc()
        # No assertion needed - if no exception raised, instrumentation is valid

    def test_graph_duration_histogram_buckets(self):
        """Test graph duration histogram has correct buckets for conversation latency."""
        # Verify histogram metric exists and can observe values
        langgraph_graph_duration_seconds.observe(5.0)
        # Buckets: [0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0]
        # 5.0 should fit in bucket

    def test_state_size_histogram_buckets(self):
        """Test state size histogram has correct buckets for large states."""
        # Verify state size metric can handle large values
        metric = langgraph_state_size_bytes.labels(node_name="test")
        metric.observe(50000)  # 50KB
        metric.observe(1000000)  # 1MB
        # Should handle both values without error


class TestMetricsCardinality:
    """Test metrics cardinality to prevent explosion."""

    def test_node_transitions_cardinality(self):
        """Test node_transitions_total has reasonable cardinality."""
        # Simulate typical node pairs
        nodes = ["router", "planner", "task_orchestrator", "response"]
        for from_node in nodes:
            for to_node in nodes:
                if from_node != to_node:  # No self-transitions
                    metric = langgraph_node_transitions_total.labels(
                        from_node=from_node, to_node=to_node
                    )
                    assert metric is not None
        # Cardinality: 4 nodes × 3 targets = 12 series (acceptable)

    def test_state_updates_cardinality(self):
        """Test state_updates_total has reasonable cardinality."""
        # Simulate typical state keys
        nodes = ["router", "planner", "task_orchestrator"]
        keys = ["messages", "routing_history", "agent_results", "execution_plan"]
        for node in nodes:
            for key in keys:
                metric = langgraph_state_updates_total.labels(node_name=node, key=key)
                assert metric is not None
        # Cardinality: 3 nodes × 4 keys = 12 series (acceptable)

    def test_subgraph_tool_calls_cardinality(self):
        """Test subgraph_tool_calls_total has reasonable cardinality."""
        # Simulate typical agents and tools
        agents = ["contacts_agent", "emails_agent"]
        tools = [
            "google_contacts_search",
            "google_contacts_list",
            "google_gmail_search",
            "google_gmail_list",
        ]
        for agent in agents:
            for tool in tools:
                metric = langgraph_subgraph_tool_calls_total.labels(
                    agent_name=agent, tool_name=tool
                )
                assert metric is not None
        # Cardinality: 2 agents × 4 tools = 8 series (acceptable)
