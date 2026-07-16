"""
Tests for HITL message filtering logic.

DISABLED: HITL message filtering is now disabled.
All messages (including HITL APPROVE/REJECT responses) are shown and counted.

These tests verify that _should_filter_hitl_message() always returns False
and no messages are filtered.
"""

from src.domains.conversations.service import ConversationService


class TestHitlMessageFiltering:
    """Test HITL message filtering logic - NOW DISABLED."""

    def test_should_not_filter_hitl_approve(self):
        """APPROVE messages should NOT be filtered (filtering disabled)."""
        metadata = {
            "hitl_response": True,
            "decision_type": "APPROVE",
            "run_id": "test123",
        }

        result = ConversationService._should_filter_hitl_message("user", metadata)

        assert result is False, "APPROVE messages should NOT be filtered (filtering disabled)"

    def test_should_not_filter_hitl_reject(self):
        """REJECT messages should NOT be filtered (filtering disabled)."""
        metadata = {
            "hitl_response": True,
            "decision_type": "REJECT",
            "run_id": "test123",
        }

        result = ConversationService._should_filter_hitl_message("user", metadata)

        assert result is False, "REJECT messages should NOT be filtered (filtering disabled)"

    def test_should_not_filter_hitl_edit(self):
        """EDIT messages should NOT be filtered."""
        metadata = {
            "hitl_response": True,
            "decision_type": "EDIT",
            "run_id": "test123",
            "edited_params": {"name": "paul"},
        }

        result = ConversationService._should_filter_hitl_message("user", metadata)

        assert result is False, "EDIT messages should be kept"

    def test_should_not_filter_hitl_ambiguous(self):
        """AMBIGUOUS messages should NOT be filtered."""
        metadata = {
            "hitl_response": True,
            "decision_type": "AMBIGUOUS",
            "run_id": "test123",
            "clarification_question": "Did you mean...?",
        }

        result = ConversationService._should_filter_hitl_message("user", metadata)

        assert result is False, "AMBIGUOUS messages should be kept"

    def test_should_not_filter_non_hitl_messages(self):
        """Non-HITL messages should NOT be filtered."""
        metadata = {"run_id": "test123", "intention": "contacts"}

        result = ConversationService._should_filter_hitl_message("user", metadata)

        assert result is False, "Non-HITL messages should be kept"

    def test_should_not_filter_assistant_messages(self):
        """Assistant messages should NOT be filtered."""
        metadata = {
            "hitl_response": True,
            "decision_type": "APPROVE",
        }

        result = ConversationService._should_filter_hitl_message("assistant", metadata)

        assert result is False, "Assistant messages should never be filtered"

    def test_should_not_filter_assistant_hitl_question(self):
        """Assistant HITL question messages should NOT be filtered (filtering disabled)."""
        metadata = {
            "hitl_question": True,
        }

        result = ConversationService._should_filter_hitl_message("assistant", metadata)

        assert result is False, "HITL questions should NOT be filtered (filtering disabled)"

    def test_should_not_filter_user_hitl_interrupted(self):
        """User messages marked as hitl_interrupted should NOT be filtered (filtering disabled)."""
        metadata = {
            "hitl_interrupted": True,
            "run_id": "test123",
        }

        result = ConversationService._should_filter_hitl_message("user", metadata)

        assert (
            result is False
        ), "hitl_interrupted messages should NOT be filtered (filtering disabled)"

    def test_should_not_filter_when_no_metadata(self):
        """Messages without metadata should NOT be filtered."""
        result = ConversationService._should_filter_hitl_message("user", None)

        assert result is False, "Messages without metadata should be kept"

    def test_should_not_filter_when_metadata_empty(self):
        """Messages with empty metadata should NOT be filtered."""
        result = ConversationService._should_filter_hitl_message("user", {})

        assert result is False, "Messages with empty metadata should be kept"

    def test_filter_hitl_messages_dict_keeps_all_messages(self):
        """filter_hitl_messages_dict should keep ALL messages (filtering disabled)."""
        messages = [
            {
                "id": "1",
                "role": "user",
                "content": "recherche jean",
                "message_metadata": None,
            },
            {
                "id": "2",
                "role": "assistant",
                "content": "Question HITL",
                "message_metadata": {"hitl_question": True},
            },
            {
                "id": "3",
                "role": "user",
                "content": "oui",
                "message_metadata": {
                    "hitl_response": True,
                    "decision_type": "APPROVE",
                },
            },
            {
                "id": "4",
                "role": "assistant",
                "content": "Résultats...",
                "message_metadata": None,
            },
            {
                "id": "5",
                "role": "user",
                "content": "recherche paul",
                "message_metadata": None,
            },
            {
                "id": "6",
                "role": "user",
                "content": "non annule",
                "message_metadata": {
                    "hitl_response": True,
                    "decision_type": "REJECT",
                },
            },
        ]

        filtered = ConversationService._filter_hitl_messages_dict(messages)

        # No filtering: all 6 messages should be kept
        assert len(filtered) == 6, "All messages should be kept (filtering disabled)"
        assert filtered[0]["id"] == "1"
        assert filtered[1]["id"] == "2"  # hitl_question kept
        assert filtered[2]["id"] == "3"  # APPROVE kept
        assert filtered[3]["id"] == "4"
        assert filtered[4]["id"] == "5"
        assert filtered[5]["id"] == "6"  # REJECT kept

    def test_filter_hitl_messages_dict_keeps_edit(self):
        """filter_hitl_messages_dict should keep all messages including EDIT."""
        messages = [
            {
                "id": "1",
                "role": "user",
                "content": "recherche jean",
                "message_metadata": None,
            },
            {
                "id": "2",
                "role": "assistant",
                "content": "Question HITL",
                "message_metadata": {"hitl_question": True},
            },
            {
                "id": "3",
                "role": "user",
                "content": "non cherche paul",
                "message_metadata": {
                    "hitl_response": True,
                    "decision_type": "EDIT",
                    "edited_params": {"name": "paul"},
                },
            },
        ]

        filtered = ConversationService._filter_hitl_messages_dict(messages)

        # All 3 messages should be kept
        assert len(filtered) == 3, "All messages should be kept (filtering disabled)"
        assert filtered[0]["id"] == "1"
        assert filtered[1]["id"] == "2"  # hitl_question kept
        assert filtered[2]["id"] == "3"  # EDIT kept

    def test_filter_hitl_messages_dict_keeps_ambiguous(self):
        """filter_hitl_messages_dict should keep AMBIGUOUS messages."""
        messages = [
            {
                "id": "1",
                "role": "user",
                "content": "recherche jean",
                "message_metadata": None,
            },
            {
                "id": "2",
                "role": "user",
                "content": "peut-être",
                "message_metadata": {
                    "hitl_response": True,
                    "decision_type": "AMBIGUOUS",
                    "clarification_question": "Voulez-vous dire...?",
                },
            },
        ]

        filtered = ConversationService._filter_hitl_messages_dict(messages)

        assert len(filtered) == 2, "All messages should be kept"
        assert any(msg["id"] == "2" for msg in filtered), "AMBIGUOUS message should be kept"

    def test_total_count_calculation_includes_all_hitl(self):
        """total_count should include ALL user messages (including HITL APPROVE/REJECT)."""
        messages = [
            {"id": "1", "role": "user", "content": "msg1", "message_metadata": None},
            {
                "id": "2",
                "role": "assistant",
                "content": "resp1",
                "message_metadata": None,
            },
            {
                "id": "3",
                "role": "user",
                "content": "oui",
                "message_metadata": {
                    "hitl_response": True,
                    "decision_type": "APPROVE",
                },
            },
            {
                "id": "4",
                "role": "user",
                "content": "non annule",
                "message_metadata": {
                    "hitl_response": True,
                    "decision_type": "REJECT",
                },
            },
            {
                "id": "5",
                "role": "user",
                "content": "non cherche paul",
                "message_metadata": {
                    "hitl_response": True,
                    "decision_type": "EDIT",
                },
            },
            {
                "id": "6",
                "role": "assistant",
                "content": "resp2",
                "message_metadata": None,
            },
        ]

        # Apply filtering (no filtering now)
        filtered = ConversationService._filter_hitl_messages_dict(messages)

        # Calculate total_count (like router does)
        total_user_messages = sum(1 for msg in filtered if msg["role"] == "user")

        # All 4 user messages should be counted (msg1 + APPROVE + REJECT + EDIT)
        assert total_user_messages == 4, "Should count all 4 user messages (no filtering)"
