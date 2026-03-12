"""
Unit tests for message filtering utilities.

Tests for filtering and processing message lists
in different contexts (response generation, agent input, tool context, etc.).
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.domains.agents.utils.message_filters import (
    _extract_text_before_html,
    extract_system_messages,
    filter_by_message_types,
    filter_conversational_messages,
    filter_for_llm_context,
    filter_tool_messages,
    remove_orphan_tool_messages,
    split_messages_by_turn,
)

# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def simple_human_message():
    """Simple user message."""
    return HumanMessage(content="Bonjour")


@pytest.fixture
def simple_ai_message():
    """Simple AI message without tool calls."""
    return AIMessage(content="Bonjour! Comment puis-je vous aider?")


@pytest.fixture
def ai_message_with_tool_calls():
    """AI message with tool calls."""
    return AIMessage(
        content="",
        tool_calls=[{"id": "call_123", "name": "search_contacts", "args": {"query": "jean"}}],
    )


@pytest.fixture
def tool_message():
    """Tool result message."""
    return ToolMessage(
        content='{"results": [{"name": "Jean Dupont"}]}',
        tool_call_id="call_123",
    )


@pytest.fixture
def orphan_tool_message():
    """Tool message without corresponding AI message."""
    return ToolMessage(
        content='{"results": []}',
        tool_call_id="call_orphan_999",
    )


@pytest.fixture
def system_message():
    """System message."""
    return SystemMessage(content="You are a helpful assistant.")


@pytest.fixture
def internal_system_message():
    """Internal system marker message."""
    return SystemMessage(content="__PLAN_REJECTED__")


@pytest.fixture
def ai_message_with_html():
    """AI message containing HTML card with single quotes."""
    return AIMessage(
        content="Voici les contacts!\n\n<div class='lia-card'><p>Jean Dupont</p></div>"
    )


@pytest.fixture
def ai_message_html_double_quotes():
    """AI message with HTML using double quotes for class."""
    return AIMessage(content='<div class="lia-card"><p>Content</p></div>')


@pytest.fixture
def full_conversation():
    """Complete conversation with various message types."""
    return [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Recherche les contacts de jean"),
        AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "search_contacts", "args": {}}],
        ),
        ToolMessage(content='{"results": ["Jean Dupont"]}', tool_call_id="call_1"),
        AIMessage(content="J'ai trouvé Jean Dupont."),
        HumanMessage(content="Envoie-lui un email"),
        AIMessage(
            content="",
            tool_calls=[{"id": "call_2", "name": "send_email", "args": {}}],
        ),
        ToolMessage(content='{"status": "sent"}', tool_call_id="call_2"),
        AIMessage(content="Email envoyé!"),
    ]


# ============================================================================
# Tests for _extract_text_before_html
# ============================================================================


class TestExtractTextBeforeHtml:
    """Tests for _extract_text_before_html() helper."""

    def test_extracts_text_before_html_div(self):
        """Test extraction of text before div tag."""
        content = "Here is the result!\n\n<div class='lia-card'>Content</div>"
        result = _extract_text_before_html(content)
        assert result == "Here is the result!"

    def test_extracts_text_before_any_html_tag(self):
        """Test extraction before any HTML tag."""
        content = "Weather report:\n<span>Data</span>"
        result = _extract_text_before_html(content)
        assert result == "Weather report:"

    def test_returns_empty_if_starts_with_html(self):
        """Test returns empty string if content starts with HTML."""
        content = "<div class='lia-card'>Content</div>"
        result = _extract_text_before_html(content)
        assert result == ""

    def test_returns_full_content_if_no_html(self):
        """Test returns full content if no HTML present."""
        content = "Just plain text response"
        result = _extract_text_before_html(content)
        assert result == "Just plain text response"

    def test_strips_whitespace(self):
        """Test that result is stripped of whitespace."""
        content = "  Text with spaces  \n\n<div>HTML</div>"
        result = _extract_text_before_html(content)
        assert result == "Text with spaces"

    def test_handles_multiple_html_tags(self):
        """Test extraction stops at first HTML tag."""
        content = "Intro\n<div>First</div>\n<span>Second</span>"
        result = _extract_text_before_html(content)
        assert result == "Intro"

    def test_handles_empty_string(self):
        """Test handling empty string input."""
        result = _extract_text_before_html("")
        assert result == ""

    def test_handles_only_whitespace(self):
        """Test handling whitespace-only string."""
        result = _extract_text_before_html("   \n\t  ")
        assert result == ""

    def test_handles_uppercase_tags(self):
        """Test handling uppercase HTML tags."""
        content = "Text before <DIV>content</DIV>"
        result = _extract_text_before_html(content)
        assert result == "Text before"

    def test_handles_self_closing_tags(self):
        """Test handling content before self-closing tags."""
        content = "Image follows <img src='test.jpg'/>"
        result = _extract_text_before_html(content)
        assert result == "Image follows"

    def test_multiline_text_before_html(self):
        """Test extracting multiline text before HTML."""
        content = "Ligne 1\nLigne 2\n\n<div>html</div>"
        result = _extract_text_before_html(content)
        assert result == "Ligne 1\nLigne 2"

    def test_handles_p_tag(self):
        """Test extraction before p tag."""
        content = "Message important\n<p>paragraph</p>"
        result = _extract_text_before_html(content)
        assert result == "Message important"

    def test_handles_special_characters_in_text(self):
        """Test handling special characters in text before HTML."""
        content = "Résumé: éléments clés <div>html</div>"
        result = _extract_text_before_html(content)
        assert result == "Résumé: éléments clés"


# ============================================================================
# Tests for filter_conversational_messages
# ============================================================================


class TestFilterConversationalMessages:
    """Tests for filter_conversational_messages()."""

    def test_keeps_human_messages(self):
        """Test that HumanMessages are kept."""
        messages = [
            HumanMessage(content="Hello"),
            HumanMessage(content="How are you?"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        assert len(result) == 2
        assert all(isinstance(m, HumanMessage) for m in result)

    def test_keeps_ai_messages_without_tool_calls(self):
        """Test that AIMessages without tool_calls are kept."""
        messages = [
            AIMessage(content="Hi there!"),
            AIMessage(content="I'm doing well."),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        assert len(result) == 2

    def test_filters_out_ai_messages_with_tool_calls(self):
        """Test that AIMessages with tool_calls are filtered out."""
        messages = [
            AIMessage(content="", tool_calls=[{"id": "1", "name": "search", "args": {}}]),
            AIMessage(content="Result"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        assert len(result) == 1
        assert result[0].content == "Result"

    def test_filters_out_tool_messages(self):
        """Test that ToolMessages are filtered out."""
        messages = [
            HumanMessage(content="Search"),
            ToolMessage(content='{"data": "result"}', tool_call_id="1"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_filters_out_internal_system_markers(self):
        """Test that SystemMessages starting with __ are filtered."""
        messages = [
            HumanMessage(content="Test"),
            SystemMessage(content="__PLAN_REJECTED__"),
            SystemMessage(content="__INTERNAL_MARKER__"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        assert len(result) == 1

    def test_empty_list_returns_empty(self):
        """Test that empty input returns empty output."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages([])

        assert result == []

    def test_ai_message_with_empty_tool_calls(self):
        """Test that AIMessage with empty tool_calls list is kept."""
        messages = [AIMessage(content="Response", tool_calls=[])]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        assert len(result) == 1

    def test_does_not_keep_regular_system_messages(self, system_message):
        """Test that regular SystemMessages are not kept."""
        messages = [system_message]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        # SystemMessage is not kept - only HumanMessage and AIMessage without tool_calls
        assert len(result) == 0

    def test_full_conversation_filtering(self, full_conversation):
        """Test filtering full conversation keeps only conversational messages."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(full_conversation)

        # Should keep: 2 HumanMessages + 2 AIMessages without tool_calls = 4
        assert len(result) == 4
        assert all(isinstance(m, HumanMessage | AIMessage) for m in result)

    def test_logs_filtering_stats(self, full_conversation):
        """Test that filtering statistics are logged."""
        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            filter_conversational_messages(full_conversation)

        mock_logger.debug.assert_called_once()
        call_kwargs = mock_logger.debug.call_args[1]
        assert "original_count" in call_kwargs
        assert "filtered_count" in call_kwargs
        assert "removed" in call_kwargs

    def test_preserves_message_order(self):
        """Test that message order is preserved."""
        messages = [
            HumanMessage(content="Message 1"),
            AIMessage(content="Response 1"),
            HumanMessage(content="Message 2"),
            AIMessage(content="Response 2"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        assert result[0].content == "Message 1"
        assert result[1].content == "Response 1"
        assert result[2].content == "Message 2"
        assert result[3].content == "Response 2"

    def test_ai_message_without_tool_calls_attribute(self):
        """Test AIMessage without tool_calls attribute is kept."""
        ai_msg = AIMessage(content="Simple response")
        messages = [ai_msg]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_conversational_messages(messages)

        assert len(result) == 1


# ============================================================================
# Tests for filter_tool_messages
# ============================================================================


class TestFilterToolMessages:
    """Tests for filter_tool_messages()."""

    def test_keeps_only_tool_messages(self):
        """Test that only ToolMessages are kept."""
        messages = [
            HumanMessage(content="Search"),
            AIMessage(content="", tool_calls=[{"id": "1", "name": "search", "args": {}}]),
            ToolMessage(content='{"data": "result1"}', tool_call_id="1"),
            ToolMessage(content='{"data": "result2"}', tool_call_id="2"),
            AIMessage(content="Done"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_tool_messages(messages)

        assert len(result) == 2
        assert all(isinstance(m, ToolMessage) for m in result)

    def test_returns_empty_if_no_tool_messages(self):
        """Test that empty list returned if no ToolMessages."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_tool_messages(messages)

        assert result == []

    def test_empty_list_returns_empty(self):
        """Test that empty input returns empty output."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_tool_messages([])

        assert result == []

    def test_logs_filtering_stats(self):
        """Test that filtering statistics are logged."""
        messages = [
            ToolMessage(content="{}", tool_call_id="call_1"),
            HumanMessage(content="Test"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            filter_tool_messages(messages)

        mock_logger.debug.assert_called_once()
        call_kwargs = mock_logger.debug.call_args[1]
        assert call_kwargs["total_messages"] == 2
        assert call_kwargs["tool_messages_count"] == 1

    def test_returns_multiple_tool_messages(self):
        """Test returning multiple ToolMessages preserves order."""
        messages = [
            ToolMessage(content='{"a": 1}', tool_call_id="call_1"),
            HumanMessage(content="Question"),
            ToolMessage(content='{"b": 2}', tool_call_id="call_2"),
            ToolMessage(content='{"c": 3}', tool_call_id="call_3"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_tool_messages(messages)

        assert len(result) == 3
        assert result[0].tool_call_id == "call_1"
        assert result[1].tool_call_id == "call_2"
        assert result[2].tool_call_id == "call_3"


# ============================================================================
# Tests for filter_by_message_types
# ============================================================================


class TestFilterByMessageTypes:
    """Tests for filter_by_message_types()."""

    def test_filters_by_single_type(self):
        """Test filtering by single message type."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
            SystemMessage(content="System"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_by_message_types(messages, [HumanMessage])

        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_filters_by_multiple_types(self):
        """Test filtering by multiple message types."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
            SystemMessage(content="System"),
            ToolMessage(content="Tool", tool_call_id="1"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_by_message_types(messages, [HumanMessage, SystemMessage])

        assert len(result) == 2

    def test_returns_empty_if_no_matches(self):
        """Test returns empty if no matching types."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_by_message_types(messages, [ToolMessage])

        assert result == []

    def test_preserves_order(self):
        """Test that message order is preserved."""
        messages = [
            HumanMessage(content="First"),
            AIMessage(content="Second"),
            HumanMessage(content="Third"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_by_message_types(messages, [HumanMessage])

        assert result[0].content == "First"
        assert result[1].content == "Third"

    def test_empty_types_list(self, full_conversation):
        """Test filtering with empty types list returns empty."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_by_message_types(full_conversation, [])

        assert result == []

    def test_empty_messages_list(self):
        """Test filtering empty messages list returns empty."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_by_message_types([], [HumanMessage, AIMessage])

        assert result == []

    def test_logs_type_names(self, full_conversation):
        """Test that type names are logged."""
        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            filter_by_message_types(full_conversation, [HumanMessage, AIMessage])

        mock_logger.debug.assert_called_once()
        call_kwargs = mock_logger.debug.call_args[1]
        assert "HumanMessage" in call_kwargs["types"]
        assert "AIMessage" in call_kwargs["types"]

    def test_uses_exact_type_matching(self):
        """Test that type matching is exact (uses type() not isinstance)."""

        # Create subclass
        class SpecialHumanMessage(HumanMessage):
            pass

        messages = [
            HumanMessage(content="Regular"),
            SpecialHumanMessage(content="Special"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_by_message_types(messages, [HumanMessage])

        # Only exact HumanMessage should match, not subclass
        assert len(result) == 1
        assert result[0].content == "Regular"

    def test_filter_all_types_returns_all(self, full_conversation):
        """Test filtering by all present types returns all messages."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_by_message_types(
                full_conversation, [HumanMessage, AIMessage, ToolMessage, SystemMessage]
            )

        assert len(result) == len(full_conversation)


# ============================================================================
# Tests for extract_system_messages
# ============================================================================


class TestExtractSystemMessages:
    """Tests for extract_system_messages()."""

    def test_extracts_all_system_messages(self):
        """Test extraction of all SystemMessages."""
        messages = [
            SystemMessage(content="System 1"),
            HumanMessage(content="Hello"),
            SystemMessage(content="System 2"),
            AIMessage(content="Hi"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = extract_system_messages(messages)

        assert len(result) == 2
        assert all(isinstance(m, SystemMessage) for m in result)

    def test_returns_empty_if_no_system_messages(self):
        """Test returns empty list if no SystemMessages."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = extract_system_messages(messages)

        assert result == []

    def test_preserves_order(self):
        """Test that order of SystemMessages is preserved."""
        messages = [
            SystemMessage(content="First"),
            HumanMessage(content="Middle"),
            SystemMessage(content="Second"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = extract_system_messages(messages)

        assert result[0].content == "First"
        assert result[1].content == "Second"

    def test_empty_list_returns_empty(self):
        """Test that empty input returns empty output."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = extract_system_messages([])

        assert result == []

    def test_includes_internal_system_markers(self, internal_system_message):
        """Test that internal system markers are also extracted."""
        messages = [internal_system_message]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = extract_system_messages(messages)

        # extract_system_messages extracts ALL SystemMessages including internal ones
        assert len(result) == 1
        assert result[0].content == "__PLAN_REJECTED__"

    def test_logs_extraction_stats(self):
        """Test that extraction statistics are logged."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="User"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            extract_system_messages(messages)

        mock_logger.debug.assert_called_once()
        call_kwargs = mock_logger.debug.call_args[1]
        assert call_kwargs["total_messages"] == 2
        assert call_kwargs["system_messages_count"] == 1

    def test_extracts_multiple_system_messages(self):
        """Test extracting multiple SystemMessages preserves content."""
        messages = [
            SystemMessage(content="System 1"),
            HumanMessage(content="User"),
            SystemMessage(content="System 2"),
            AIMessage(content="AI"),
            SystemMessage(content="System 3"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = extract_system_messages(messages)

        assert len(result) == 3
        assert [m.content for m in result] == ["System 1", "System 2", "System 3"]


# ============================================================================
# Tests for remove_orphan_tool_messages
# ============================================================================


class TestRemoveOrphanToolMessages:
    """Tests for remove_orphan_tool_messages()."""

    def test_keeps_tool_messages_with_matching_ai_message(self):
        """Test that ToolMessages with matching AIMessage are kept."""
        messages = [
            HumanMessage(content="Search"),
            AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search", "args": {}}]),
            ToolMessage(content='{"data": "result"}', tool_call_id="call_1"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        assert len(result) == 3

    def test_removes_orphan_tool_messages(self):
        """Test that ToolMessages without matching AIMessage are removed."""
        messages = [
            HumanMessage(content="Search"),
            ToolMessage(content='{"data": "result"}', tool_call_id="orphan_id"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_keeps_non_tool_messages(self):
        """Test that non-ToolMessages are always kept."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
            SystemMessage(content="System"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        assert len(result) == 3

    def test_handles_multiple_tool_calls(self):
        """Test handling of multiple tool calls in one AIMessage."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call_1", "name": "search", "args": {}},
                    {"id": "call_2", "name": "filter", "args": {}},
                ],
            ),
            ToolMessage(content='{"data": "1"}', tool_call_id="call_1"),
            ToolMessage(content='{"data": "2"}', tool_call_id="call_2"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        assert len(result) == 3

    def test_empty_list_returns_empty(self):
        """Test that empty input returns empty output."""
        result = remove_orphan_tool_messages([])
        assert result == []

    def test_removes_only_orphan_tool_messages(self):
        """Test that only orphan ToolMessages are removed."""
        messages = [
            AIMessage(content="", tool_calls=[{"id": "valid_id", "name": "tool", "args": {}}]),
            ToolMessage(content="valid", tool_call_id="valid_id"),
            ToolMessage(content="orphan", tool_call_id="invalid_id"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        assert len(result) == 2
        # Check the orphan was removed
        tool_msgs = [m for m in result if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].content == "valid"

    def test_logs_orphan_removal_warning(self, orphan_tool_message):
        """Test that orphan removal is logged with warning."""
        messages = [orphan_tool_message]

        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            remove_orphan_tool_messages(messages)

        mock_logger.warning.assert_called()
        # Check the event name
        assert mock_logger.warning.call_args[0][0] == "orphan_tool_message_removed"

    def test_logs_summary_when_orphans_found(self, orphan_tool_message):
        """Test that summary is logged when orphans are found."""
        messages = [HumanMessage(content="Test"), orphan_tool_message]

        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            remove_orphan_tool_messages(messages)

        mock_logger.info.assert_called()
        call_kwargs = mock_logger.info.call_args[1]
        assert call_kwargs["orphans_removed"] == 1

    def test_no_summary_log_when_no_orphans(self):
        """Test that no summary is logged when no orphans found."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "test", "args": {}}],
            ),
            ToolMessage(content="{}", tool_call_id="call_1"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            remove_orphan_tool_messages(messages)

        # info should not be called (only called when orphans removed)
        mock_logger.info.assert_not_called()

    def test_handles_tool_call_as_dict(self):
        """Test handling tool_calls as dict with 'id' key."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_dict", "name": "tool", "args": {}}],
            ),
            ToolMessage(content="{}", tool_call_id="call_dict"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        assert len(result) == 2

    def test_handles_tool_message_without_tool_call_id(self):
        """Test handling ToolMessage without tool_call_id attribute."""
        tool_msg = ToolMessage(content="{}", tool_call_id="some_id")

        # Create message with tool_call_id = None via getattr default
        messages = [tool_msg]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        # Should be removed as orphan (no matching AI message)
        assert len(result) == 0

    def test_preserves_message_order(self):
        """Test that message order is preserved after filtering."""
        messages = [
            HumanMessage(content="First"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "tool", "args": {}}],
            ),
            ToolMessage(content="{}", tool_call_id="call_1"),
            AIMessage(content="Last"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        assert result[0].content == "First"
        assert result[-1].content == "Last"

    def test_mixed_valid_and_orphan_tool_messages(self):
        """Test filtering mixed valid and orphan ToolMessages."""
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_valid", "name": "search", "args": {}}],
            ),
            ToolMessage(content='{"valid": true}', tool_call_id="call_valid"),
            ToolMessage(content='{"orphan": true}', tool_call_id="call_orphan"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = remove_orphan_tool_messages(messages)

        assert len(result) == 2
        # Valid tool message kept
        assert any(isinstance(m, ToolMessage) and m.tool_call_id == "call_valid" for m in result)
        # Orphan removed
        assert not any(
            isinstance(m, ToolMessage) and m.tool_call_id == "call_orphan" for m in result
        )


# ============================================================================
# Tests for filter_for_llm_context
# ============================================================================


class TestFilterForLlmContext:
    """Tests for filter_for_llm_context()."""

    def test_keeps_human_messages(self):
        """Test that HumanMessages are kept."""
        messages = [HumanMessage(content="Hello")]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_keeps_tool_messages(self):
        """Test that ToolMessages are kept (JSON data)."""
        messages = [ToolMessage(content='{"data": "value"}', tool_call_id="1")]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 1

    def test_keeps_simple_ai_messages(self):
        """Test that simple AIMessages without HTML are kept."""
        messages = [AIMessage(content="Simple response")]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 1

    def test_filters_ai_messages_with_tool_calls(self):
        """Test that AIMessages with tool_calls are filtered."""
        messages = [
            AIMessage(content="", tool_calls=[{"id": "1", "name": "tool", "args": {}}]),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 0

    def test_replaces_ai_html_with_text_before(self):
        """Test that AI messages with HTML keep text before HTML."""
        messages = [AIMessage(content='Here is the result!\n\n<div class="lia-card">Card</div>')]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 1
        assert result[0].content == "Here is the result!"

    def test_replaces_ai_html_only_with_placeholder(self):
        """Test that AI messages with only HTML get placeholder."""
        messages = [AIMessage(content="<div class='lia-card'>Card</div>")]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 1
        assert result[0].content == "[Résultats affichés]"

    def test_filters_internal_system_markers(self):
        """Test that SystemMessages starting with __ are filtered."""
        messages = [
            SystemMessage(content="__INTERNAL_MARKER__"),
            SystemMessage(content="Normal system message"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 1
        assert result[0].content == "Normal system message"

    def test_empty_list_returns_empty(self):
        """Test that empty input returns empty output."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context([])

        assert result == []

    def test_extracts_text_from_ai_with_html_single_quotes(self, ai_message_with_html):
        """Test extracting text before HTML with single quotes."""
        messages = [ai_message_with_html]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 1
        assert result[0].content == "Voici les contacts!"

    def test_extracts_text_from_ai_with_html_double_quotes(self, ai_message_html_double_quotes):
        """Test extracting text before HTML with double quotes."""
        messages = [ai_message_html_double_quotes]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert len(result) == 1
        # No text before HTML, should use placeholder
        assert result[0].content == "[Résultats affichés]"

    def test_full_conversation_filtering(self, full_conversation):
        """Test filtering full conversation for LLM context."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(full_conversation)

        # Should keep: SystemMessage, HumanMessages, ToolMessages, AIMessages without tool_calls
        # Removes: AIMessages with tool_calls
        human_count = sum(1 for m in result if isinstance(m, HumanMessage))
        tool_count = sum(1 for m in result if isinstance(m, ToolMessage))
        ai_count = sum(1 for m in result if isinstance(m, AIMessage))
        system_count = sum(1 for m in result if isinstance(m, SystemMessage))

        assert human_count == 2
        assert tool_count == 2
        assert ai_count == 2  # Only AIMessages without tool_calls
        assert system_count == 1

    def test_logs_filtering_stats(self, full_conversation):
        """Test that filtering statistics are logged."""
        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            filter_for_llm_context(full_conversation)

        mock_logger.debug.assert_called_once()
        call_kwargs = mock_logger.debug.call_args[1]
        assert "original_count" in call_kwargs
        assert "filtered_count" in call_kwargs

    def test_handles_ai_message_with_empty_content(self):
        """Test handling AIMessage with empty content."""
        ai_msg = AIMessage(content="")
        messages = [ai_msg]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        # Should be kept (no HTML in empty string)
        assert len(result) == 1

    def test_handles_system_message_with_empty_content(self):
        """Test handling SystemMessage with empty content."""
        sys_msg = SystemMessage(content="")
        messages = [sys_msg]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        # Should be kept (doesn't start with __)
        assert len(result) == 1

    def test_preserves_message_order(self):
        """Test that message order is preserved."""
        messages = [
            HumanMessage(content="First"),
            AIMessage(content="Second"),
            HumanMessage(content="Third"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        assert result[0].content == "First"
        assert result[1].content == "Second"
        assert result[2].content == "Third"


# ============================================================================
# Tests for split_messages_by_turn
# ============================================================================


class TestSplitMessagesByTurn:
    """Tests for split_messages_by_turn()."""

    def test_splits_simple_conversation(self):
        """Test splitting simple conversation into turns."""
        messages = [
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        assert len(turns) == 2
        assert turns[0][0].content == "Q1"
        assert len(turns[0][1]) == 1
        assert turns[0][1][0].content == "A1"

    def test_handles_multiple_responses_per_turn(self):
        """Test turn with multiple response messages."""
        messages = [
            HumanMessage(content="Search"),
            AIMessage(content="", tool_calls=[{"id": "1", "name": "search", "args": {}}]),
            ToolMessage(content="result", tool_call_id="1"),
            AIMessage(content="Here is the result"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        assert len(turns) == 1
        assert turns[0][0].content == "Search"
        assert len(turns[0][1]) == 3

    def test_handles_unanswered_question(self):
        """Test turn with HumanMessage but no responses yet."""
        messages = [
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),  # No response yet
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        assert len(turns) == 2
        assert turns[1][0].content == "Q2"
        assert len(turns[1][1]) == 0

    def test_empty_list_returns_empty(self):
        """Test that empty input returns empty output."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn([])

        assert turns == []

    def test_ignores_messages_before_first_human(self):
        """Test that messages before first HumanMessage are ignored."""
        messages = [
            SystemMessage(content="System"),
            AIMessage(content="Greeting"),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        # Should have 1 turn, messages before first HumanMessage ignored
        assert len(turns) == 1
        assert turns[0][0].content == "Hello"

    def test_preserves_order_within_turn(self):
        """Test that response order within turn is preserved."""
        messages = [
            HumanMessage(content="Q"),
            AIMessage(content="Response 1"),
            AIMessage(content="Response 2"),
            AIMessage(content="Response 3"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        assert turns[0][1][0].content == "Response 1"
        assert turns[0][1][1].content == "Response 2"
        assert turns[0][1][2].content == "Response 3"

    def test_handles_turn_with_no_responses(self):
        """Test handling turn with no responses."""
        messages = [
            HumanMessage(content="Hello"),
            HumanMessage(content="Anyone there?"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        assert len(turns) == 2
        assert turns[0][0].content == "Hello"
        assert turns[0][1] == []  # No responses
        assert turns[1][0].content == "Anyone there?"
        assert turns[1][1] == []  # No responses

    def test_handles_only_non_human_messages(self):
        """Test handling list with no HumanMessages."""
        messages = [
            SystemMessage(content="System"),
            AIMessage(content="AI response"),
            ToolMessage(content="{}", tool_call_id="c1"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        # No turns since no HumanMessage
        assert turns == []

    def test_logs_split_stats(self):
        """Test that split statistics are logged."""
        messages = [
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger") as mock_logger:
            split_messages_by_turn(messages)

        mock_logger.debug.assert_called_once()
        call_kwargs = mock_logger.debug.call_args[1]
        assert call_kwargs["total_messages"] == 4
        assert call_kwargs["turns_count"] == 2

    def test_single_human_message_only(self):
        """Test handling single HumanMessage with no responses."""
        messages = [HumanMessage(content="Hello")]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        assert len(turns) == 1
        assert turns[0][0].content == "Hello"
        assert turns[0][1] == []

    def test_responses_include_all_message_types(self):
        """Test that responses include all non-Human message types."""
        messages = [
            HumanMessage(content="Query"),
            SystemMessage(content="System reminder"),
            AIMessage(content="Response"),
            ToolMessage(content="{}", tool_call_id="c1"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(messages)

        assert len(turns) == 1
        # All non-Human messages in responses
        assert len(turns[0][1]) == 3
        assert isinstance(turns[0][1][0], SystemMessage)
        assert isinstance(turns[0][1][1], AIMessage)
        assert isinstance(turns[0][1][2], ToolMessage)


# ============================================================================
# Integration tests
# ============================================================================


class TestIntegrationScenarios:
    """Integration tests for realistic scenarios."""

    def test_full_tool_conversation_filtering(self):
        """Test filtering a complete tool-based conversation."""
        messages = [
            SystemMessage(content="You are helpful"),
            HumanMessage(content="Find John"),
            AIMessage(content="", tool_calls=[{"id": "1", "name": "search", "args": {}}]),
            ToolMessage(content='{"name": "John", "email": "john@example.com"}', tool_call_id="1"),
            AIMessage(content='<div class="lia-card">John\'s card</div>'),
            HumanMessage(content="Email him"),
            AIMessage(content="", tool_calls=[{"id": "2", "name": "send_email", "args": {}}]),
            ToolMessage(content='{"status": "sent"}', tool_call_id="2"),
            AIMessage(content='Done! <div class="lia-card">Confirmation</div>'),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            # Test conversational filtering
            conversational = filter_conversational_messages(messages)
            # Should have: 2 HumanMessages + 2 AIMessages (without tool_calls)
            assert len(conversational) == 4
            human_count = sum(1 for m in conversational if isinstance(m, HumanMessage))
            ai_count = sum(1 for m in conversational if isinstance(m, AIMessage))
            assert human_count == 2
            assert ai_count == 2

            # Test LLM context filtering
            llm_context = filter_for_llm_context(messages)
            # Should have: SystemMessage, 2 HumanMessages, 2 ToolMessages,
            # 2 modified AIMessages (one with placeholder, one with "Done!")
            human_count = sum(1 for m in llm_context if isinstance(m, HumanMessage))
            tool_count = sum(1 for m in llm_context if isinstance(m, ToolMessage))
            assert human_count == 2
            assert tool_count == 2

    def test_filter_then_remove_orphans(self, full_conversation):
        """Test filtering then removing orphans."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            # First filter for LLM context
            filtered = filter_for_llm_context(full_conversation)
            # Then remove orphan tool messages
            cleaned = remove_orphan_tool_messages(filtered)

        # All ToolMessages should be orphans now (AIMessages with tool_calls were removed)
        tool_messages = [m for m in cleaned if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 0

    def test_extract_system_then_filter_conversational(self, full_conversation):
        """Test extracting system messages then filtering conversational."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            system_msgs = extract_system_messages(full_conversation)
            conversational = filter_conversational_messages(full_conversation)

        # Combine for agent input
        system_msgs + conversational

        # Should have system + conversational messages
        assert len(system_msgs) == 1
        assert len(conversational) == 4  # 2 Human + 2 AI without tool_calls

    def test_split_then_analyze_turns(self, full_conversation):
        """Test splitting then analyzing individual turns."""
        with patch("src.domains.agents.utils.message_filters.logger"):
            turns = split_messages_by_turn(full_conversation)

        for _user_msg, responses in turns:
            # Each turn should have responses
            assert len(responses) > 0

            # Extract tool messages from this turn
            turn_tool_msgs = filter_tool_messages(responses)
            assert len(turn_tool_msgs) == 1  # Each turn has one tool execution

    def test_immutability_of_input(self, full_conversation):
        """Test that input lists are never modified."""
        original_count = len(full_conversation)
        original_content = [m.content for m in full_conversation]

        with patch("src.domains.agents.utils.message_filters.logger"):
            filter_conversational_messages(full_conversation)
            filter_tool_messages(full_conversation)
            filter_by_message_types(full_conversation, [HumanMessage])
            extract_system_messages(full_conversation)
            remove_orphan_tool_messages(full_conversation)
            filter_for_llm_context(full_conversation)
            split_messages_by_turn(full_conversation)

        # Original list should be unchanged
        assert len(full_conversation) == original_count
        assert [m.content for m in full_conversation] == original_content

    def test_chained_filtering(self):
        """Test chaining multiple filters."""
        messages = [
            SystemMessage(content="System"),
            HumanMessage(content="User 1"),
            AIMessage(content="", tool_calls=[{"id": "c1", "name": "t", "args": {}}]),
            ToolMessage(content="{}", tool_call_id="c1"),
            AIMessage(content="Response 1"),
            HumanMessage(content="User 2"),
            AIMessage(content="<div class='lia-card'>HTML</div>"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            # Chain: filter for LLM context -> remove orphans
            step1 = filter_for_llm_context(messages)
            step2 = remove_orphan_tool_messages(step1)

        # Verify expected result
        human_msgs = [m for m in step2 if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 2

    def test_complex_html_filtering_scenario(self):
        """Test complex scenario with various HTML patterns."""
        messages = [
            HumanMessage(content="Météo"),
            AIMessage(content="Il fait beau!\n\n<div class='lia-card'>☀️ 25°C</div>"),
            HumanMessage(content="Contacts"),
            AIMessage(content='<div class="lia-card">Jean Dupont</div>'),  # HTML only
            HumanMessage(content="Email"),
            AIMessage(content="Email envoyé!"),  # Simple response
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            result = filter_for_llm_context(messages)

        # Human messages kept
        humans = [m for m in result if isinstance(m, HumanMessage)]
        assert len(humans) == 3

        # AI messages transformed
        ais = [m for m in result if isinstance(m, AIMessage)]
        assert len(ais) == 3
        assert ais[0].content == "Il fait beau!"  # Text before HTML
        assert ais[1].content == "[Résultats affichés]"  # Placeholder
        assert ais[2].content == "Email envoyé!"  # Unchanged

    def test_realistic_multi_turn_tool_conversation(self):
        """Test realistic multi-turn tool conversation."""
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Find contacts named Jean"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "search_1", "name": "search_contacts", "args": {"query": "Jean"}}
                ],
            ),
            ToolMessage(
                content='{"results": [{"name": "Jean Dupont", "email": "jean@example.com"}]}',
                tool_call_id="search_1",
            ),
            AIMessage(content="J'ai trouvé Jean Dupont. <div class='lia-card'>Jean Dupont</div>"),
            HumanMessage(content="Send him an email"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "email_1", "name": "send_email", "args": {"to": "jean@example.com"}}
                ],
            ),
            ToolMessage(
                content='{"status": "sent", "message_id": "msg_123"}', tool_call_id="email_1"
            ),
            AIMessage(content="Email envoyé avec succès!"),
        ]

        with patch("src.domains.agents.utils.message_filters.logger"):
            # Split by turns
            turns = split_messages_by_turn(messages)
            assert len(turns) == 2

            # Filter for conversational context
            conversational = filter_conversational_messages(messages)
            # Only HumanMessages and AIMessages without tool_calls
            assert len(conversational) == 4

            # Filter for LLM context
            llm_context = filter_for_llm_context(messages)
            # Check HTML handling
            ai_messages = [m for m in llm_context if isinstance(m, AIMessage)]
            # First AI response should have text extracted
            assert ai_messages[0].content == "J'ai trouvé Jean Dupont."
            # Second AI response is simple text
            assert ai_messages[1].content == "Email envoyé avec succès!"
