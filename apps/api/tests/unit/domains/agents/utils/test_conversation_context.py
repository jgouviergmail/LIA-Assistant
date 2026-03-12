"""
Unit tests for conversation context utilities.

Tests for conversation history injection and formatting
for LangGraph orchestration nodes.
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.domains.agents.utils.conversation_context import (
    format_conversation_history,
    get_conversation_summary_for_logging,
    inject_conversation_history,
)

# ============================================================================
# Tests for format_conversation_history
# ============================================================================


class TestFormatConversationHistoryBasic:
    """Tests for basic conversation formatting."""

    def test_format_empty_messages(self):
        """Test formatting with empty message list."""
        result = format_conversation_history([])
        assert result == "(aucun historique)"

    def test_format_single_human_message(self):
        """Test formatting a single HumanMessage."""
        messages = [HumanMessage(content="Bonjour")]
        result = format_conversation_history(messages)
        assert result == "[USER]: Bonjour"

    def test_format_single_ai_message(self):
        """Test formatting a single AIMessage."""
        messages = [AIMessage(content="Salut!")]
        result = format_conversation_history(messages)
        assert result == "[ASSISTANT]: Salut!"

    def test_format_alternating_messages(self):
        """Test formatting alternating Human/AI messages."""
        messages = [
            HumanMessage(content="Bonjour"),
            AIMessage(content="Salut! Comment puis-je vous aider?"),
            HumanMessage(content="Recherche mes contacts"),
        ]
        result = format_conversation_history(messages)

        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0] == "[USER]: Bonjour"
        assert lines[1] == "[ASSISTANT]: Salut! Comment puis-je vous aider?"
        assert lines[2] == "[USER]: Recherche mes contacts"


class TestFormatConversationHistoryTruncation:
    """Tests for content truncation in formatting."""

    def test_truncates_long_content(self):
        """Test that long content is truncated."""
        long_content = "a" * 1000
        messages = [HumanMessage(content=long_content)]
        result = format_conversation_history(messages, max_content_length=100)

        assert len(result) < len(long_content) + 20  # [USER]: prefix + ...
        assert result.endswith("...")

    def test_truncates_at_specified_length(self):
        """Test truncation at exact max_content_length."""
        content = "Hello World"
        messages = [HumanMessage(content=content)]
        result = format_conversation_history(messages, max_content_length=5)

        assert "[USER]: Hello..." in result

    def test_no_truncation_for_short_content(self):
        """Test no truncation when content is short."""
        content = "Short"
        messages = [HumanMessage(content=content)]
        result = format_conversation_history(messages, max_content_length=500)

        assert result == "[USER]: Short"
        assert "..." not in result


class TestFormatConversationHistorySpecialCases:
    """Tests for special cases in formatting."""

    def test_skips_system_messages(self):
        """Test that SystemMessage is skipped."""
        messages = [
            SystemMessage(content="System instructions"),
            HumanMessage(content="User message"),
        ]
        result = format_conversation_history(messages)

        assert "System" not in result
        assert "[USER]: User message" in result

    def test_skips_empty_content_messages(self):
        """Test that empty content messages are skipped."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content=""),
            HumanMessage(content="World"),
        ]
        result = format_conversation_history(messages)

        lines = result.split("\n")
        assert len(lines) == 2
        assert "[USER]: Hello" in result
        assert "[USER]: World" in result

    def test_skips_whitespace_only_content(self):
        """Test that whitespace-only content is skipped."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="   \n\t  "),
            HumanMessage(content="World"),
        ]
        result = format_conversation_history(messages)

        lines = result.split("\n")
        assert len(lines) == 2

    def test_returns_no_history_when_all_empty(self):
        """Test returns no history when all messages are empty."""
        messages = [
            AIMessage(content=""),
            AIMessage(content="   "),
        ]
        result = format_conversation_history(messages)
        assert result == "(aucun historique)"

    def test_handles_unknown_message_type(self):
        """Test handling of unknown message types."""

        # Create a custom message type
        class CustomMessage(BaseMessage):
            type: str = "custom"

        messages = [CustomMessage(content="Custom content")]
        result = format_conversation_history(messages)

        assert "[CUSTOMMESSAGE]: Custom content" in result


class TestFormatConversationHistoryEdgeCases:
    """Tests for edge cases in formatting."""

    def test_message_without_content_attribute(self):
        """Test handling message without content attribute."""

        # This is an edge case - normally all messages have content
        class NoContentMessage(BaseMessage):
            type: str = "no_content"

        msg = NoContentMessage(content="")
        messages = [msg]
        result = format_conversation_history(messages)

        assert result == "(aucun historique)"

    def test_preserves_message_order(self):
        """Test that message order is preserved."""
        messages = [
            HumanMessage(content="First"),
            AIMessage(content="Second"),
            HumanMessage(content="Third"),
            AIMessage(content="Fourth"),
        ]
        result = format_conversation_history(messages)

        lines = result.split("\n")
        assert "First" in lines[0]
        assert "Second" in lines[1]
        assert "Third" in lines[2]
        assert "Fourth" in lines[3]


# ============================================================================
# Tests for inject_conversation_history
# ============================================================================


class TestInjectConversationHistoryBasic:
    """Tests for basic conversation injection."""

    def test_inject_simple_history(self):
        """Test injecting simple conversation history."""
        prompt = [
            SystemMessage(content="You are an assistant."),
            HumanMessage(content="Generate a plan."),
        ]
        history = [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello!"),
        ]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = history
            with patch("src.domains.agents.utils.conversation_context.logger"):
                result = inject_conversation_history(prompt, history, node_name="test")

        assert len(result) == 4  # System + Hi + Hello + Generate
        assert isinstance(result[0], SystemMessage)
        assert result[1].content == "Hi"
        assert result[2].content == "Hello!"
        assert result[-1].content == "Generate a plan."

    def test_inject_empty_history(self):
        """Test injection with empty conversation history."""
        prompt = [
            SystemMessage(content="System"),
            HumanMessage(content="User"),
        ]

        with patch("src.domains.agents.utils.conversation_context.logger"):
            result = inject_conversation_history(prompt, [], node_name="test")

        # Should return original prompt unchanged
        assert result == prompt

    def test_inject_preserves_original_order(self):
        """Test that injection preserves conversation order."""
        prompt = [
            SystemMessage(content="System"),
            HumanMessage(content="Final query"),
        ]
        history = [
            HumanMessage(content="Message 1"),
            AIMessage(content="Response 1"),
            HumanMessage(content="Message 2"),
            AIMessage(content="Response 2"),
        ]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = history
            with patch("src.domains.agents.utils.conversation_context.logger"):
                result = inject_conversation_history(prompt, history)

        # Check order: System, history..., Final
        assert result[0].content == "System"
        assert result[1].content == "Message 1"
        assert result[2].content == "Response 1"
        assert result[3].content == "Message 2"
        assert result[4].content == "Response 2"
        assert result[5].content == "Final query"


class TestInjectConversationHistoryValidation:
    """Tests for validation in conversation injection."""

    def test_returns_original_when_prompt_empty(self):
        """Test returns original when prompt is empty."""
        prompt: list[BaseMessage] = []
        history = [HumanMessage(content="Hi")]

        with patch("src.domains.agents.utils.conversation_context.logger") as mock_logger:
            result = inject_conversation_history(prompt, history, node_name="test")

        assert result == prompt
        mock_logger.warning.assert_called()

    def test_returns_original_when_prompt_too_short(self):
        """Test returns original when prompt has only one message."""
        prompt = [SystemMessage(content="Only system")]
        history = [HumanMessage(content="Hi")]

        with patch("src.domains.agents.utils.conversation_context.logger") as mock_logger:
            result = inject_conversation_history(prompt, history, node_name="test")

        assert result == prompt
        mock_logger.warning.assert_called()

    def test_returns_original_when_first_not_system(self):
        """Test returns original when first message is not SystemMessage."""
        prompt = [
            HumanMessage(content="Not system"),
            HumanMessage(content="User query"),
        ]
        history = [HumanMessage(content="Hi")]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = history
            with patch("src.domains.agents.utils.conversation_context.logger") as mock_logger:
                result = inject_conversation_history(prompt, history, node_name="test")

        assert result == prompt
        mock_logger.warning.assert_called()

    def test_returns_original_when_last_not_human(self):
        """Test returns original when last message is not HumanMessage."""
        prompt = [
            SystemMessage(content="System"),
            AIMessage(content="Not human"),
        ]
        history = [HumanMessage(content="Hi")]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = history
            with patch("src.domains.agents.utils.conversation_context.logger") as mock_logger:
                result = inject_conversation_history(prompt, history, node_name="test")

        assert result == prompt
        mock_logger.warning.assert_called()


class TestInjectConversationHistoryFiltering:
    """Tests for filtering during injection."""

    def test_filters_conversation_messages(self):
        """Test that conversation messages are filtered."""
        prompt = [
            SystemMessage(content="System"),
            HumanMessage(content="Query"),
        ]
        history = [
            HumanMessage(content="User message"),
            ToolMessage(content="Tool result", tool_call_id="tc1"),
            AIMessage(content="AI response"),
        ]

        # Mock filter to return only conversational messages
        filtered = [HumanMessage(content="User message"), AIMessage(content="AI response")]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = filtered
            with patch("src.domains.agents.utils.conversation_context.logger"):
                result = inject_conversation_history(prompt, history, node_name="test")

        # Should have System + filtered + Query
        assert len(result) == 4

    def test_returns_original_when_all_filtered_out(self):
        """Test returns original when filtering removes all messages."""
        prompt = [
            SystemMessage(content="System"),
            HumanMessage(content="Query"),
        ]
        history = [
            ToolMessage(content="Tool only", tool_call_id="tc1"),
        ]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = []  # All filtered out
            with patch("src.domains.agents.utils.conversation_context.logger"):
                result = inject_conversation_history(prompt, history, node_name="test")

        assert result == prompt


class TestInjectConversationHistoryLogging:
    """Tests for logging in conversation injection."""

    def test_logs_warning_for_invalid_prompt(self):
        """Test warning is logged for invalid prompt."""
        with patch("src.domains.agents.utils.conversation_context.logger") as mock_logger:
            inject_conversation_history([], [HumanMessage("Hi")], run_id="123", node_name="planner")

        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args
        assert "planner" in call_args[0][0]
        assert call_args[1]["run_id"] == "123"

    def test_logs_debug_for_no_conversation(self):
        """Test debug is logged when no conversation to inject."""
        prompt = [
            SystemMessage(content="System"),
            HumanMessage(content="Query"),
        ]

        with patch("src.domains.agents.utils.conversation_context.logger") as mock_logger:
            inject_conversation_history(prompt, [], run_id="456", node_name="router")

        mock_logger.debug.assert_called()

    def test_logs_info_on_successful_injection(self):
        """Test info is logged on successful injection."""
        prompt = [
            SystemMessage(content="System"),
            HumanMessage(content="Query"),
        ]
        history = [HumanMessage(content="Hi")]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = history
            with patch("src.domains.agents.utils.conversation_context.logger") as mock_logger:
                inject_conversation_history(prompt, history, run_id="789", node_name="response")

        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args
        assert "response" in call_args[0][0]
        assert "history_count" in call_args[1]


class TestInjectConversationHistoryNodeNames:
    """Tests for different node names in injection."""

    @pytest.mark.parametrize("node_name", ["router", "planner", "response", "semantic_validator"])
    def test_various_node_names(self, node_name):
        """Test injection with various node names."""
        prompt = [
            SystemMessage(content="System"),
            HumanMessage(content="Query"),
        ]
        history = [HumanMessage(content="Hi")]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = history
            with patch("src.domains.agents.utils.conversation_context.logger") as mock_logger:
                inject_conversation_history(prompt, history, node_name=node_name)

        # Check that node_name appears in log event
        call_args = mock_logger.info.call_args
        assert node_name in call_args[0][0]


# ============================================================================
# Tests for get_conversation_summary_for_logging
# ============================================================================


class TestGetConversationSummaryBasic:
    """Tests for basic conversation summary functionality."""

    def test_empty_messages_returns_empty_list(self):
        """Test that empty message list returns empty summary."""
        result = get_conversation_summary_for_logging([])
        assert result == []

    def test_summarizes_single_message(self):
        """Test summary of a single message."""
        messages = [HumanMessage(content="Hello World")]
        result = get_conversation_summary_for_logging(messages)

        assert len(result) == 1
        assert result[0]["type"] == "HumanMessage"
        assert result[0]["preview"] == "Hello World"

    def test_summarizes_multiple_messages(self):
        """Test summary of multiple messages."""
        messages = [
            HumanMessage(content="First"),
            AIMessage(content="Second"),
            SystemMessage(content="Third"),
        ]
        result = get_conversation_summary_for_logging(messages)

        assert len(result) == 3
        assert result[0]["type"] == "HumanMessage"
        assert result[1]["type"] == "AIMessage"
        assert result[2]["type"] == "SystemMessage"


class TestGetConversationSummaryTruncation:
    """Tests for preview truncation in summary."""

    def test_truncates_long_preview(self):
        """Test that long content is truncated in preview."""
        long_content = "a" * 200
        messages = [HumanMessage(content=long_content)]
        result = get_conversation_summary_for_logging(messages, max_preview_length=50)

        assert len(result[0]["preview"]) == 53  # 50 + "..."
        assert result[0]["preview"].endswith("...")

    def test_no_truncation_for_short_content(self):
        """Test no truncation for short content."""
        messages = [HumanMessage(content="Short")]
        result = get_conversation_summary_for_logging(messages, max_preview_length=100)

        assert result[0]["preview"] == "Short"
        assert "..." not in result[0]["preview"]

    def test_custom_preview_length(self):
        """Test custom max_preview_length parameter."""
        content = "Hello World Testing"
        messages = [HumanMessage(content=content)]
        result = get_conversation_summary_for_logging(messages, max_preview_length=5)

        assert result[0]["preview"] == "Hello..."


class TestGetConversationSummaryMessageTypes:
    """Tests for different message types in summary."""

    def test_includes_tool_message_type(self):
        """Test that ToolMessage type is captured."""
        messages = [ToolMessage(content="Tool result", tool_call_id="tc1")]
        result = get_conversation_summary_for_logging(messages)

        assert result[0]["type"] == "ToolMessage"

    def test_includes_all_common_types(self):
        """Test that all common message types are captured."""
        messages = [
            HumanMessage(content="User"),
            AIMessage(content="AI"),
            SystemMessage(content="System"),
            ToolMessage(content="Tool", tool_call_id="tc1"),
        ]
        result = get_conversation_summary_for_logging(messages)

        types = [r["type"] for r in result]
        assert "HumanMessage" in types
        assert "AIMessage" in types
        assert "SystemMessage" in types
        assert "ToolMessage" in types


class TestGetConversationSummaryEdgeCases:
    """Tests for edge cases in conversation summary."""

    def test_handles_empty_content(self):
        """Test handling of empty content."""
        messages = [HumanMessage(content="")]
        result = get_conversation_summary_for_logging(messages)

        assert result[0]["preview"] == ""

    def test_preserves_message_order(self):
        """Test that message order is preserved in summary."""
        messages = [
            HumanMessage(content="First"),
            AIMessage(content="Second"),
            HumanMessage(content="Third"),
        ]
        result = get_conversation_summary_for_logging(messages)

        assert result[0]["preview"] == "First"
        assert result[1]["preview"] == "Second"
        assert result[2]["preview"] == "Third"

    def test_handles_content_with_newlines(self):
        """Test handling content with newlines."""
        messages = [HumanMessage(content="Line 1\nLine 2\nLine 3")]
        result = get_conversation_summary_for_logging(messages)

        assert "Line 1" in result[0]["preview"]
        assert "\n" in result[0]["preview"]


# ============================================================================
# Tests for module interface
# ============================================================================


class TestModuleInterface:
    """Tests for module exports and interface."""

    def test_all_functions_exported(self):
        """Test that __all__ contains all public functions."""
        from src.domains.agents.utils import conversation_context

        expected_exports = [
            "format_conversation_history",
            "get_conversation_summary_for_logging",
            "inject_conversation_history",
        ]

        for export in expected_exports:
            assert export in conversation_context.__all__
            assert hasattr(conversation_context, export)

    def test_functions_are_callable(self):
        """Test that all exported functions are callable."""
        from src.domains.agents.utils import conversation_context

        for name in conversation_context.__all__:
            func = getattr(conversation_context, name)
            assert callable(func)


# ============================================================================
# Integration-style tests
# ============================================================================


class TestConversationContextIntegration:
    """Integration tests combining multiple functions."""

    def test_format_then_summarize_flow(self):
        """Test formatting followed by summarizing."""
        messages = [
            HumanMessage(content="What's the weather?"),
            AIMessage(content="It's sunny today!"),
        ]

        # Format for prompt
        formatted = format_conversation_history(messages)
        assert "[USER]:" in formatted
        assert "[ASSISTANT]:" in formatted

        # Summarize for logging
        summary = get_conversation_summary_for_logging(messages)
        assert len(summary) == 2

    def test_inject_with_varied_history_lengths(self):
        """Test injection with different history lengths."""
        prompt = [
            SystemMessage(content="System"),
            HumanMessage(content="Query"),
        ]

        for length in [1, 5, 10, 20]:
            history = [HumanMessage(content=f"Message {i}") for i in range(length)]

            with patch(
                "src.domains.agents.utils.conversation_context.filter_for_llm_context"
            ) as mock_filter:
                mock_filter.return_value = history
                with patch("src.domains.agents.utils.conversation_context.logger"):
                    result = inject_conversation_history(prompt, history)

            # Should have System + history + Query
            assert len(result) == length + 2

    def test_realistic_router_scenario(self):
        """Test realistic router node scenario."""
        # Router prompt
        prompt = [
            SystemMessage(content="You are a router. Decide: CHAT or PLANNER."),
            HumanMessage(content="CURRENT QUERY: Find my contacts"),
        ]

        # Conversation history (windowed to 5 turns)
        history = [
            HumanMessage(content="Bonjour"),
            AIMessage(content="Bonjour! Comment puis-je vous aider?"),
            HumanMessage(content="Quels sont mes rendez-vous demain?"),
            AIMessage(content="Vous avez 2 rendez-vous demain: ..."),
        ]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = history
            with patch("src.domains.agents.utils.conversation_context.logger"):
                result = inject_conversation_history(
                    prompt, history, run_id="run_abc", node_name="router"
                )

        # Verify structure
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[-1], HumanMessage)
        assert "Find my contacts" in result[-1].content
        assert len(result) == 6  # System + 4 history + final human

    def test_realistic_planner_scenario(self):
        """Test realistic planner node scenario."""
        prompt = [
            SystemMessage(content="You are a planner. Generate an ExecutionPlan."),
            HumanMessage(content="Plan request: Send email to John about meeting"),
        ]

        history = [
            HumanMessage(content="Who is John?"),
            AIMessage(content="John Smith is your contact."),
        ]

        with patch(
            "src.domains.agents.utils.conversation_context.filter_for_llm_context"
        ) as mock_filter:
            mock_filter.return_value = history
            with patch("src.domains.agents.utils.conversation_context.logger"):
                result = inject_conversation_history(
                    prompt, history, run_id="plan_123", node_name="planner"
                )

        assert len(result) == 4
        assert "planner" in str(result)  # From logging
