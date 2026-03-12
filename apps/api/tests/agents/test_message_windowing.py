"""
Unit tests for message windowing utilities.

Tests the message_windowing module which reduces token count and latency
by keeping only recent conversation turns while preserving context.
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.domains.agents.utils.message_windowing import (
    extract_last_user_message,
    get_planner_windowed_messages,
    get_response_windowed_messages,
    get_router_windowed_messages,
    get_windowed_messages,
)


class TestGetWindowedMessages:
    """Test the core get_windowed_messages function."""

    def test_empty_messages(self):
        """Should handle empty message list."""
        result = get_windowed_messages([], window_size=5)
        assert result == []

    def test_system_message_always_included(self):
        """Should always include SystemMessage regardless of window size."""
        messages = [
            SystemMessage(content="You are a helpful assistant"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]

        result = get_windowed_messages(messages, window_size=1)

        # Should have SystemMessage + last 2 messages (1 turn)
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert result[1].content == "Hello"
        assert result[2].content == "Hi there!"

    def test_system_message_excluded_when_disabled(self):
        """Should exclude SystemMessage when include_system=False."""
        messages = [
            SystemMessage(content="You are a helpful assistant"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]

        result = get_windowed_messages(messages, window_size=1, include_system=False)

        # Should have only last 2 messages (1 turn), no SystemMessage
        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "Hi there!"

    def test_window_larger_than_history(self):
        """Should return all conversational messages when window > history."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Turn 1 user"),
            AIMessage(content="Turn 1 assistant"),
            HumanMessage(content="Turn 2 user"),
            AIMessage(content="Turn 2 assistant"),
        ]

        result = get_windowed_messages(messages, window_size=10)  # Large window

        # Should return all messages (window larger than history)
        assert len(result) == 5  # 1 system + 4 conversational

    def test_window_size_exactly_matches_history(self):
        """Should return all messages when window size == number of turns."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Turn 1 user"),
            AIMessage(content="Turn 1 assistant"),
            HumanMessage(content="Turn 2 user"),
            AIMessage(content="Turn 2 assistant"),
        ]

        result = get_windowed_messages(messages, window_size=2)  # Exactly 2 turns

        # Should return all messages
        assert len(result) == 5  # 1 system + 4 conversational

    def test_window_smaller_than_history(self):
        """Should keep only last N turns when window < history."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Turn 1 user"),
            AIMessage(content="Turn 1 assistant"),
            HumanMessage(content="Turn 2 user"),
            AIMessage(content="Turn 2 assistant"),
            HumanMessage(content="Turn 3 user"),
            AIMessage(content="Turn 3 assistant"),
        ]

        result = get_windowed_messages(messages, window_size=1)  # Last 1 turn only

        # Should have SystemMessage + last 2 messages (1 turn)
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert result[1].content == "Turn 3 user"
        assert result[2].content == "Turn 3 assistant"

    def test_filters_tool_messages(self):
        """Should filter out ToolMessages (internal tool execution details)."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Search contacts"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content='{"results": [...]}', tool_call_id="call_1"),
            AIMessage(content="Found 3 contacts"),
            HumanMessage(content="Show details"),
            AIMessage(content="Here are the details"),
        ]

        result = get_windowed_messages(messages, window_size=2)

        # Should exclude ToolMessage and AIMessage with tool_calls
        # Keeps: SystemMessage + 4 conversational (2 HumanMessage + 2 AIMessage)
        # With window_size=2, we can keep up to 4 messages (2 turns * 2)
        # Conversational messages after filtering: 4 messages total
        # Result: All 4 conversational + SystemMessage = 5 total
        assert len(result) == 5
        assert isinstance(result[0], SystemMessage)
        # Messages are in chronological order after SystemMessage
        assert result[1].content == "Search contacts"
        assert result[2].content == "Found 3 contacts"
        assert result[3].content == "Show details"
        assert result[4].content == "Here are the details"

    def test_multiple_system_messages(self):
        """Should handle multiple SystemMessages correctly."""
        messages = [
            SystemMessage(content="System 1"),
            SystemMessage(content="System 2"),
            HumanMessage(content="User message"),
            AIMessage(content="AI response"),
        ]

        result = get_windowed_messages(messages, window_size=1)

        # Should have 2 SystemMessages + last 2 conversational
        assert len(result) == 4
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], SystemMessage)

    def test_window_size_zero(self):
        """Should return only SystemMessages when window_size=0."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="User"),
            AIMessage(content="Assistant"),
        ]

        result = get_windowed_messages(messages, window_size=0)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)

    def test_window_size_negative(self):
        """Should return only SystemMessages when window_size is negative."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="User"),
            AIMessage(content="Assistant"),
        ]

        result = get_windowed_messages(messages, window_size=-5)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)

    def test_long_conversation_windowing(self):
        """Test windowing with a long 50-turn conversation."""
        messages = [SystemMessage(content="System")]

        # Add 50 turns
        for i in range(1, 51):
            messages.append(HumanMessage(content=f"Turn {i} user"))
            messages.append(AIMessage(content=f"Turn {i} assistant"))

        # Window size = 5 turns (last 5 turns only)
        result = get_windowed_messages(messages, window_size=5)

        # Should have 1 SystemMessage + 10 messages (5 turns = 5 HumanMessage + 5 AIMessage)
        assert len(result) == 11
        assert isinstance(result[0], SystemMessage)

        # Check that we have turns 46-50 (last 5)
        assert "Turn 46 user" in result[1].content
        assert "Turn 46 assistant" in result[2].content
        assert "Turn 50 user" in result[9].content
        assert "Turn 50 assistant" in result[10].content

    def test_preserves_message_order(self):
        """Should preserve chronological order of messages."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="First"),
            AIMessage(content="Second"),
            HumanMessage(content="Third"),
            AIMessage(content="Fourth"),
        ]

        result = get_windowed_messages(messages, window_size=1)

        # SystemMessage first, then chronological
        assert result[0].content == "System"
        assert result[1].content == "Third"
        assert result[2].content == "Fourth"


class TestPrebuiltWindowFunctions:
    """Test the prebuilt window functions for specific nodes."""

    def test_router_windowed_messages(self):
        """Test get_router_windowed_messages uses correct window size."""
        messages = [SystemMessage(content="System")]

        # Add 20 turns
        for i in range(1, 21):
            messages.append(HumanMessage(content=f"Turn {i} user"))
            messages.append(AIMessage(content=f"Turn {i} assistant"))

        result = get_router_windowed_messages(messages)

        # Router default: 5 turns (settings.router_message_window_size)
        # Should have 1 SystemMessage + 10 messages (5 turns)
        assert len(result) == 11
        assert "Turn 16 user" in result[1].content  # Last 5 turns start at turn 16

    def test_planner_windowed_messages(self):
        """Test get_planner_windowed_messages uses correct window size."""
        messages = [SystemMessage(content="System")]

        # Add 20 turns
        for i in range(1, 21):
            messages.append(HumanMessage(content=f"Turn {i} user"))
            messages.append(AIMessage(content=f"Turn {i} assistant"))

        result = get_planner_windowed_messages(messages)

        # Planner default: 10 turns (settings.planner_message_window_size)
        # Should have 1 SystemMessage + 20 messages (10 turns)
        assert len(result) == 21
        assert "Turn 11 user" in result[1].content  # Last 10 turns start at turn 11

    def test_response_windowed_messages(self):
        """Test get_response_windowed_messages uses correct window size."""
        messages = [SystemMessage(content="System")]

        # Add 30 turns
        for i in range(1, 31):
            messages.append(HumanMessage(content=f"Turn {i} user"))
            messages.append(AIMessage(content=f"Turn {i} assistant"))

        result = get_response_windowed_messages(messages)

        # Response default: 20 turns (settings.response_message_window_size)
        # Should have 1 SystemMessage + 40 messages (20 turns)
        assert len(result) == 41
        assert "Turn 11 user" in result[1].content  # Last 20 turns start at turn 11


class TestExtractLastUserMessage:
    """Test the extract_last_user_message utility function."""

    def test_extracts_last_user_message(self):
        """Should extract content from last HumanMessage."""
        messages = [
            HumanMessage(content="First user message"),
            AIMessage(content="First AI response"),
            HumanMessage(content="Second user message"),
            AIMessage(content="Second AI response"),
        ]

        result = extract_last_user_message(messages)

        assert result == "Second user message"

    def test_empty_message_list(self):
        """Should return None for empty message list."""
        result = extract_last_user_message([])
        assert result is None

    def test_no_user_messages(self):
        """Should return None when no HumanMessage found."""
        messages = [
            SystemMessage(content="System"),
            AIMessage(content="AI response"),
        ]

        result = extract_last_user_message(messages)
        assert result is None

    def test_only_user_message(self):
        """Should extract the only user message."""
        messages = [HumanMessage(content="Only user message")]

        result = extract_last_user_message(messages)
        assert result == "Only user message"

    def test_user_message_not_last(self):
        """Should extract last user message even if not the final message."""
        messages = [
            HumanMessage(content="User message"),
            AIMessage(content="AI response"),
            SystemMessage(content="System message at end"),
        ]

        result = extract_last_user_message(messages)
        assert result == "User message"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_only_system_messages(self):
        """Should handle conversation with only SystemMessages."""
        messages = [
            SystemMessage(content="System 1"),
            SystemMessage(content="System 2"),
        ]

        result = get_windowed_messages(messages, window_size=5)

        # Should return all SystemMessages
        assert len(result) == 2
        assert all(isinstance(m, SystemMessage) for m in result)

    def test_alternating_multiple_ai_messages(self):
        """Should handle multiple AI messages in a row (streaming scenario)."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="User query"),
            AIMessage(content="Thinking..."),
            AIMessage(content="Still thinking..."),
            AIMessage(content="Final answer"),
        ]

        result = get_windowed_messages(messages, window_size=1)

        # With window_size=1, we keep last 2 conversational messages
        # The function keeps last (window_size * 2) messages after filtering
        # Conversational messages: HumanMessage + 3 AIMessages = 4 messages
        # Last 2 conversational: last 2 AIMessages
        # Result: SystemMessage + 2 AIMessages = 3 total
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert "Still thinking..." in result[1].content
        assert "Final answer" in result[2].content

    def test_none_window_size_uses_default(self):
        """Should use settings.default_message_window_size when window_size=None."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="User"),
            AIMessage(content="Assistant"),
        ]

        result = get_windowed_messages(messages, window_size=None)

        # Should use default (5 turns)
        # With only 1 turn, should return all messages
        assert len(result) == 3
