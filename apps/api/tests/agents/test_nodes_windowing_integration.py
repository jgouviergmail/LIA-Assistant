"""
Integration tests for message windowing in router, planner, and response nodes.

These tests validate that windowing is correctly applied in each node
and that the system maintains functional correctness while reducing latency.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.domains.agents.constants import STATE_KEY_MESSAGES
from src.domains.agents.models import MessagesState


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


# ADR-094: TestPlannerNodeWindowing removed — the planner uses SmartPlannerService
# (_prepare_planner_inputs), never get_planner_windowed_messages (dead helper, deleted).


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
