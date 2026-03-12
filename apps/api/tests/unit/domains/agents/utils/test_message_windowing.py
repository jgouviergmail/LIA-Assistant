"""
Unit tests for message windowing utilities.

Tests for message windowing functions that optimize LLM latency
by creating message "windows" - keeping only recent conversation turns.
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.domains.agents.utils.message_windowing import (
    extract_last_user_message,
    get_orchestrator_windowed_messages,
    get_planner_windowed_messages,
    get_response_windowed_messages,
    get_router_windowed_messages,
    get_windowed_messages,
)

# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def simple_conversation():
    """Simple conversation with 3 turns."""
    return [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Q1"),
        AIMessage(content="A1"),
        HumanMessage(content="Q2"),
        AIMessage(content="A2"),
        HumanMessage(content="Q3"),
        AIMessage(content="A3"),
    ]


@pytest.fixture
def conversation_with_tools():
    """Conversation with tool calls."""
    return [
        SystemMessage(content="System prompt"),
        HumanMessage(content="Search contacts"),
        AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
        ToolMessage(content='{"results": []}', tool_call_id="call_1"),
        AIMessage(content="No contacts found."),
        HumanMessage(content="Try again"),
        AIMessage(content="", tool_calls=[{"id": "call_2", "name": "search", "args": {}}]),
        ToolMessage(content='{"results": ["John"]}', tool_call_id="call_2"),
        AIMessage(content="Found John!"),
    ]


@pytest.fixture
def long_conversation():
    """Long conversation with 20 turns."""
    messages = [SystemMessage(content="System")]
    for i in range(20):
        messages.append(HumanMessage(content=f"Question {i}"))
        messages.append(AIMessage(content=f"Answer {i}"))
    return messages


@pytest.fixture
def mock_settings():
    """Mock settings with default values."""
    mock = MagicMock()
    mock.default_message_window_size = 5
    mock.router_message_window_size = 5
    mock.planner_message_window_size = 10
    mock.response_message_window_size = 20
    mock.orchestrator_message_window_size = 4
    return mock


# ============================================================================
# Tests for get_windowed_messages - Basic
# ============================================================================


class TestGetWindowedMessagesBasic:
    """Basic tests for get_windowed_messages()."""

    def test_empty_messages_returns_empty_list(self):
        """Test that empty message list returns empty list."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages([])
        assert result == []

    def test_returns_all_messages_if_window_larger_than_history(self):
        """Test that all messages returned if window covers entire history."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=10)

        # SystemMessage + 2 conversational messages
        assert len(result) == 3

    def test_window_size_zero_returns_only_system_messages(self):
        """Test that window_size=0 returns only system messages."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=0)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)

    def test_negative_window_size_returns_only_system_messages(self):
        """Test that negative window_size returns only system messages."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=-1)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)

    def test_include_system_false_excludes_system_messages(self):
        """Test that include_system=False excludes system messages."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=5, include_system=False)

        for msg in result:
            assert not isinstance(msg, SystemMessage)

    def test_include_system_false_with_zero_window_returns_empty(self):
        """Test that include_system=False with window_size=0 returns empty."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="Hello"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=0, include_system=False)

        assert result == []

    def test_single_message_returns_single_message(self):
        """Test with single message."""
        messages = [HumanMessage(content="Hello")]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=5)

        assert len(result) == 1
        assert result[0].content == "Hello"

    def test_only_system_messages_returns_only_system(self):
        """Test with only system messages."""
        messages = [
            SystemMessage(content="System 1"),
            SystemMessage(content="System 2"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=5)

        # Only system messages, no conversational
        assert len(result) == 2
        assert all(isinstance(m, SystemMessage) for m in result)


# ============================================================================
# Tests for get_windowed_messages - Filtering
# ============================================================================


class TestGetWindowedMessagesFiltering:
    """Tests for message filtering in get_windowed_messages()."""

    def test_filters_out_tool_messages(self, conversation_with_tools):
        """Test that ToolMessages are filtered out."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(conversation_with_tools, window_size=10)

        # Should not contain any ToolMessage
        for msg in result:
            assert not isinstance(msg, ToolMessage)

    def test_filters_out_ai_messages_with_tool_calls(self, conversation_with_tools):
        """Test that AIMessages with tool_calls are filtered out."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(conversation_with_tools, window_size=10)

        # Check no AIMessage with tool_calls
        for msg in result:
            if isinstance(msg, AIMessage):
                assert not (hasattr(msg, "tool_calls") and msg.tool_calls)

    def test_keeps_human_messages(self):
        """Test that HumanMessages are preserved."""
        messages = [
            HumanMessage(content="First question"),
            AIMessage(content="Answer 1"),
            HumanMessage(content="Second question"),
            AIMessage(content="Answer 2"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=10)

        human_count = sum(1 for m in result if isinstance(m, HumanMessage))
        assert human_count == 2

    def test_keeps_conversational_ai_messages(self):
        """Test that AIMessages without tool_calls are preserved."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            HumanMessage(content="How are you?"),
            AIMessage(content="I'm doing well."),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=10)

        ai_count = sum(1 for m in result if isinstance(m, AIMessage))
        assert ai_count == 2

    def test_mixed_conversation_filtering(self, conversation_with_tools):
        """Test filtering a conversation with mixed message types."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(conversation_with_tools, window_size=10)

        # Should have:
        # - 1 SystemMessage
        # - 2 HumanMessages
        # - 2 conversational AIMessages (the ones without tool_calls)
        assert len(result) == 5


# ============================================================================
# Tests for get_windowed_messages - Windowing
# ============================================================================


class TestGetWindowedMessagesWindowing:
    """Tests for actual windowing behavior."""

    def test_window_size_1_keeps_2_conversational_messages(self, simple_conversation):
        """Test that window_size=1 keeps last 2 conversational messages (1 turn)."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(simple_conversation, window_size=1)

        # Should have SystemMessage + last 2 conversational messages
        conversational = [m for m in result if not isinstance(m, SystemMessage)]
        assert len(conversational) == 2
        assert conversational[0].content == "Q3"
        assert conversational[1].content == "A3"

    def test_window_size_2_keeps_4_conversational_messages(self, simple_conversation):
        """Test that window_size=2 keeps last 4 conversational messages (2 turns)."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(simple_conversation, window_size=2)

        conversational = [m for m in result if not isinstance(m, SystemMessage)]
        assert len(conversational) == 4
        # Should be Q2, A2, Q3, A3
        assert conversational[0].content == "Q2"
        assert conversational[3].content == "A3"

    def test_window_size_3_keeps_6_conversational_messages(self, simple_conversation):
        """Test that window_size=3 keeps last 6 conversational messages (3 turns)."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(simple_conversation, window_size=3)

        conversational = [m for m in result if not isinstance(m, SystemMessage)]
        # simple_conversation has only 3 turns, so all 6 conversational messages
        assert len(conversational) == 6

    def test_system_message_always_first(self):
        """Test that system messages come first in output."""
        messages = [
            HumanMessage(content="Q1"),
            SystemMessage(content="System"),
            AIMessage(content="A1"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=5)

        # System message should be first
        assert isinstance(result[0], SystemMessage)

    def test_preserves_chronological_order(self):
        """Test that message order is preserved within window."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=5)

        # After system, should be in order
        non_system = [m for m in result if not isinstance(m, SystemMessage)]
        assert non_system[0].content == "Q1"
        assert non_system[1].content == "A1"
        assert non_system[2].content == "Q2"
        assert non_system[3].content == "A2"

    def test_long_conversation_truncation(self, long_conversation):
        """Test that long conversations are properly truncated."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(long_conversation, window_size=5)

        # Should have system + 10 messages (5 turns)
        assert len(result) == 11

        # Verify last messages are the most recent
        non_system = [m for m in result if not isinstance(m, SystemMessage)]
        assert non_system[-1].content == "Answer 19"
        assert non_system[-2].content == "Question 19"


# ============================================================================
# Tests for get_windowed_messages - Default Window Size
# ============================================================================


class TestGetWindowedMessagesDefaultWindowSize:
    """Tests for default window size behavior."""

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_uses_default_window_size_from_settings(self, mock_settings, long_conversation):
        """Test that None window_size uses settings.default_message_window_size."""
        mock_settings.default_message_window_size = 3

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(long_conversation, window_size=None)

        # With window_size=3, should keep system + 6 conversational messages (3 turns)
        assert len(result) == 7  # 1 system + 6 conversational

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_uses_default_when_window_size_not_specified(self, mock_settings):
        """Test that window_size defaults from settings when not provided."""
        mock_settings.default_message_window_size = 2
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
            HumanMessage(content="Q3"),
            AIMessage(content="A3"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages)

        # With default 2, should keep system + 4 messages
        assert len(result) == 5


# ============================================================================
# Tests for get_windowed_messages - Logging
# ============================================================================


class TestGetWindowedMessagesLogging:
    """Tests for logging in get_windowed_messages()."""

    def test_logs_windowing_applied_when_truncating(self, long_conversation):
        """Test that debug log is emitted when windowing is applied."""
        with patch("src.domains.agents.utils.message_windowing.logger") as mock_logger:
            get_windowed_messages(long_conversation, window_size=5)

        # Should have debug log with windowing_applied
        debug_calls = [
            call for call in mock_logger.debug.call_args_list if call[0][0] == "windowing_applied"
        ]
        assert len(debug_calls) == 1

        # Verify kwargs
        call_kwargs = debug_calls[0][1]
        assert call_kwargs["window_size"] == 5
        assert "windowed_count" in call_kwargs

    def test_logs_windowing_skipped_for_small_history(self):
        """Test that debug log is emitted when history smaller than window."""
        messages = [
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger") as mock_logger:
            get_windowed_messages(messages, window_size=10)

        # Should have debug log with windowing_skipped
        debug_calls = [
            call
            for call in mock_logger.debug.call_args_list
            if call[0][0] == "windowing_skipped_small_history"
        ]
        assert len(debug_calls) == 1

    def test_logs_completion_info(self, simple_conversation):
        """Test that info log is emitted on completion."""
        with patch("src.domains.agents.utils.message_windowing.logger") as mock_logger:
            get_windowed_messages(simple_conversation, window_size=2)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "message_windowing_complete"

        call_kwargs = call_args[1]
        assert "input_messages" in call_kwargs
        assert "output_messages" in call_kwargs
        assert "reduction_percent" in call_kwargs


# ============================================================================
# Tests for get_router_windowed_messages
# ============================================================================


class TestGetRouterWindowedMessages:
    """Tests for get_router_windowed_messages()."""

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_uses_router_window_size_setting(self, mock_settings):
        """Test that router uses settings.router_message_window_size."""
        mock_settings.router_message_window_size = 5
        messages = [HumanMessage(content="Test")]

        with patch("src.domains.agents.utils.message_windowing.get_windowed_messages") as mock_get:
            with patch("src.domains.agents.utils.message_windowing.logger"):
                mock_get.return_value = []
                get_router_windowed_messages(messages)
                mock_get.assert_called_once_with(messages, window_size=5)

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_router_window_size_integration(self, mock_settings, long_conversation):
        """Test router windowing with actual messages."""
        mock_settings.router_message_window_size = 3

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_router_windowed_messages(long_conversation)

        # Should have system + 6 messages (3 turns)
        assert len(result) == 7


# ============================================================================
# Tests for get_planner_windowed_messages
# ============================================================================


class TestGetPlannerWindowedMessages:
    """Tests for get_planner_windowed_messages()."""

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_uses_planner_window_size_setting(self, mock_settings):
        """Test that planner uses settings.planner_message_window_size."""
        mock_settings.planner_message_window_size = 10
        messages = [HumanMessage(content="Test")]

        with patch("src.domains.agents.utils.message_windowing.get_windowed_messages") as mock_get:
            with patch("src.domains.agents.utils.message_windowing.logger"):
                mock_get.return_value = []
                get_planner_windowed_messages(messages)
                mock_get.assert_called_once_with(messages, window_size=10)

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_planner_window_size_integration(self, mock_settings, long_conversation):
        """Test planner windowing with actual messages."""
        mock_settings.planner_message_window_size = 5

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_planner_windowed_messages(long_conversation)

        # Should have system + 10 messages (5 turns)
        assert len(result) == 11


# ============================================================================
# Tests for get_response_windowed_messages
# ============================================================================


class TestGetResponseWindowedMessages:
    """Tests for get_response_windowed_messages()."""

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_uses_response_window_size_setting(self, mock_settings):
        """Test that response uses settings.response_message_window_size."""
        mock_settings.response_message_window_size = 20
        messages = [HumanMessage(content="Test")]

        with patch("src.domains.agents.utils.message_windowing.get_windowed_messages") as mock_get:
            with patch("src.domains.agents.utils.message_windowing.logger"):
                mock_get.return_value = []
                get_response_windowed_messages(messages)
                mock_get.assert_called_once_with(messages, window_size=20)

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_response_window_size_integration(self, mock_settings, long_conversation):
        """Test response windowing with actual messages."""
        mock_settings.response_message_window_size = 10

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_response_windowed_messages(long_conversation)

        # Should have system + 20 messages (10 turns)
        assert len(result) == 21


# ============================================================================
# Tests for get_orchestrator_windowed_messages
# ============================================================================


class TestGetOrchestratorWindowedMessages:
    """Tests for get_orchestrator_windowed_messages()."""

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_uses_orchestrator_window_size_setting(self, mock_settings):
        """Test that orchestrator uses settings.orchestrator_message_window_size."""
        mock_settings.orchestrator_message_window_size = 4
        messages = [HumanMessage(content="Test")]

        with patch("src.domains.agents.utils.message_windowing.get_windowed_messages") as mock_get:
            with patch("src.domains.agents.utils.message_windowing.logger"):
                mock_get.return_value = []
                get_orchestrator_windowed_messages(messages)
                mock_get.assert_called_once_with(messages, window_size=4)

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_orchestrator_window_size_integration(self, mock_settings, long_conversation):
        """Test orchestrator windowing with actual messages."""
        mock_settings.orchestrator_message_window_size = 2

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_orchestrator_windowed_messages(long_conversation)

        # Should have system + 4 messages (2 turns)
        assert len(result) == 5


# ============================================================================
# Tests for extract_last_user_message
# ============================================================================


class TestExtractLastUserMessage:
    """Tests for extract_last_user_message()."""

    def test_extracts_content_from_last_human_message(self):
        """Test extraction of last HumanMessage content."""
        messages = [
            HumanMessage(content="First question"),
            AIMessage(content="Answer"),
            HumanMessage(content="Second question"),
        ]
        result = extract_last_user_message(messages)
        assert result == "Second question"

    def test_returns_none_for_empty_list(self):
        """Test that empty list returns None."""
        result = extract_last_user_message([])
        assert result is None

    def test_returns_none_if_no_human_messages(self):
        """Test that None is returned if no HumanMessages exist."""
        messages = [
            SystemMessage(content="System"),
            AIMessage(content="Response"),
        ]
        result = extract_last_user_message(messages)
        assert result is None

    def test_ignores_ai_and_system_messages(self):
        """Test that AI and System messages are ignored."""
        messages = [
            HumanMessage(content="User question"),
            AIMessage(content="AI response"),
            SystemMessage(content="System note"),
        ]
        result = extract_last_user_message(messages)
        assert result == "User question"

    def test_handles_single_human_message(self):
        """Test with single HumanMessage."""
        messages = [HumanMessage(content="Only message")]
        result = extract_last_user_message(messages)
        assert result == "Only message"

    def test_handles_human_message_between_others(self):
        """Test finding HumanMessage when it's not last in list."""
        messages = [
            HumanMessage(content="User input"),
            AIMessage(content="Response 1"),
            AIMessage(content="Response 2"),
            ToolMessage(content="Tool result", tool_call_id="123"),
        ]
        result = extract_last_user_message(messages)
        assert result == "User input"

    def test_handles_multiple_human_messages(self):
        """Test with multiple HumanMessages returns the last one."""
        messages = [
            HumanMessage(content="First"),
            HumanMessage(content="Second"),
            HumanMessage(content="Third"),
        ]
        result = extract_last_user_message(messages)
        assert result == "Third"

    def test_handles_human_message_with_empty_content(self):
        """Test with HumanMessage that has empty content."""
        messages = [HumanMessage(content="")]
        result = extract_last_user_message(messages)
        assert result == ""

    def test_finds_human_message_after_many_ai_responses(self):
        """Test finding HumanMessage followed by many AI responses."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Query"),
            AIMessage(content="Part 1"),
            AIMessage(content="Part 2"),
            AIMessage(content="Part 3"),
            AIMessage(content="Part 4"),
        ]
        result = extract_last_user_message(messages)
        assert result == "Query"


# ============================================================================
# Integration tests
# ============================================================================


class TestIntegrationScenarios:
    """Integration tests for realistic message scenarios."""

    def test_complete_conversation_flow(self):
        """Test windowing a complete conversation with tool calls."""
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Find John's email"),
            AIMessage(content="", tool_calls=[{"id": "1", "name": "search_contacts", "args": {}}]),
            ToolMessage(content='{"email": "john@example.com"}', tool_call_id="1"),
            AIMessage(content="John's email is john@example.com"),
            HumanMessage(content="Send him a hello message"),
            AIMessage(content="", tool_calls=[{"id": "2", "name": "send_email", "args": {}}]),
            ToolMessage(content='{"status": "sent"}', tool_call_id="2"),
            AIMessage(content="Message sent successfully!"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=10)

        # Should have:
        # - 1 SystemMessage
        # - 2 HumanMessages
        # - 2 conversational AIMessages (without tool_calls)
        assert len(result) == 5

        # Verify types
        types = [type(m).__name__ for m in result]
        assert "SystemMessage" in types
        assert "HumanMessage" in types
        assert "AIMessage" in types
        assert "ToolMessage" not in types

    def test_multiple_system_messages_preserved(self):
        """Test that multiple system messages are all preserved."""
        messages = [
            SystemMessage(content="System 1"),
            SystemMessage(content="System 2"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=5)

        system_msgs = [m for m in result if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 2

    def test_immutability_of_input(self, long_conversation):
        """Test that input list is never modified."""
        original_length = len(long_conversation)
        original_contents = [m.content for m in long_conversation]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            get_windowed_messages(long_conversation, window_size=3)

        # Original list unchanged
        assert len(long_conversation) == original_length
        assert [m.content for m in long_conversation] == original_contents

    def test_windowing_then_extract_user_message(self, long_conversation):
        """Test combining windowing with extract_last_user_message."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            windowed = get_windowed_messages(long_conversation, window_size=3)

        user_msg = extract_last_user_message(windowed)
        # Last user message in the window should be Question 19
        assert user_msg == "Question 19"

    def test_different_window_sizes_same_messages(self, long_conversation):
        """Test that different window sizes produce different results."""
        with patch("src.domains.agents.utils.message_windowing.logger"):
            small = get_windowed_messages(long_conversation, window_size=2)
            medium = get_windowed_messages(long_conversation, window_size=5)
            large = get_windowed_messages(long_conversation, window_size=10)

        # Each should have different lengths
        assert len(small) < len(medium) < len(large)

        # All should have the system message
        for result in [small, medium, large]:
            assert isinstance(result[0], SystemMessage)

    @patch("src.domains.agents.utils.message_windowing.settings")
    def test_all_specialized_functions_use_correct_settings(self, mock_settings, long_conversation):
        """Test that all specialized windowing functions use correct settings."""
        mock_settings.router_message_window_size = 2
        mock_settings.planner_message_window_size = 4
        mock_settings.response_message_window_size = 6
        mock_settings.orchestrator_message_window_size = 1

        with patch("src.domains.agents.utils.message_windowing.logger"):
            router_result = get_router_windowed_messages(long_conversation)
            planner_result = get_planner_windowed_messages(long_conversation)
            response_result = get_response_windowed_messages(long_conversation)
            orchestrator_result = get_orchestrator_windowed_messages(long_conversation)

        # Each should produce different lengths based on window size
        # (1 system + 2*window_size messages)
        assert len(router_result) == 5  # 1 + 4
        assert len(planner_result) == 9  # 1 + 8
        assert len(response_result) == 13  # 1 + 12
        assert len(orchestrator_result) == 3  # 1 + 2

    def test_realistic_multi_tool_conversation(self):
        """Test windowing a realistic conversation with multiple tool invocations."""
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="What's the weather and my schedule?"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "weather_1", "name": "get_weather", "args": {}},
                    {"id": "calendar_1", "name": "get_calendar", "args": {}},
                ],
            ),
            ToolMessage(content='{"temp": 25}', tool_call_id="weather_1"),
            ToolMessage(content='{"events": []}', tool_call_id="calendar_1"),
            AIMessage(content="The weather is 25°C and you have no events today."),
            HumanMessage(content="Thanks!"),
            AIMessage(content="You're welcome!"),
        ]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=10)

        # Should have: 1 System + 2 Human + 2 AI (conversational only)
        assert len(result) == 5

        # Verify the conversational AI messages are kept
        ai_messages = [m for m in result if isinstance(m, AIMessage)]
        assert len(ai_messages) == 2
        assert "weather is 25°C" in ai_messages[0].content
        assert ai_messages[1].content == "You're welcome!"

    def test_empty_conversation_with_system_only(self):
        """Test windowing with only system messages (no conversation)."""
        messages = [SystemMessage(content="System prompt")]

        with patch("src.domains.agents.utils.message_windowing.logger"):
            result = get_windowed_messages(messages, window_size=5)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)

    def test_reduction_percentage_calculation(self, long_conversation):
        """Test that reduction percentage is calculated correctly."""
        with patch("src.domains.agents.utils.message_windowing.logger") as mock_logger:
            get_windowed_messages(long_conversation, window_size=5)

        # Find the info call
        info_call = mock_logger.info.call_args
        reduction_percent = info_call[1]["reduction_percent"]

        # 41 input messages (1 system + 40 conversational)
        # 11 output messages (1 system + 10 conversational)
        # Reduction = (1 - 11/41) * 100 ≈ 73%
        assert 70 <= reduction_percent <= 75
