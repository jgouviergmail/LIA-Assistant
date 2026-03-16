"""Unit tests for compaction_node.

Tests:
- Pass-through when compaction disabled
- Pass-through when too few messages
- /resume command detection and consumption
- /resume consumed when compaction unsafe
- Compaction applied: messages removed + summary added
- HITL safety skip

Phase: F4 — Intelligent Context Compaction
Created: 2026-03-16
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage

from src.domains.agents.nodes.compaction_node import (
    _is_resume_command,
    compaction_node,
)
from src.domains.agents.services.compaction_service import (
    CompactionResult,
    SafetyCheckResult,
)

# ============================================================================
# _is_resume_command
# ============================================================================


class TestIsResumeCommand:
    """Tests for /resume command detection."""

    def test_resume_command(self):
        assert _is_resume_command([HumanMessage(content="/resume")]) is True

    def test_resume_with_whitespace(self):
        assert _is_resume_command([HumanMessage(content="  /resume  ")]) is True

    def test_resume_case_insensitive(self):
        assert _is_resume_command([HumanMessage(content="/RESUME")]) is True

    def test_not_resume(self):
        assert _is_resume_command([HumanMessage(content="Hello")]) is False

    def test_empty_messages(self):
        assert _is_resume_command([]) is False

    def test_ai_message_not_resume(self):
        assert _is_resume_command([AIMessage(content="/resume")]) is False


# ============================================================================
# compaction_node
# ============================================================================


class TestCompactionNode:
    """Tests for the compaction_node LangGraph node."""

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    async def test_disabled_passthrough(self, mock_settings):
        """Returns empty dict when compaction is disabled."""
        mock_settings.compaction_enabled = False
        state = {"messages": [HumanMessage(content="Hello", id="h1")]}

        result = await compaction_node(state, config={})
        assert result == {}

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_below_threshold_passthrough(self, mock_svc_cls, mock_settings):
        """Returns empty dict when below threshold."""
        mock_settings.compaction_enabled = True

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = False
        mock_svc_cls.return_value = mock_svc

        state = {"messages": [HumanMessage(content="Hello", id="h1")]}
        result = await compaction_node(state, config={})
        assert result == {}

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_hitl_unsafe_skip(self, mock_svc_cls, mock_settings):
        """Skips compaction when HITL state is pending."""
        mock_settings.compaction_enabled = True
        mock_settings.compaction_preserve_recent_messages = 5

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = True
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(
            safe=False, reason="hitl_pending_draft"
        )
        mock_svc_cls.return_value = mock_svc

        state = {
            "messages": [HumanMessage(content="Hello", id="h1")],
            "pending_draft_critique": {"draft_id": "d1"},
        }
        result = await compaction_node(state, config={})
        assert result == {}

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_resume_forces_compaction(self, mock_svc_cls, mock_settings):
        """The /resume command forces compaction even below threshold."""
        mock_settings.compaction_enabled = True
        mock_settings.compaction_preserve_recent_messages = 2

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = False  # Below threshold
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        mock_svc.compact = AsyncMock(
            return_value=CompactionResult(
                summary="Conversation about contacts.",
                tokens_before=5000,
                tokens_after=500,
                tokens_saved=4500,
                identifiers_preserved=["user@example.com"],
                strategy="single_chunk",
            )
        )
        mock_svc_cls.return_value = mock_svc

        msgs = [
            SystemMessage(content="System", id="s1"),
            HumanMessage(content="Find contact Jean", id="h1"),
            AIMessage(content="Found 3 contacts", id="a1"),
            HumanMessage(content="Show the first", id="h2"),
            AIMessage(content="Here are details", id="a2"),
            HumanMessage(content="/resume", id="h3"),
        ]
        state = {
            "messages": msgs,
            "user_language": "en",
            "compaction_count": 0,
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }

        result = await compaction_node(state, config={})

        # Should have called compact
        mock_svc.compact.assert_called_once()
        assert result["compaction_count"] == 1
        assert "messages" in result

        # /resume message should be removed
        remove_ids = [m.id for m in result["messages"] if isinstance(m, RemoveMessage)]
        assert "h3" in remove_ids

        # Summary as SystemMessage (not routed)
        sys_msgs = [m for m in result["messages"] if isinstance(m, SystemMessage)]
        assert len(sys_msgs) == 1
        assert "conversation about contacts" in sys_msgs[0].content.lower()

        # /resume triggers a conversational HumanMessage for confirmation
        human_msgs = [m for m in result["messages"] if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 1
        assert "compacted" in human_msgs[0].content.lower()

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_resume_consumed_when_unsafe(self, mock_svc_cls, mock_settings):
        """The /resume command is consumed even when compaction is unsafe."""
        mock_settings.compaction_enabled = True

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = False
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(
            safe=False, reason="hitl_pending_draft"
        )
        mock_svc_cls.return_value = mock_svc

        msgs = [HumanMessage(content="/resume", id="h1")]
        state = {
            "messages": msgs,
            "pending_draft_critique": {"draft_id": "d1"},
        }

        result = await compaction_node(state, config={})

        # /resume should be consumed (RemoveMessage + replacement)
        assert "messages" in result
        remove_msgs = [m for m in result["messages"] if isinstance(m, RemoveMessage)]
        assert len(remove_msgs) == 1
        assert remove_msgs[0].id == "h1"

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_compaction_applied(self, mock_svc_cls, mock_settings):
        """Full compaction: old messages removed, summary added."""
        mock_settings.compaction_enabled = True
        mock_settings.compaction_preserve_recent_messages = 2

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = True
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        mock_svc.compact = AsyncMock(
            return_value=CompactionResult(
                summary="User searched contacts and emails.",
                tokens_before=70000,
                tokens_after=500,
                tokens_saved=69500,
                identifiers_preserved=["user@test.com"],
                strategy="single_chunk",
            )
        )
        mock_svc_cls.return_value = mock_svc

        msgs = [
            SystemMessage(content="System", id="s1"),
            HumanMessage(content="msg1", id="h1"),
            AIMessage(content="resp1", id="a1"),
            HumanMessage(content="msg2", id="h2"),
            AIMessage(content="resp2", id="a2"),
            HumanMessage(content="msg3", id="h3"),
            AIMessage(content="resp3", id="a3"),
        ]
        state = {
            "messages": msgs,
            "user_language": "fr",
            "compaction_count": 0,
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }

        result = await compaction_node(state, config={})

        assert result["compaction_count"] == 1
        assert result["compaction_summary"] == "User searched contacts and emails."

        # Old messages (h1, a1, h2, a2) should be removed, recent (h3, a3) kept
        remove_msgs = [m for m in result["messages"] if isinstance(m, RemoveMessage)]
        remove_ids = {m.id for m in remove_msgs}
        assert "h1" in remove_ids
        assert "a1" in remove_ids
        assert "h2" in remove_ids
        assert "a2" in remove_ids
        # Recent messages NOT removed
        assert "h3" not in remove_ids
        assert "a3" not in remove_ids

        # Summary injected as SystemMessage (not HumanMessage — avoids router treating it as query)
        system_msgs = [m for m in result["messages"] if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 1
        assert "compaction #1" in system_msgs[0].content.lower()
        assert "user searched contacts" in system_msgs[0].content.lower()

        # Auto-trigger: no extra HumanMessage added (real user msg is in preserved recent)
        human_msgs = [m for m in result["messages"] if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 0
