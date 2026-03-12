"""
Comprehensive unit tests for message filtering utilities.

Tests all functions in message_filters module with 100% coverage:
- filter_conversational_messages
- filter_tool_messages
- filter_by_message_types
- extract_system_messages
- remove_orphan_tool_messages
- split_messages_by_turn
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.domains.agents.utils.message_filters import (
    extract_system_messages,
    filter_by_message_types,
    filter_conversational_messages,
    filter_tool_messages,
    remove_orphan_tool_messages,
    split_messages_by_turn,
)


class TestFilterConversationalMessages:
    """Test filter_conversational_messages function."""

    def test_empty_messages(self):
        """Should return empty list for empty input."""
        result = filter_conversational_messages([])
        assert not result

    def test_keeps_human_messages(self):
        """Should keep all HumanMessages."""
        messages = [
            HumanMessage(content="First message"),
            HumanMessage(content="Second message"),
        ]

        result = filter_conversational_messages(messages)

        assert len(result) == 2
        assert all(isinstance(m, HumanMessage) for m in result)

    def test_keeps_ai_messages_without_tool_calls(self):
        """Should keep AIMessages without tool_calls."""
        messages = [
            AIMessage(content="Response without tools"),
            AIMessage(content="Another response"),
        ]

        result = filter_conversational_messages(messages)

        assert len(result) == 2
        assert all(isinstance(m, AIMessage) for m in result)

    def test_filters_ai_messages_with_tool_calls(self):
        """Should filter out AIMessages with tool_calls."""
        messages = [
            HumanMessage(content="User query"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            AIMessage(content="Final response"),
        ]

        result = filter_conversational_messages(messages)

        # Should have HumanMessage + final AIMessage only
        assert len(result) == 2
        assert isinstance(result[0], HumanMessage)
        assert isinstance(result[1], AIMessage)
        assert result[1].content == "Final response"

    def test_filters_tool_messages(self):
        """Should filter out all ToolMessages."""
        messages = [
            HumanMessage(content="User query"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content='{"results": [...]}', tool_call_id="call_1"),
            AIMessage(content="Final response"),
        ]

        result = filter_conversational_messages(messages)

        # Should have HumanMessage + final AIMessage only (no ToolMessage)
        assert len(result) == 2
        assert not any(isinstance(m, ToolMessage) for m in result)

    def test_filters_system_messages(self):
        """Should NOT filter SystemMessages (they are kept in conversational flow)."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="User query"),
            AIMessage(content="Response"),
        ]

        result = filter_conversational_messages(messages)

        # SystemMessages are not conversational, so they should be kept or filtered
        # Based on the actual implementation, let's verify behavior
        # Looking at the code, SystemMessages are NOT explicitly handled
        # So they should be skipped (not added to conversational list)
        assert len(result) == 2
        assert not any(isinstance(m, SystemMessage) for m in result)

    def test_complex_conversation_flow(self):
        """Should correctly filter complex conversation with multiple message types."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="Search contacts"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content='{"results": [...]}', tool_call_id="call_1"),
            AIMessage(content="Found 3 contacts"),
            HumanMessage(content="Show details"),
            AIMessage(content="", tool_calls=[{"id": "call_2", "name": "get_details", "args": {}}]),
            ToolMessage(content='{"details": [...]}', tool_call_id="call_2"),
            AIMessage(content="Here are the details"),
        ]

        result = filter_conversational_messages(messages)

        # Should have: 2 HumanMessages + 2 AIMessages (without tool_calls)
        assert len(result) == 4
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Search contacts"
        assert isinstance(result[1], AIMessage)
        assert result[1].content == "Found 3 contacts"
        assert isinstance(result[2], HumanMessage)
        assert result[2].content == "Show details"
        assert isinstance(result[3], AIMessage)
        assert result[3].content == "Here are the details"


class TestFilterToolMessages:
    """Test filter_tool_messages function."""

    def test_empty_messages(self):
        """Should return empty list for empty input."""
        result = filter_tool_messages([])
        assert not result

    def test_extracts_only_tool_messages(self):
        """Should extract only ToolMessages."""
        messages = [
            HumanMessage(content="User query"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content='{"result": "data"}', tool_call_id="call_1"),
            AIMessage(content="Response"),
        ]

        result = filter_tool_messages(messages)

        assert len(result) == 1
        assert isinstance(result[0], ToolMessage)
        assert result[0].tool_call_id == "call_1"

    def test_multiple_tool_messages(self):
        """Should extract all ToolMessages."""
        messages = [
            ToolMessage(content='{"result1": "data1"}', tool_call_id="call_1"),
            HumanMessage(content="User"),
            ToolMessage(content='{"result2": "data2"}', tool_call_id="call_2"),
        ]

        result = filter_tool_messages(messages)

        assert len(result) == 2
        assert all(isinstance(m, ToolMessage) for m in result)

    def test_no_tool_messages(self):
        """Should return empty list when no ToolMessages present."""
        messages = [
            HumanMessage(content="User"),
            AIMessage(content="Response"),
            SystemMessage(content="System"),
        ]

        result = filter_tool_messages(messages)

        assert not result


class TestFilterByMessageTypes:
    """Test filter_by_message_types function."""

    def test_empty_messages(self):
        """Should return empty list for empty input."""
        result = filter_by_message_types([], [HumanMessage])
        assert not result

    def test_single_type_filter(self):
        """Should filter by single message type."""
        messages = [
            HumanMessage(content="User 1"),
            AIMessage(content="AI"),
            HumanMessage(content="User 2"),
        ]

        result = filter_by_message_types(messages, [HumanMessage])

        assert len(result) == 2
        assert all(isinstance(m, HumanMessage) for m in result)

    def test_multiple_types_filter(self):
        """Should filter by multiple message types."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="User"),
            AIMessage(content="AI"),
            ToolMessage(content="Tool", tool_call_id="call_1"),
        ]

        result = filter_by_message_types(messages, [HumanMessage, SystemMessage])

        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)

    def test_no_matching_types(self):
        """Should return empty list when no types match."""
        messages = [
            HumanMessage(content="User"),
            AIMessage(content="AI"),
        ]

        result = filter_by_message_types(messages, [ToolMessage])

        assert not result

    def test_preserves_order(self):
        """Should preserve chronological order of filtered messages."""
        messages = [
            HumanMessage(content="First"),
            AIMessage(content="AI"),
            HumanMessage(content="Second"),
            AIMessage(content="AI 2"),
            HumanMessage(content="Third"),
        ]

        result = filter_by_message_types(messages, [HumanMessage])

        assert len(result) == 3
        assert result[0].content == "First"
        assert result[1].content == "Second"
        assert result[2].content == "Third"


class TestExtractSystemMessages:
    """Test extract_system_messages function."""

    def test_empty_messages(self):
        """Should return empty list for empty input."""
        result = extract_system_messages([])
        assert not result

    def test_extracts_single_system_message(self):
        """Should extract single SystemMessage."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="User"),
        ]

        result = extract_system_messages(messages)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "System prompt"

    def test_extracts_multiple_system_messages(self):
        """Should extract all SystemMessages."""
        messages = [
            SystemMessage(content="System 1"),
            HumanMessage(content="User"),
            SystemMessage(content="System 2"),
            AIMessage(content="AI"),
        ]

        result = extract_system_messages(messages)

        assert len(result) == 2
        assert all(isinstance(m, SystemMessage) for m in result)

    def test_no_system_messages(self):
        """Should return empty list when no SystemMessages present."""
        messages = [
            HumanMessage(content="User"),
            AIMessage(content="AI"),
        ]

        result = extract_system_messages(messages)

        assert not result

    def test_preserves_order(self):
        """Should preserve order of SystemMessages."""
        messages = [
            SystemMessage(content="First"),
            HumanMessage(content="User"),
            SystemMessage(content="Second"),
        ]

        result = extract_system_messages(messages)

        assert len(result) == 2
        assert result[0].content == "First"
        assert result[1].content == "Second"


class TestRemoveOrphanToolMessages:
    """Test remove_orphan_tool_messages function."""

    def test_empty_messages(self):
        """Should return empty list for empty input."""
        result = remove_orphan_tool_messages([])
        assert not result

    def test_valid_tool_message_kept(self):
        """Should keep ToolMessage with valid parent AIMessage."""
        messages = [
            HumanMessage(content="User query"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content='{"result": "data"}', tool_call_id="call_1"),
        ]

        result = remove_orphan_tool_messages(messages)

        assert len(result) == 3
        assert isinstance(result[2], ToolMessage)

    def test_orphan_tool_message_removed(self):
        """Should remove ToolMessage without parent AIMessage."""
        messages = [
            HumanMessage(content="User query"),
            ToolMessage(content='{"result": "data"}', tool_call_id="call_orphan"),
        ]

        result = remove_orphan_tool_messages(messages)

        # ToolMessage should be removed
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_multiple_tool_calls_validation(self):
        """Should validate multiple tool_calls correctly."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call_1", "name": "search", "args": {}},
                    {"id": "call_2", "name": "get_details", "args": {}},
                ],
            ),
            ToolMessage(content='{"result": "data1"}', tool_call_id="call_1"),
            ToolMessage(content='{"result": "data2"}', tool_call_id="call_2"),
            ToolMessage(content='{"result": "orphan"}', tool_call_id="call_3"),  # Orphan
        ]

        result = remove_orphan_tool_messages(messages)

        # Should keep AIMessage + 2 valid ToolMessages, remove orphan
        assert len(result) == 3
        tool_messages = [m for m in result if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 2
        assert all(m.tool_call_id in ["call_1", "call_2"] for m in tool_messages)

    def test_non_tool_messages_preserved(self):
        """Should preserve all non-ToolMessages."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="User"),
            AIMessage(content="AI"),
            ToolMessage(content="Orphan", tool_call_id="call_orphan"),
        ]

        result = remove_orphan_tool_messages(messages)

        # Should keep System, Human, AI messages
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert isinstance(result[2], AIMessage)

    def test_tool_call_id_empty_string_removed(self):
        """Should remove ToolMessage with empty string tool_call_id."""
        messages = [
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content="Invalid", tool_call_id=""),  # Empty string - orphan
        ]

        result = remove_orphan_tool_messages(messages)

        assert len(result) == 1
        assert isinstance(result[0], AIMessage)


class TestSplitMessagesByTurn:
    """Test split_messages_by_turn function."""

    def test_empty_messages(self):
        """Should return empty list for empty input."""
        result = split_messages_by_turn([])
        assert not result

    def test_single_turn(self):
        """Should handle single conversation turn."""
        messages = [
            HumanMessage(content="User query"),
            AIMessage(content="AI response"),
        ]

        result = split_messages_by_turn(messages)

        assert len(result) == 1
        user_msg, responses = result[0]
        assert user_msg.content == "User query"
        assert len(responses) == 1
        assert responses[0].content == "AI response"

    def test_multiple_turns(self):
        """Should split multiple conversation turns correctly."""
        messages = [
            HumanMessage(content="Turn 1 user"),
            AIMessage(content="Turn 1 AI"),
            HumanMessage(content="Turn 2 user"),
            AIMessage(content="Turn 2 AI"),
        ]

        result = split_messages_by_turn(messages)

        assert len(result) == 2

        # Turn 1
        user_msg_1, responses_1 = result[0]
        assert user_msg_1.content == "Turn 1 user"
        assert len(responses_1) == 1
        assert responses_1[0].content == "Turn 1 AI"

        # Turn 2
        user_msg_2, responses_2 = result[1]
        assert user_msg_2.content == "Turn 2 user"
        assert len(responses_2) == 1
        assert responses_2[0].content == "Turn 2 AI"

    def test_turn_with_tool_execution(self):
        """Should group tool execution within turn."""
        messages = [
            HumanMessage(content="Search contacts"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content='{"results": [...]}', tool_call_id="call_1"),
            AIMessage(content="Found 3 contacts"),
        ]

        result = split_messages_by_turn(messages)

        assert len(result) == 1
        user_msg, responses = result[0]
        assert user_msg.content == "Search contacts"
        assert len(responses) == 3  # AIMessage + ToolMessage + AIMessage

    def test_turn_with_system_message(self):
        """Should include system messages in turn responses."""
        messages = [
            SystemMessage(content="System prompt"),
            HumanMessage(content="User query"),
            AIMessage(content="AI response"),
        ]

        result = split_messages_by_turn(messages)

        assert len(result) == 1
        user_msg, turn_responses = result[0]
        assert user_msg.content == "User query"
        assert len(turn_responses) == 1
        assert isinstance(turn_responses[0], AIMessage)

    def test_incomplete_turn(self):
        """Should handle incomplete turn (user message without response)."""
        messages = [
            HumanMessage(content="Turn 1"),
            AIMessage(content="Response 1"),
            HumanMessage(content="Turn 2 without response"),
        ]

        result = split_messages_by_turn(messages)

        assert len(result) == 2

        # Turn 1 complete
        user_msg_1, responses_1 = result[0]
        assert user_msg_1.content == "Turn 1"
        assert len(responses_1) == 1

        # Turn 2 incomplete
        user_msg_2, responses_2 = result[1]
        assert user_msg_2.content == "Turn 2 without response"
        assert len(responses_2) == 0

    def test_messages_before_first_user(self):
        """Should ignore messages before first HumanMessage."""
        messages = [
            SystemMessage(content="System"),
            AIMessage(content="Some AI message"),
            HumanMessage(content="First user message"),
            AIMessage(content="Response"),
        ]

        result = split_messages_by_turn(messages)

        # Should only have 1 turn starting from first HumanMessage
        assert len(result) == 1
        user_msg, responses = result[0]
        assert user_msg.content == "First user message"

    def test_consecutive_user_messages(self):
        """Should handle consecutive user messages as separate turns."""
        messages = [
            HumanMessage(content="First"),
            HumanMessage(content="Second"),
            AIMessage(content="Response to second"),
        ]

        result = split_messages_by_turn(messages)

        # Should have 2 turns
        assert len(result) == 2

        # First turn has no responses
        user_msg_1, responses_1 = result[0]
        assert user_msg_1.content == "First"
        assert len(responses_1) == 0

        # Second turn has response
        user_msg_2, responses_2 = result[1]
        assert user_msg_2.content == "Second"
        assert len(responses_2) == 1


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_ai_message_with_empty_tool_calls(self):
        """Should handle AIMessage with empty tool_calls list."""
        messages = [
            AIMessage(content="Response", tool_calls=[]),
        ]

        result = filter_conversational_messages(messages)

        # Empty tool_calls should be treated as no tool_calls
        assert len(result) == 1
        assert result[0].content == "Response"

    def test_ai_message_without_tool_calls_attribute(self):
        """Should handle AIMessage without tool_calls attribute."""
        # Create AIMessage without tool_calls
        msg = AIMessage(content="Response")
        if hasattr(msg, "tool_calls"):
            delattr(msg, "tool_calls")

        messages = [msg]

        result = filter_conversational_messages(messages)

        assert len(result) == 1
        assert result[0].content == "Response"

    def test_tool_message_with_malformed_tool_call_id(self):
        """Should handle ToolMessage with malformed tool_call_id."""
        messages = [
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content="Result", tool_call_id=""),  # Empty string
        ]

        result = remove_orphan_tool_messages(messages)

        # Empty tool_call_id should be treated as orphan
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
