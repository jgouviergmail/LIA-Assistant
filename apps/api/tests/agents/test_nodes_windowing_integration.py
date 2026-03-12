"""
Integration tests for message windowing in router, planner, and response nodes.

These tests validate that windowing is correctly applied in each node
and that the system maintains functional correctness while reducing latency.
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.domains.agents.constants import STATE_KEY_MESSAGES
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes import router_node


@pytest.fixture
def mock_runnable_config():
    """Create mock RunnableConfig for node execution."""
    return {
        "configurable": {
            "thread_id": "test-thread-123",
            "user_id": "test-user-456",
        },
        "run_id": "test-run-789",
    }


@pytest.fixture
def short_conversation_state():
    """Create state with short conversation (< window size)."""
    return MessagesState(
        messages=[
            SystemMessage(content="You are a helpful assistant"),
            HumanMessage(content="Turn 1: Hello"),
            AIMessage(content="Turn 1: Hi there!"),
            HumanMessage(content="Turn 2: How are you?"),
        ]
    )


@pytest.fixture
def long_conversation_state():
    """Create state with long conversation (> router window size of 5)."""
    messages = [SystemMessage(content="You are a helpful assistant")]

    # Add 20 conversation turns (40 messages)
    for i in range(1, 21):
        messages.append(HumanMessage(content=f"Turn {i} user message"))
        messages.append(AIMessage(content=f"Turn {i} assistant response"))

    return MessagesState(messages=messages)


@pytest.fixture
def conversation_with_tool_execution():
    """Create state with tool execution that should be filtered."""
    return MessagesState(
        messages=[
            SystemMessage(content="You are a helpful assistant"),
            HumanMessage(content="Search contacts named John"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "search", "args": {"query": "John"}}],
            ),
            ToolMessage(content='{"results": [...]}', tool_call_id="call_1"),
            AIMessage(content="Found 3 contacts named John"),
            HumanMessage(content="Show me the first one"),
        ]
    )


class TestRouterNodeWindowing:
    """Test router_node with message windowing."""

    @pytest.mark.asyncio
    async def test_router_receives_windowed_messages_short_conversation(
        self, short_conversation_state, mock_runnable_config
    ):
        """Router should receive all messages when conversation is short."""
        with patch("src.domains.agents.nodes.router_node._call_router_llm") as mock_llm:
            mock_llm.return_value = RouterOutput(
                intention="simple_conversation",
                confidence=0.9,
                context_label="greeting",
                next_node="response",
                reasoning="Simple greeting",
            )

            # Execute router node
            await router_node(short_conversation_state, mock_runnable_config)

            # Verify LLM was called with windowed messages
            assert mock_llm.called
            messages_arg = mock_llm.call_args[1]["messages"]

            # Short conversation should have all messages (window > conversation size)
            assert len(messages_arg) == 4  # 1 SystemMessage + 3 conversational

    @pytest.mark.asyncio
    async def test_router_receives_windowed_messages_long_conversation(
        self, long_conversation_state, mock_runnable_config
    ):
        """Router should receive only recent messages when conversation is long.

        Windowing should reduce the message count significantly for long conversations.
        The exact count depends on configured window size, but it should be less than original.
        """
        with patch("src.domains.agents.nodes.router_node._call_router_llm") as mock_llm:
            mock_llm.return_value = RouterOutput(
                intention="simple_conversation",
                confidence=0.9,
                context_label="chat",
                next_node="response",
                reasoning="Casual chat",
            )

            original_count = len(long_conversation_state[STATE_KEY_MESSAGES])  # 41

            # Execute router node
            await router_node(long_conversation_state, mock_runnable_config)

            # Verify LLM was called with windowed messages
            assert mock_llm.called
            messages_arg = mock_llm.call_args[1]["messages"]

            # Key assertion: windowing should reduce message count
            assert len(messages_arg) < original_count, "Windowing should reduce message count"

            # Verify SystemMessage is first
            assert isinstance(messages_arg[0], SystemMessage)

            # Verify we have recent messages (last turn should be Turn 20)
            human_messages = [m for m in messages_arg if isinstance(m, HumanMessage)]
            assert len(human_messages) > 0, "Should have at least one HumanMessage"
            assert (
                "Turn 20 user message" in human_messages[-1].content
            ), "Last turn should be Turn 20"

    @pytest.mark.asyncio
    async def test_router_filters_tool_messages(
        self, conversation_with_tool_execution, mock_runnable_config
    ):
        """Router should not receive ToolMessages or AIMessages with tool_calls."""
        with patch("src.domains.agents.nodes.router_node._call_router_llm") as mock_llm:
            mock_llm.return_value = RouterOutput(
                intention="complex_multi_step",
                confidence=0.85,
                context_label="search",
                next_node="planner",
                reasoning="Search query",
            )

            # Execute router node
            await router_node(conversation_with_tool_execution, mock_runnable_config)

            # Verify LLM was called
            assert mock_llm.called
            messages_arg = mock_llm.call_args[1]["messages"]

            # Should have: SystemMessage + 2 HumanMessages + 1 AIMessage (without tool_calls)
            assert len(messages_arg) == 4

            # Verify no ToolMessages
            assert not any(isinstance(m, ToolMessage) for m in messages_arg)

            # Verify no AIMessages with tool_calls
            ai_messages = [m for m in messages_arg if isinstance(m, AIMessage)]
            assert all(not hasattr(m, "tool_calls") or not m.tool_calls for m in ai_messages)


class TestPlannerNodeWindowing:
    """Test planner_node with message windowing.

    Note: Planner node uses SmartPlannerService (v3) internally which handles windowing via
    _prepare_planner_inputs. These tests verify the windowing utility functions
    work correctly for planner's use case rather than mocking internal node structure.
    """

    @pytest.mark.asyncio
    async def test_planner_windowing_utility_reduces_messages(self, long_conversation_state):
        """Verify the windowing utility correctly reduces messages for planner.

        Tests the windowing function directly to ensure it works correctly
        for planner's use case (10 turns by default).
        """
        from src.domains.agents.utils.message_windowing import get_planner_windowed_messages

        original_count = len(long_conversation_state[STATE_KEY_MESSAGES])

        # Apply windowing with planner settings
        windowed = get_planner_windowed_messages(long_conversation_state[STATE_KEY_MESSAGES])

        # Verify windowing reduces message count
        assert len(windowed) < original_count, "Windowing should reduce messages"

        # Verify SystemMessage is preserved if present
        system_messages = [m for m in windowed if isinstance(m, SystemMessage)]
        if any(isinstance(m, SystemMessage) for m in long_conversation_state[STATE_KEY_MESSAGES]):
            assert len(system_messages) == 1, "SystemMessage should be preserved"

    @pytest.mark.asyncio
    async def test_planner_windowing_preserves_last_user_message(self, long_conversation_state):
        """Verify windowing preserves the most recent user message.

        Critical for planner to understand the current request.
        """
        from src.domains.agents.utils.message_windowing import get_planner_windowed_messages

        # Apply windowing
        windowed = get_planner_windowed_messages(long_conversation_state[STATE_KEY_MESSAGES])

        # Get last user message from windowed
        human_messages = [m for m in windowed if isinstance(m, HumanMessage)]
        assert len(human_messages) > 0, "Should have at least one HumanMessage"

        # The last HumanMessage should be Turn 20 (most recent)
        assert "Turn 20 user message" in human_messages[-1].content


class TestResponseNodeWindowing:
    """Test response_node with message windowing.

    Note: Response node uses a chain pattern internally (prompt | llm).
    These tests verify the windowing utility functions work correctly for response's use case.
    """

    @pytest.mark.asyncio
    async def test_response_windowing_utility_for_long_conversation(self, long_conversation_state):
        """Verify the windowing utility correctly handles long conversations for response.

        Tests the windowing and filtering functions directly.
        """
        from src.domains.agents.utils.message_filters import filter_conversational_messages
        from src.domains.agents.utils.message_windowing import get_response_windowed_messages

        original_messages = long_conversation_state[STATE_KEY_MESSAGES]

        # Step 1: Apply windowing with response settings
        windowed = get_response_windowed_messages(original_messages)

        # Step 2: Filter to conversational only (removes SystemMessage, ToolMessages, etc.)
        conversational = filter_conversational_messages(windowed)

        # Verify filtering worked - no SystemMessage in filtered result
        assert not any(isinstance(m, SystemMessage) for m in conversational)
        assert not any(isinstance(m, ToolMessage) for m in conversational)

        # Verify we have conversational messages
        assert len(conversational) > 0, "Should have conversational messages"

    @pytest.mark.asyncio
    async def test_response_filtering_removes_tool_messages(self, conversation_with_tool_execution):
        """Verify response filtering removes ToolMessages and AIMessages with tool_calls."""
        from src.domains.agents.utils.message_filters import filter_conversational_messages

        original_messages = conversation_with_tool_execution[STATE_KEY_MESSAGES]

        # Filter to conversational
        conversational = filter_conversational_messages(original_messages)

        # Verify no ToolMessages
        assert not any(isinstance(m, ToolMessage) for m in conversational)

        # Verify no AIMessages with tool_calls
        ai_messages = [m for m in conversational if isinstance(m, AIMessage)]
        for ai_msg in ai_messages:
            tool_calls = getattr(ai_msg, "tool_calls", None)
            assert not tool_calls, f"AIMessage should not have tool_calls: {ai_msg}"

        # Should have: 2 HumanMessages + 1 AIMessage (without tool_calls)
        # The AIMessage with tool_calls should be filtered out
        human_count = len([m for m in conversational if isinstance(m, HumanMessage)])
        ai_count = len(ai_messages)
        assert human_count == 2, f"Expected 2 HumanMessages, got {human_count}"
        assert ai_count == 1, f"Expected 1 AIMessage (without tool_calls), got {ai_count}"


class TestWindowingConfiguration:
    """Test that windowing respects configuration settings."""

    @pytest.mark.asyncio
    async def test_router_window_size_configurable(
        self, long_conversation_state, mock_runnable_config
    ):
        """Router window size should be configurable via settings."""
        with (
            patch("src.domains.agents.nodes.router_node._call_router_llm") as mock_llm,
            patch("src.domains.agents.utils.message_windowing.settings") as mock_settings,
        ):
            # Configure smaller window size
            mock_settings.router_message_window_size = 2  # Only 2 turns

            mock_llm.return_value = RouterOutput(
                intention="simple_conversation",
                confidence=0.9,
                context_label="chat",
                next_node="response",
                reasoning="Chat",
            )

            # Execute router node
            await router_node(long_conversation_state, mock_runnable_config)

            # Verify smaller window was applied
            assert mock_llm.called
            messages_arg = mock_llm.call_args[1]["messages"]

            # Should have 1 SystemMessage + 4 conversational (2 turns)
            assert len(messages_arg) == 5


class TestWindowingFunctionalCorrectness:
    """Test that windowing doesn't break functionality."""

    @pytest.mark.asyncio
    async def test_router_still_makes_correct_routing_decision(
        self, long_conversation_state, mock_runnable_config
    ):
        """Router should still make correct routing decisions with windowing."""
        with patch("src.domains.agents.nodes.router_node._call_router_llm") as mock_llm:
            mock_llm.return_value = RouterOutput(
                intention="simple_conversation",
                confidence=0.9,
                context_label="chat",
                next_node="response",
                reasoning="Casual conversation",
            )

            # Execute router node
            result = await router_node(long_conversation_state, mock_runnable_config)

            # Verify routing decision is returned correctly
            # Router node returns routing_history (list of RouterOutput)
            assert "routing_history" in result
            assert result["routing_history"][0].next_node == "response"

    @pytest.mark.asyncio
    async def test_system_message_always_preserved(
        self, long_conversation_state, mock_runnable_config
    ):
        """SystemMessage should always be preserved regardless of window size."""
        with patch("src.domains.agents.nodes.router_node._call_router_llm") as mock_llm:
            mock_llm.return_value = RouterOutput(
                intention="simple_conversation",
                confidence=0.9,
                context_label="chat",
                next_node="response",
                reasoning="Chat",
            )

            # Execute router node
            await router_node(long_conversation_state, mock_runnable_config)

            # Verify SystemMessage is first in windowed messages
            assert mock_llm.called
            messages_arg = mock_llm.call_args[1]["messages"]
            assert isinstance(messages_arg[0], SystemMessage)
            assert messages_arg[0].content == "You are a helpful assistant"


class TestWindowingPerformanceImpact:
    """Test that windowing reduces message count as expected."""

    @pytest.mark.asyncio
    async def test_windowing_reduces_message_count(
        self, long_conversation_state, mock_runnable_config
    ):
        """Windowing should significantly reduce message count for long conversations."""
        original_message_count = len(long_conversation_state[STATE_KEY_MESSAGES])
        assert original_message_count == 41  # 1 SystemMessage + 40 conversational

        with patch("src.domains.agents.nodes.router_node._call_router_llm") as mock_llm:
            mock_llm.return_value = RouterOutput(
                intention="simple_conversation",
                confidence=0.9,
                context_label="chat",
                next_node="response",
                reasoning="Chat",
            )

            # Execute router node
            await router_node(long_conversation_state, mock_runnable_config)

            # Verify windowed message count
            assert mock_llm.called
            messages_arg = mock_llm.call_args[1]["messages"]
            windowed_count = len(messages_arg)

            # Windowed count should be significantly less than original
            assert windowed_count < original_message_count, "Windowing should reduce message count"

            # Calculate reduction
            reduction_percent = (1 - windowed_count / original_message_count) * 100
            # Should reduce by at least 50% for a 41-message conversation
            assert reduction_percent > 50, f"Expected >50% reduction, got {reduction_percent}%"

    @pytest.mark.asyncio
    async def test_no_windowing_overhead_for_short_conversations(
        self, short_conversation_state, mock_runnable_config
    ):
        """Short conversations should not be truncated by windowing."""
        original_message_count = len(short_conversation_state[STATE_KEY_MESSAGES])

        with patch("src.domains.agents.nodes.router_node._call_router_llm") as mock_llm:
            mock_llm.return_value = RouterOutput(
                intention="simple_conversation",
                confidence=0.9,
                context_label="greeting",
                next_node="response",
                reasoning="Greeting",
            )

            # Execute router node
            await router_node(short_conversation_state, mock_runnable_config)

            # Verify all messages are kept (window size > conversation length)
            assert mock_llm.called
            messages_arg = mock_llm.call_args[1]["messages"]

            # All messages should be preserved
            assert len(messages_arg) == original_message_count
