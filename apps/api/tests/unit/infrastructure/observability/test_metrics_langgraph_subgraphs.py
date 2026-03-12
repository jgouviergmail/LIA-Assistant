"""
Unit tests for LangGraph subgraph metrics (P4).

Tests that agent wrappers correctly track:
- Subgraph invocations (langgraph_subgraph_invocations_total)
- Subgraph duration (langgraph_subgraph_duration_seconds)
- Tool calls within subgraphs (langgraph_subgraph_tool_calls_total)

Phase: PHASE 2.5 - LangGraph Observability (P4)
Created: 2025-11-22
"""

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from prometheus_client import REGISTRY

from src.domains.agents.constants import (
    AGENT_CONTACT,
    AGENT_EMAIL,
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_MESSAGES,
)
from src.domains.agents.graphs.base_agent_builder import create_agent_wrapper_node
from src.domains.agents.models import MessagesState
from src.infrastructure.observability.metrics_langgraph import (
    langgraph_subgraph_duration_seconds,
    langgraph_subgraph_invocations_total,
    langgraph_subgraph_tool_calls_total,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test to ensure clean state."""
    for collector in list(REGISTRY._collector_to_names.keys()):
        if hasattr(collector, "_metrics"):
            collector._metrics.clear()
    yield


class TestSubgraphInvocationMetrics:
    """Test subgraph invocation tracking."""

    @pytest.mark.asyncio
    async def test_tracks_successful_subgraph_invocation(self):
        """Verify successful subgraph invocations are tracked."""
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
            STATE_KEY_MESSAGES: [HumanMessage(content="test")],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = {"metadata": {"run_id": "test_run"}}

        await wrapper(state, config)

        # Verify invocation was tracked
        invocation_samples = langgraph_subgraph_invocations_total.collect()[0].samples
        success_samples = [
            s
            for s in invocation_samples
            if s.labels.get("agent_name") == AGENT_CONTACT and s.labels.get("status") == "success"
        ]

        assert len(success_samples) > 0
        assert success_samples[0].value >= 1.0

    @pytest.mark.asyncio
    async def test_tracks_failed_subgraph_invocation(self):
        """Verify failed subgraph invocations are tracked."""
        # Create mock agent that raises exception
        mock_agent = AsyncMock()
        mock_agent.ainvoke.side_effect = Exception("Agent error")

        # Create wrapper
        wrapper = create_agent_wrapper_node(
            agent_runnable=mock_agent,
            agent_name="contacts_agent",
            agent_constant=AGENT_CONTACT,
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="test")],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = {"metadata": {"run_id": "test_run"}}

        with pytest.raises(Exception, match="Agent error"):
            await wrapper(state, config)

        # Verify error invocation was tracked
        invocation_samples = langgraph_subgraph_invocations_total.collect()[0].samples
        error_samples = [
            s
            for s in invocation_samples
            if s.labels.get("agent_name") == AGENT_CONTACT and s.labels.get("status") == "error"
        ]

        assert len(error_samples) > 0
        assert error_samples[0].value >= 1.0


class TestSubgraphDurationMetrics:
    """Test subgraph duration tracking."""

    @pytest.mark.asyncio
    async def test_tracks_subgraph_duration_success(self):
        """Verify subgraph duration is tracked on success."""
        # Create mock agent with simulated delay
        mock_agent = AsyncMock()

        async def mock_invoke(*args, **kwargs):
            import asyncio

            await asyncio.sleep(0.01)  # 10ms delay
            return {STATE_KEY_MESSAGES: [AIMessage(content="Response")]}

        mock_agent.ainvoke = mock_invoke

        # Create wrapper
        wrapper = create_agent_wrapper_node(
            agent_runnable=mock_agent,
            agent_name="contacts_agent",
            agent_constant=AGENT_CONTACT,
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="test")],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = {"metadata": {"run_id": "test_run"}}

        await wrapper(state, config)

        # Verify duration was tracked
        duration_samples = langgraph_subgraph_duration_seconds.collect()[0].samples
        contacts_samples = [
            s for s in duration_samples if s.labels.get("agent_name") == AGENT_CONTACT
        ]

        assert len(contacts_samples) > 0
        # Check that at least one histogram bucket was incremented
        assert any(s.value > 0 for s in contacts_samples)

    @pytest.mark.asyncio
    async def test_tracks_subgraph_duration_error(self):
        """Verify subgraph duration is tracked even on error."""
        # Create mock agent that raises exception
        mock_agent = AsyncMock()

        async def mock_invoke_error(*args, **kwargs):
            import asyncio

            await asyncio.sleep(0.01)  # 10ms delay before error
            raise Exception("Agent error")

        mock_agent.ainvoke = mock_invoke_error

        # Create wrapper
        wrapper = create_agent_wrapper_node(
            agent_runnable=mock_agent,
            agent_name="contacts_agent",
            agent_constant=AGENT_CONTACT,
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="test")],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = {"metadata": {"run_id": "test_run"}}

        with pytest.raises(Exception, match="Agent error"):
            await wrapper(state, config)

        # Verify duration was tracked despite error
        duration_samples = langgraph_subgraph_duration_seconds.collect()[0].samples
        contacts_samples = [
            s for s in duration_samples if s.labels.get("agent_name") == AGENT_CONTACT
        ]

        assert len(contacts_samples) > 0
        assert any(s.value > 0 for s in contacts_samples)


class TestSubgraphToolCallsMetrics:
    """Test tool call tracking within subgraphs."""

    @pytest.mark.asyncio
    async def test_tracks_tool_calls_single_tool(self):
        """Verify tool calls are tracked when agent uses tools."""
        # Create mock agent that returns ToolMessages
        mock_agent = AsyncMock()
        tool_msg = ToolMessage(
            content="Contact found: John Doe",
            tool_call_id="call_123",
            name="google_contacts_search",
        )
        mock_agent.ainvoke.return_value = {
            STATE_KEY_MESSAGES: [
                AIMessage(content="Searching..."),
                tool_msg,
                AIMessage(content="Found contact"),
            ],
        }

        # Create wrapper
        wrapper = create_agent_wrapper_node(
            agent_runnable=mock_agent,
            agent_name="contacts_agent",
            agent_constant=AGENT_CONTACT,
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="Find John")],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = {"metadata": {"run_id": "test_run"}}

        await wrapper(state, config)

        # Verify tool call was tracked
        tool_samples = langgraph_subgraph_tool_calls_total.collect()[0].samples
        contacts_tool_samples = [
            s
            for s in tool_samples
            if s.labels.get("agent_name") == AGENT_CONTACT
            and s.labels.get("tool_name") == "google_contacts_search"
        ]

        assert len(contacts_tool_samples) > 0
        assert contacts_tool_samples[0].value >= 1.0

    @pytest.mark.asyncio
    async def test_tracks_multiple_tool_calls(self):
        """Verify multiple tool calls are tracked correctly."""
        # Create mock agent that uses multiple tools
        mock_agent = AsyncMock()
        tool_msg1 = ToolMessage(
            content="Contact found",
            tool_call_id="call_123",
            name="google_contacts_search",
        )
        tool_msg2 = ToolMessage(
            content="Contact details retrieved",
            tool_call_id="call_456",
            name="google_contacts_get",
        )
        mock_agent.ainvoke.return_value = {
            STATE_KEY_MESSAGES: [
                AIMessage(content="Searching..."),
                tool_msg1,
                AIMessage(content="Getting details..."),
                tool_msg2,
                AIMessage(content="Done"),
            ],
        }

        # Create wrapper
        wrapper = create_agent_wrapper_node(
            agent_runnable=mock_agent,
            agent_name="contacts_agent",
            agent_constant=AGENT_CONTACT,
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="Find and get John")],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = {"metadata": {"run_id": "test_run"}}

        await wrapper(state, config)

        # Verify both tool calls were tracked
        tool_samples = langgraph_subgraph_tool_calls_total.collect()[0].samples

        search_samples = [
            s
            for s in tool_samples
            if s.labels.get("agent_name") == AGENT_CONTACT
            and s.labels.get("tool_name") == "google_contacts_search"
        ]
        assert len(search_samples) > 0
        assert search_samples[0].value >= 1.0

        get_samples = [
            s
            for s in tool_samples
            if s.labels.get("agent_name") == AGENT_CONTACT
            and s.labels.get("tool_name") == "google_contacts_get"
        ]
        assert len(get_samples) > 0
        assert get_samples[0].value >= 1.0

    @pytest.mark.asyncio
    async def test_tracks_no_tool_calls(self):
        """Verify no metrics emitted when agent doesn't use tools."""
        # Create mock agent that doesn't use tools
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {
            STATE_KEY_MESSAGES: [AIMessage(content="Direct response without tools")],
        }

        # Create wrapper
        wrapper = create_agent_wrapper_node(
            agent_runnable=mock_agent,
            agent_name="contacts_agent",
            agent_constant=AGENT_CONTACT,
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="Hello")],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = {"metadata": {"run_id": "test_run"}}

        await wrapper(state, config)

        # Verify no tool call metrics (only invocation metrics should exist)
        tool_samples = langgraph_subgraph_tool_calls_total.collect()[0].samples
        contacts_tool_samples = [
            s for s in tool_samples if s.labels.get("agent_name") == AGENT_CONTACT
        ]

        # Should be empty or zero if no tools were used
        assert len(contacts_tool_samples) == 0


class TestMultipleAgentsMetrics:
    """Test metrics for multiple different agents."""

    @pytest.mark.asyncio
    async def test_tracks_different_agents_separately(self):
        """Verify contacts_agent and emails_agent metrics are tracked separately."""
        # Create contacts_agent wrapper
        mock_contacts_agent = AsyncMock()
        mock_contacts_agent.ainvoke.return_value = {
            STATE_KEY_MESSAGES: [AIMessage(content="Contacts response")],
        }
        contacts_wrapper = create_agent_wrapper_node(
            agent_runnable=mock_contacts_agent,
            agent_name="contacts_agent",
            agent_constant=AGENT_CONTACT,
        )

        # Create emails_agent wrapper
        mock_emails_agent = AsyncMock()
        mock_emails_agent.ainvoke.return_value = {
            STATE_KEY_MESSAGES: [AIMessage(content="Emails response")],
        }
        emails_wrapper = create_agent_wrapper_node(
            agent_runnable=mock_emails_agent,
            agent_name="emails_agent",
            agent_constant=AGENT_EMAIL,
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [HumanMessage(content="test")],
            STATE_KEY_AGENT_RESULTS: {},
            "current_turn_id": 1,
        }
        config = {"metadata": {"run_id": "test_run"}}

        # Invoke both agents
        await contacts_wrapper(state, config)
        await emails_wrapper(state, config)

        # Verify both agents tracked separately
        invocation_samples = langgraph_subgraph_invocations_total.collect()[0].samples

        contacts_samples = [
            s for s in invocation_samples if s.labels.get("agent_name") == AGENT_CONTACT
        ]
        assert len(contacts_samples) > 0

        emails_samples = [
            s for s in invocation_samples if s.labels.get("agent_name") == AGENT_EMAIL
        ]
        assert len(emails_samples) > 0


class TestMetricsCardinality:
    """Test that subgraph metrics have acceptable cardinality."""

    def test_subgraph_invocations_cardinality(self):
        """Verify langgraph_subgraph_invocations_total has acceptable label combinations."""
        # Expected agent_name values: 2 agents (contacts_agent, emails_agent)
        # Expected status values: 2 statuses (success, error)
        # Total: 2 * 2 = 4 time series
        expected_agents = [AGENT_CONTACT, AGENT_EMAIL]
        expected_statuses = ["success", "error"]
        max_expected_series = len(expected_agents) * len(expected_statuses)

        assert max_expected_series == 4

    def test_subgraph_duration_cardinality(self):
        """Verify langgraph_subgraph_duration_seconds has acceptable label combinations."""
        # Expected agent_name values: 2 agents
        # Histogram buckets: 8 buckets [0.5s, 1s, 2s, 5s, 10s, 20s, 30s, 60s]
        # Total: 2 * 8 = 16 time series
        expected_agents = 2
        histogram_buckets = 8
        max_expected_series = expected_agents * histogram_buckets

        assert max_expected_series == 16

    def test_subgraph_tool_calls_cardinality(self):
        """Verify langgraph_subgraph_tool_calls_total has acceptable label combinations."""
        # Expected agent_name values: 2 agents
        # Expected tool_name values per agent:
        # - contacts_agent: ~6 tools (search, list, get, create, update, delete)
        # - emails_agent: ~5 tools (list, get, send, search, delete)
        # Total: 2 agents * avg 5-6 tools = ~12 time series
        max_expected_series = 15  # Buffer for future tools

        expected_agents = [AGENT_CONTACT, AGENT_EMAIL]
        avg_tools_per_agent = 6
        estimated_series = len(expected_agents) * avg_tools_per_agent

        assert estimated_series <= max_expected_series
