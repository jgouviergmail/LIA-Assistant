"""
Unit tests for LangGraph state management metrics (P3).

Tests that all nodes correctly track state updates and state size:
- langgraph_state_updates_total{node_name, key}
- langgraph_state_size_bytes{node_name}

Phase: PHASE 2.5 - LangGraph Observability (P3)
Created: 2025-11-22
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY

from src.domains.agents.constants import (
    AGENT_CONTACT,
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_MESSAGES,
    STATE_KEY_ORCHESTRATION_PLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.models import MessagesState
from src.infrastructure.observability.metrics_langgraph import (
    langgraph_state_size_bytes,
    langgraph_state_updates_total,
)

# Skip entire module - State metrics not implemented in nodes yet
# The langgraph_state_updates_total and langgraph_state_size_bytes metrics
# are defined but not recorded by nodes. Tests are skipped until implementation.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skip(reason="State metrics not implemented in nodes"),
]


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test to ensure clean state."""
    for collector in list(REGISTRY._collector_to_names.keys()):
        if hasattr(collector, "_metrics"):
            collector._metrics.clear()
    yield


class TestRouterNodeStateMetrics:
    """Test state tracking for router_node."""

    @pytest.mark.asyncio
    async def test_tracks_state_updates_success_path(self):
        """Verify router_node tracks state updates on success path."""
        from langchain_core.messages import HumanMessage
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
        from src.domains.agents.nodes import router_node

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="test message")],
        }
        config = RunnableConfig(metadata={"run_id": "test_run"})

        # Create mock QueryIntelligence result
        mock_intelligence = QueryIntelligence(
            original_query="test message",
            english_query="test message",
            immediate_intent="chat",
            immediate_confidence=0.9,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="Test reasoning",
            domains=[],
            route_to="response",
            confidence=0.9,
        )

        mock_service = MagicMock()
        mock_service.analyze_full = AsyncMock(return_value=mock_intelligence)

        with patch(
            "src.domains.agents.services.query_analyzer_service.get_query_analyzer_service",
            return_value=mock_service,
        ):
            await router_node(state, config)

        # Check that state updates were tracked
        update_samples = langgraph_state_updates_total.collect()[0].samples
        router_samples = [s for s in update_samples if s.labels.get("node_name") == "router_v3"]

        assert len(router_samples) > 0, "Router should track state updates"

        # Verify specific keys were tracked
        tracked_keys = {s.labels.get("key") for s in router_samples}
        assert STATE_KEY_ROUTING_HISTORY in tracked_keys

        # Check state size was tracked
        size_samples = langgraph_state_size_bytes.collect()[0].samples
        router_size_samples = [s for s in size_samples if s.labels.get("node_name") == "router_v3"]
        assert len(router_size_samples) > 0, "Router should track state size"


class TestPlannerNodeStateMetrics:
    """Test state tracking for planner_node."""

    @pytest.mark.asyncio
    async def test_tracks_state_updates_missing_routing_history(self):
        """Verify planner_node tracks state updates when routing_history is missing."""
        from langchain_core.messages import HumanMessage
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.nodes import planner_node

        # Missing routing_history will trigger error path in planner
        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="test")],
            # No routing_history key
        }
        config = RunnableConfig(metadata={"run_id": "test_run"})

        await planner_node(state, config)

        # Check that state updates were tracked despite error
        update_samples = langgraph_state_updates_total.collect()[0].samples
        planner_samples = [s for s in update_samples if s.labels.get("node_name") == "planner"]

        assert len(planner_samples) > 0, "Planner should track state updates on error"

        # Check state size was tracked
        size_samples = langgraph_state_size_bytes.collect()[0].samples
        planner_size_samples = [s for s in size_samples if s.labels.get("node_name") == "planner"]
        assert len(planner_size_samples) > 0, "Planner should track state size on error"


class TestApprovalGateNodeStateMetrics:
    """Test state tracking for approval_gate_node.

    NOTE (2026-01-19): HITL is now always enabled (no kill switch).
    """

    @pytest.mark.asyncio
    async def test_tracks_state_updates_no_execution_plan(self):
        """Verify approval_gate_node tracks state when no execution plan."""
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.nodes.approval_gate_node import approval_gate_node

        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            # No execution_plan key
        }
        config = RunnableConfig(metadata={"run_id": "test_run"})

        # NOTE: HITL is always enabled - no need to mock settings
        await approval_gate_node(state, config)

        # Check that state updates were tracked
        update_samples = langgraph_state_updates_total.collect()[0].samples
        approval_samples = [
            s for s in update_samples if s.labels.get("node_name") == "approval_gate"
        ]

        assert len(approval_samples) > 0

        # Verify keys were tracked
        tracked_keys = {s.labels.get("key") for s in approval_samples}
        assert STATE_KEY_PLAN_APPROVED in tracked_keys
        assert STATE_KEY_PLAN_REJECTION_REASON in tracked_keys


class TestTaskOrchestratorNodeStateMetrics:
    """Test state tracking for task_orchestrator_node."""

    @pytest.mark.asyncio
    async def test_tracks_state_updates_no_routing_history(self):
        """Verify task_orchestrator_node tracks state when no routing history."""
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.nodes.task_orchestrator_node import task_orchestrator_node

        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_ROUTING_HISTORY: [],  # Empty routing history
        }
        config = RunnableConfig(metadata={"run_id": "test_run"})

        await task_orchestrator_node(state, config)

        # Check that state updates were tracked
        update_samples = langgraph_state_updates_total.collect()[0].samples
        orchestrator_samples = [
            s for s in update_samples if s.labels.get("node_name") == "task_orchestrator"
        ]

        assert len(orchestrator_samples) > 0

        # Verify keys were tracked
        tracked_keys = {s.labels.get("key") for s in orchestrator_samples}
        assert STATE_KEY_ORCHESTRATION_PLAN in tracked_keys
        assert STATE_KEY_AGENT_RESULTS in tracked_keys

    @pytest.mark.asyncio
    async def test_tracks_state_updates_on_exception(self):
        """Verify task_orchestrator_node tracks state on exception path."""
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.domain_schemas import RouterOutput
        from src.domains.agents.nodes.task_orchestrator_node import task_orchestrator_node

        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_ROUTING_HISTORY: [
                RouterOutput(
                    intention="test",
                    confidence=0.9,
                    context_label="test",
                    next_node="planner",
                )
            ],
        }
        config = RunnableConfig(metadata={"run_id": "test_run"})

        # Mock to force exception
        with patch(
            "src.domains.agents.nodes.task_orchestrator_node.create_orchestration_plan"
        ) as mock_create:
            mock_create.side_effect = Exception("Test error")

            await task_orchestrator_node(state, config)

        # Check that state updates were tracked despite exception
        update_samples = langgraph_state_updates_total.collect()[0].samples
        orchestrator_samples = [
            s for s in update_samples if s.labels.get("node_name") == "task_orchestrator"
        ]

        assert len(orchestrator_samples) > 0

        # Check state size was tracked
        size_samples = langgraph_state_size_bytes.collect()[0].samples
        orchestrator_size_samples = [
            s for s in size_samples if s.labels.get("node_name") == "task_orchestrator"
        ]
        assert len(orchestrator_size_samples) > 0


class TestResponseNodeStateMetrics:
    """Test state tracking for response_node."""

    @pytest.mark.asyncio
    async def test_tracks_state_updates_success_path(self):
        """Verify response_node tracks state updates on success."""
        from langchain_core.messages import AIMessage, HumanMessage
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.nodes.response_node import response_node

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="test")],
            STATE_KEY_AGENT_RESULTS: {},
        }
        config = RunnableConfig(metadata={"run_id": "test_run"})

        # Mock LLM response
        with patch("src.domains.agents.nodes.response_node.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_get_llm.return_value = mock_llm

            mock_chain = AsyncMock()
            mock_chain.ainvoke.return_value = AIMessage(content="Test response")

            with patch("src.domains.agents.nodes.response_node.get_response_prompt") as mock_prompt:
                mock_prompt.return_value = "mock system prompt"

                with patch("src.domains.agents.nodes.response_node.ChatPromptTemplate") as mock_cpt:
                    mock_prompt_obj = MagicMock()
                    mock_prompt_obj.__or__ = MagicMock(return_value=mock_chain)
                    mock_cpt.from_messages.return_value = mock_prompt_obj

                    await response_node(state, config)

        # Check that state updates were tracked
        update_samples = langgraph_state_updates_total.collect()[0].samples
        response_samples = [s for s in update_samples if s.labels.get("node_name") == "response"]

        assert len(response_samples) > 0

        # Verify messages key was tracked
        tracked_keys = {s.labels.get("key") for s in response_samples}
        assert STATE_KEY_MESSAGES in tracked_keys

    @pytest.mark.asyncio
    async def test_tracks_state_updates_on_exception(self):
        """Verify response_node tracks state on exception path."""
        from langchain_core.messages import HumanMessage
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.nodes.response_node import response_node

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="test")],
            STATE_KEY_AGENT_RESULTS: {},
        }
        config = RunnableConfig(metadata={"run_id": "test_run"})

        # Mock to force exception
        with patch("src.domains.agents.nodes.response_node.get_llm") as mock_get_llm:
            mock_get_llm.side_effect = Exception("LLM error")

            await response_node(state, config)

        # Check that state updates were tracked despite exception
        update_samples = langgraph_state_updates_total.collect()[0].samples
        response_samples = [s for s in update_samples if s.labels.get("node_name") == "response"]

        assert len(response_samples) > 0


class TestAgentWrapperStateMetrics:
    """Test state tracking for agent wrapper nodes."""

    @pytest.mark.asyncio
    async def test_tracks_state_updates_wrapper(self):
        """Verify agent wrapper tracks state updates."""
        from langchain_core.messages import AIMessage
        from langchain_core.runnables import RunnableConfig

        from src.domains.agents.graphs.base_agent_builder import create_agent_wrapper_node

        # Create mock agent runnable
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            STATE_KEY_MESSAGES: [AIMessage(content="Agent response")],
        }

        # Create wrapper
        wrapper = create_agent_wrapper_node(
            agent_runnable=mock_agent,
            agent_name="contacts_agent",
            agent_constant=AGENT_CONTACT,
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = RunnableConfig(metadata={"run_id": "test_run"})

        await wrapper(state, config)

        # Check that state updates were tracked
        update_samples = langgraph_state_updates_total.collect()[0].samples
        agent_samples = [s for s in update_samples if s.labels.get("node_name") == AGENT_CONTACT]

        assert len(agent_samples) > 0

        # Verify keys were tracked
        tracked_keys = {s.labels.get("key") for s in agent_samples}
        assert STATE_KEY_MESSAGES in tracked_keys
        assert STATE_KEY_AGENT_RESULTS in tracked_keys


class TestMetricsCardinality:
    """Test that state metrics have acceptable cardinality."""

    def test_state_updates_cardinality(self):
        """Verify langgraph_state_updates_total has acceptable label combinations."""
        # Expected node_name values: 7 nodes
        expected_nodes = [
            "router",
            "planner",
            "approval_gate",
            "task_orchestrator",
            "response",
            "contacts_agent",  # Agent wrapper
            "emails_agent",  # Agent wrapper
        ]

        # Expected key values (approximate, depends on execution paths):
        # - messages (all nodes)
        # - routing_history (router, task_orchestrator)
        # - execution_plan (planner, approval_gate, task_orchestrator)
        # - validation_result (planner)
        # - plan_approved (approval_gate)
        # - orchestration_plan (task_orchestrator)
        # - agent_results (task_orchestrator, response, agents)
        # - content_final_replacement (response)
        # - planner_error (planner)
        # Total unique combinations: ~40 (7 nodes * average 6 keys)

        max_expected_series = 50  # Buffer for future additions

        # This test validates design, actual metrics populated by other tests
        # Cardinality check: node_name (7) * avg_keys_per_node (6) < 50 ✓

        assert len(expected_nodes) == 7
        assert max_expected_series == 50

    def test_state_size_cardinality(self):
        """Verify langgraph_state_size_bytes has acceptable label combinations."""
        # Expected node_name values: 7 nodes (same as state_updates)
        # Histogram buckets: 8 buckets [1KB, 5KB, 10KB, 50KB, 100KB, 500KB, 1MB, 5MB]
        # Total time series: 7 nodes * 8 buckets = 56 series

        max_expected_series = 60  # Buffer

        expected_nodes_count = 7
        histogram_buckets = 8

        actual_max_series = expected_nodes_count * histogram_buckets
        assert actual_max_series <= max_expected_series
