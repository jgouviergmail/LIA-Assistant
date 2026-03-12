"""
Performance and Regression Tests for State Management.

Tests LangGraph v1.0 state management compliance:
- add_messages reducer behavior
- Message truncation performance
- Token-based truncation
- RemoveMessage support (HITL edit workflow)

Compliance: LangGraph v1.0 best practices
"""

import time

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)

from src.domains.agents.models import (
    add_messages_with_truncate,
    create_initial_state,
    validate_state_consistency,
)


class TestAddMessagesReducer:
    """Test add_messages reducer with RemoveMessage support."""

    def test_add_messages_basic(self):
        """Test basic message addition."""
        left = [HumanMessage(content="Hello")]
        right = [AIMessage(content="Hi")]

        result = add_messages_with_truncate(left, right)

        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "Hi"

    def test_add_messages_with_remove(self):
        """Test RemoveMessage support (HITL edit workflow)."""
        # Setup: existing messages
        msg1 = HumanMessage(content="Original", id="msg-1")
        msg2 = AIMessage(content="Response", id="msg-2")
        left = [msg1, msg2]

        # Remove msg1 and add new message
        right = [RemoveMessage(id="msg-1"), HumanMessage(content="Edited", id="msg-3")]

        result = add_messages_with_truncate(left, right)

        # Should have msg2 and msg3, but not msg1
        assert len(result) == 2
        assert result[0].id == "msg-2"  # Original response kept
        assert result[1].id == "msg-3"  # New edited message
        assert result[1].content == "Edited"

    def test_empty_messages(self):
        """Test handling of empty message lists."""
        result = add_messages_with_truncate([], [])
        assert result == []


class TestMessageTruncation:
    """Test message truncation performance and correctness."""

    def test_massive_history_truncation_performance(self):
        """
        Test truncation performance with massive history (500 messages).

        Performance requirement: <100ms for 500 messages
        """
        # Create 500 messages (alternating human/ai)
        messages = []
        for i in range(500):
            if i % 2 == 0:
                messages.append(HumanMessage(content=f"Question {i}"))
            else:
                messages.append(AIMessage(content=f"Answer {i}"))

        # Measure truncation time
        start = time.perf_counter()
        result = add_messages_with_truncate([], messages)
        duration = time.perf_counter() - start

        # Assertions
        assert len(result) < 500, "Truncation should reduce message count"
        assert duration < 0.1, f"Truncation took {duration:.3f}s, expected <0.1s"

        print(f"\n[PERF] Truncated 500 → {len(result)} messages in {duration * 1000:.2f}ms")

    def test_system_message_preservation(self):
        """Test that SystemMessage is always preserved."""
        system_msg = SystemMessage(content="You are an assistant")
        user_msgs = [HumanMessage(content=f"Message {i}") for i in range(100)]

        messages = [system_msg] + user_msgs
        result = add_messages_with_truncate([], messages)

        # SystemMessage should be first
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are an assistant"

    def test_token_based_truncation(self):
        """Test that token-based truncation works correctly."""
        # Create messages with known token counts
        # Short message: ~10 tokens
        # Long message: ~100 tokens
        messages = [
            HumanMessage(content="Short message"),
            AIMessage(content="This is a much longer message " * 10),
            HumanMessage(content="Another short one"),
            AIMessage(content="Very long response " * 20),
        ]

        result = add_messages_with_truncate([], messages)

        # Should keep recent messages within token limit
        assert len(result) > 0
        assert len(result) <= len(messages)

    def test_orphan_tool_message_removal(self):
        """
        Test that orphan ToolMessages are removed after truncation.

        Scenario: Truncation cuts off AIMessage with tool_calls,
        leaving orphan ToolMessage (would cause OpenAI API error).
        """
        # Create sequence: Human → AI(tool_calls) → Tool → AI → Human
        messages = [
            HumanMessage(content="Search contacts"),
            AIMessage(
                content="", tool_calls=[{"name": "search", "args": {}, "id": "call-1"}], id="ai-1"
            ),
            ToolMessage(content="Results", tool_call_id="call-1", id="tool-1"),
            AIMessage(content="Found 3 contacts", id="ai-2"),
            HumanMessage(content="Show first", id="human-2"),
        ]

        # Simulate truncation that removes AI message with tool_calls
        # Force truncation by providing only recent messages
        truncated_input = messages[2:]  # Start from ToolMessage (orphan)

        result = add_messages_with_truncate([], truncated_input)

        # Orphan ToolMessage should be removed
        tool_messages = [m for m in result if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 0, "Orphan ToolMessage should be removed"


class TestStateValidation:
    """Test state consistency validation."""

    def test_valid_state(self):
        """Test validation passes for valid state."""
        state = create_initial_state(
            user_id="test-user", session_id="test-session", run_id="test-run"
        )

        issues = validate_state_consistency(state)
        assert issues == [], f"Valid state should have no issues: {issues}"

    def test_future_turn_detection(self):
        """Test detection of future turn_id in agent_results."""
        state = create_initial_state(
            user_id="test-user", session_id="test-session", run_id="test-run"
        )
        state["current_turn_id"] = 3
        state["agent_results"] = {
            "3:contacts_agent": {"status": "success"},
            "5:emails_agent": {"status": "success"},  # Future turn!
        }

        issues = validate_state_consistency(state)

        assert len(issues) > 0
        assert any("Future turn" in issue for issue in issues)

    def test_invalid_key_format(self):
        """Test detection of invalid agent_results key format."""
        state = create_initial_state(
            user_id="test-user", session_id="test-session", run_id="test-run"
        )
        state["agent_results"] = {
            "contacts_agent": {"status": "success"},  # Missing turn_id!
        }

        issues = validate_state_consistency(state)

        assert len(issues) > 0
        assert any("Invalid agent_results key format" in issue for issue in issues)

    def test_negative_turn_id(self):
        """Test detection of negative turn_id."""
        state = create_initial_state(
            user_id="test-user", session_id="test-session", run_id="test-run"
        )
        state["current_turn_id"] = -1

        issues = validate_state_consistency(state)

        assert len(issues) > 0
        assert any("Negative turn_id" in issue for issue in issues)


class TestStateSchema:
    """Test state schema compliance with LangGraph v1.0."""

    def test_initial_state_structure(self):
        """Test that initial state has all required fields."""
        state = create_initial_state(
            user_id="test-user",
            session_id="test-session",
            run_id="test-run",
            user_timezone="America/New_York",
            user_language="en",
        )

        # Check all required fields exist
        assert "messages" in state
        assert "metadata" in state
        assert "routing_history" in state
        assert "agent_results" in state
        assert "orchestration_plan" in state
        assert "current_turn_id" in state
        assert "user_timezone" in state
        assert "user_language" in state
        assert "_schema_version" in state

        # Check field types
        assert isinstance(state["messages"], list)
        assert isinstance(state["metadata"], dict)
        assert isinstance(state["routing_history"], list)
        assert isinstance(state["agent_results"], dict)
        assert isinstance(state["current_turn_id"], int)
        assert isinstance(state["user_timezone"], str)
        assert isinstance(state["user_language"], str)
        assert isinstance(state["_schema_version"], str)

        # Check initial values
        assert state["current_turn_id"] == 0
        assert state["user_timezone"] == "America/New_York"
        assert state["user_language"] == "en"
        assert state["_schema_version"] == "1.0"

    def test_schema_version_tracking(self):
        """Test schema version is properly tracked."""
        state = create_initial_state(
            user_id="test-user", session_id="test-session", run_id="test-run"
        )

        assert state["_schema_version"] == "1.0"


class TestTruncationEdgeCases:
    """Test edge cases and corner scenarios for truncation."""

    def test_only_system_message(self):
        """Test truncation with only SystemMessage."""
        messages = [SystemMessage(content="System prompt")]
        result = add_messages_with_truncate([], messages)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)

    def test_alternating_human_ai(self):
        """Test truncation preserves conversation structure."""
        messages = []
        for i in range(50):
            messages.append(HumanMessage(content=f"Q{i}"))
            messages.append(AIMessage(content=f"A{i}"))

        result = add_messages_with_truncate([], messages)

        # Check that conversation structure is maintained
        # (though some may be truncated)
        assert len(result) > 0
        assert len(result) <= len(messages)

    def test_tool_message_sequence(self):
        """Test proper handling of tool message sequences."""
        messages = [
            HumanMessage(content="Search"),
            AIMessage(
                content="", tool_calls=[{"name": "search", "args": {}, "id": "call-1"}], id="ai-1"
            ),
            ToolMessage(content="Result 1", tool_call_id="call-1", id="tool-1"),
            AIMessage(content="Found it", id="ai-2"),
        ]

        result = add_messages_with_truncate([], messages)

        # All messages should be kept (small set)
        assert len(result) == 4

        # Validate no orphan ToolMessages
        for i, msg in enumerate(result):
            if isinstance(msg, ToolMessage):
                # Find corresponding AIMessage before it
                found_ai_with_tool_calls = False
                for j in range(i):
                    if isinstance(result[j], AIMessage) and hasattr(result[j], "tool_calls"):
                        if result[j].tool_calls:
                            found_ai_with_tool_calls = True
                            break
                assert found_ai_with_tool_calls, "ToolMessage without corresponding AIMessage"


class TestStateManagementIntegration:
    """Integration tests for complete state management workflow."""

    def test_full_conversation_flow(self):
        """Test complete conversation with truncation."""
        # Start with initial state
        messages = [SystemMessage(content="System")]

        # Simulate 100 conversation turns
        for i in range(100):
            messages.append(HumanMessage(content=f"User message {i}"))
            messages.append(AIMessage(content=f"AI response {i}"))

        # Apply truncation
        result = add_messages_with_truncate([], messages)

        # Validate
        assert len(result) < len(messages)  # Truncated
        assert isinstance(result[0], SystemMessage)  # System preserved
        assert len([m for m in result if isinstance(m, ToolMessage)]) == 0  # No orphans

    def test_hitl_edit_workflow(self):
        """Test HITL edit workflow with RemoveMessage."""
        # Initial conversation
        messages = [
            HumanMessage(content="Search jean", id="human-1"),
            AIMessage(content="Searching...", id="ai-1"),
        ]

        # User edits request via HITL
        edit_messages = [
            RemoveMessage(id="human-1"),
            HumanMessage(content="Search jean", id="human-2"),
        ]

        result = add_messages_with_truncate(messages, edit_messages)

        # Original human message should be removed
        human_msgs = [m for m in result if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 1
        assert human_msgs[0].content == "Search jean"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
