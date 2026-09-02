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

    # ========================================================================
    # Task 1.5 — Removal of prior "compaction #N" SystemMessages
    # ========================================================================

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_prior_summaries_removed_only_when_consolidated(
        self, mock_svc_cls, mock_settings
    ):
        """Prior 'compaction #N' SystemMessages are removed iff result.consolidated_previous_summaries=True."""
        mock_settings.compaction_enabled = True
        mock_settings.compaction_preserve_recent_messages = 2
        mock_settings.compaction_include_previous_summaries = True

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = True
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        mock_svc.compact = AsyncMock(
            return_value=CompactionResult(
                summary="Consolidated everything.",
                tokens_before=80000,
                tokens_after=500,
                tokens_saved=79500,
                identifiers_preserved=[],
                strategy="multi_chunk",
                consolidated_previous_summaries=True,
            )
        )
        mock_svc_cls.return_value = mock_svc

        prior1 = SystemMessage(
            content="[Conversation history compacted — compaction #1.]\n\nOld summary 1",
            id="prior-1",
        )
        prior2 = SystemMessage(
            content="[Conversation history compacted — compaction #2.]\n\nOld summary 2",
            id="prior-2",
        )
        msgs = [
            prior1,
            prior2,
            HumanMessage(content="msg1", id="h1"),
            HumanMessage(content="msg2", id="h2"),
            HumanMessage(content="msg3", id="h3"),
        ]
        state = {
            "messages": msgs,
            "user_language": "fr",
            "compaction_count": 2,
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }

        result = await compaction_node(state, config={})
        remove_ids = {m.id for m in result["messages"] if isinstance(m, RemoveMessage)}
        assert "prior-1" in remove_ids
        assert "prior-2" in remove_ids

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_prior_summaries_preserved_on_truncation_fallback(
        self, mock_svc_cls, mock_settings
    ):
        """When the service falls back to truncation, prior summaries stay in state.

        This is the regression guard for Task 1.5: even though previous compaction
        summaries are now eligible to be consolidated, the node must NEVER emit
        RemoveMessage for them when the fallback path runs — otherwise we lose
        information v1 preserved.
        """
        mock_settings.compaction_enabled = True
        mock_settings.compaction_preserve_recent_messages = 2
        mock_settings.compaction_include_previous_summaries = True

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = True
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        mock_svc.compact = AsyncMock(
            return_value=CompactionResult(
                summary="[Older conversation truncated — 3 messages removed because the automatic summary could not complete (global_timeout). Key identifiers preserved: ]",
                tokens_before=80000,
                tokens_after=300,
                tokens_saved=79700,
                identifiers_preserved=[],
                strategy="truncation",
                consolidated_previous_summaries=False,
            )
        )
        mock_svc_cls.return_value = mock_svc

        prior1 = SystemMessage(
            content="[Conversation history compacted — compaction #1.]\n\nOld summary 1",
            id="prior-1",
        )
        msgs = [
            prior1,
            HumanMessage(content="msg1", id="h1"),
            HumanMessage(content="msg2", id="h2"),
            HumanMessage(content="msg3", id="h3"),
        ]
        state = {
            "messages": msgs,
            "user_language": "fr",
            "compaction_count": 1,
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }

        result = await compaction_node(state, config={})
        remove_ids = {m.id for m in result["messages"] if isinstance(m, RemoveMessage)}
        # The prior summary must NOT be removed — v1's preserved context stays.
        assert "prior-1" not in remove_ids

    # ========================================================================
    # Task 2.2 — SSE events emitted via get_stream_writer
    # ========================================================================

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.get_stream_writer")
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_emits_compaction_start_and_done_on_success(
        self, mock_svc_cls, mock_settings, mock_get_writer
    ):
        """When compaction runs successfully, exactly one compaction_start and one
        compaction_done event are emitted via the LangGraph stream writer."""
        mock_settings.compaction_enabled = True
        mock_settings.compaction_preserve_recent_messages = 2
        mock_settings.compaction_include_previous_summaries = True

        captured: list[dict] = []
        mock_writer = MagicMock(side_effect=captured.append)
        mock_get_writer.return_value = mock_writer

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = True
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        mock_svc.compact = AsyncMock(
            return_value=CompactionResult(
                summary="Recap",
                tokens_before=50000,
                tokens_after=400,
                tokens_saved=49600,
                identifiers_preserved=[],
                strategy="single_chunk",
            )
        )
        mock_svc_cls.return_value = mock_svc

        msgs = [
            HumanMessage(content="msg1", id="h1"),
            HumanMessage(content="msg2", id="h2"),
            HumanMessage(content="msg3", id="h3"),
        ]
        state = {
            "messages": msgs,
            "user_language": "fr",
            "compaction_count": 0,
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }

        await compaction_node(state, config={})

        labels = [c.get("step_label") for c in captured]
        assert labels == ["compaction_start", "compaction_done"]
        assert captured[0]["step_type"] == "compaction"
        assert captured[0]["metadata"]["phase"] == "start"
        assert "estimated_duration_seconds" in captured[0]["metadata"]
        assert captured[1]["metadata"]["phase"] == "done"
        assert captured[1]["metadata"]["strategy"] == "single_chunk"
        assert captured[1]["metadata"]["tokens_saved"] == 49600
        assert captured[1]["metadata"]["duration_ms"] >= 0

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.get_stream_writer")
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_emits_compaction_done_with_truncation_strategy(
        self, mock_svc_cls, mock_settings, mock_get_writer
    ):
        """On truncation fallback, compaction_done carries strategy='truncation'.

        The frontend uses this to show the "older conversation truncated" banner
        instead of the regular "summary in progress" one.
        """
        mock_settings.compaction_enabled = True
        mock_settings.compaction_preserve_recent_messages = 2
        mock_settings.compaction_include_previous_summaries = True

        captured: list[dict] = []
        mock_writer = MagicMock(side_effect=captured.append)
        mock_get_writer.return_value = mock_writer

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = True
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        mock_svc.compact = AsyncMock(
            return_value=CompactionResult(
                summary="[Older conversation truncated — 3 messages removed because the automatic summary could not complete (global_timeout). Key identifiers preserved: ]",
                tokens_before=80000,
                tokens_after=300,
                tokens_saved=79700,
                identifiers_preserved=[],
                strategy="truncation",
                consolidated_previous_summaries=False,
            )
        )
        mock_svc_cls.return_value = mock_svc

        msgs = [
            HumanMessage(content="m1", id="h1"),
            HumanMessage(content="m2", id="h2"),
            HumanMessage(content="m3", id="h3"),
        ]
        state = {
            "messages": msgs,
            "user_language": "fr",
            "compaction_count": 0,
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }

        await compaction_node(state, config={})

        done_events = [c for c in captured if c.get("step_label") == "compaction_done"]
        assert len(done_events) == 1
        assert done_events[0]["metadata"]["strategy"] == "truncation"


# ============================================================================
# Lot B (2026-09) — Provenance banner placement in the summary SystemMessage
# ============================================================================


class TestProvenanceBanner:
    """The summary inherits the external-content taint, AFTER the marker."""

    @staticmethod
    def _state_and_service(mock_svc_cls, mock_settings, *, tainted: bool):
        from src.core.constants import COMPACTION_SUMMARY_MARKER  # noqa: F401

        mock_settings.compaction_enabled = True
        mock_settings.compaction_preserve_recent_messages = 2
        mock_settings.compaction_include_previous_summaries = True

        mock_svc = MagicMock()
        mock_svc.should_compact.return_value = True
        mock_svc.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        mock_svc.compact = AsyncMock(
            return_value=CompactionResult(
                summary="- summary body",
                tokens_before=70000,
                tokens_after=500,
                tokens_saved=69500,
                identifiers_preserved=[],
                strategy="single_chunk",
                contains_external_content=tainted,
            )
        )
        mock_svc_cls.return_value = mock_svc

        msgs = [
            HumanMessage(content="m1", id="h1"),
            AIMessage(content="r1", id="a1"),
            HumanMessage(content="m2", id="h2"),
            AIMessage(content="r2", id="a2"),
        ]
        return {
            "messages": msgs,
            "user_language": "fr",
            "compaction_count": 0,
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_tainted_summary_carries_banner_after_marker(self, mock_svc_cls, mock_settings):
        from src.core.constants import (
            COMPACTION_EXTERNAL_PROVENANCE_BANNER,
            COMPACTION_SUMMARY_MARKER,
        )

        state = self._state_and_service(mock_svc_cls, mock_settings, tainted=True)
        result = await compaction_node(state, config={})

        summary_msgs = [m for m in result["messages"] if isinstance(m, SystemMessage)]
        assert len(summary_msgs) == 1
        content = summary_msgs[0].content
        # The marker MUST stay the prefix: two readers rely on startswith().
        assert content.startswith(COMPACTION_SUMMARY_MARKER)
        assert COMPACTION_EXTERNAL_PROVENANCE_BANNER in content
        # Banner sits between header and body, never before the marker.
        assert content.index(COMPACTION_EXTERNAL_PROVENANCE_BANNER) < content.index(
            "- summary body"
        )

    @pytest.mark.asyncio
    @patch("src.domains.agents.nodes.compaction_node.settings")
    @patch("src.domains.agents.nodes.compaction_node.CompactionService")
    async def test_clean_summary_has_no_banner(self, mock_svc_cls, mock_settings):
        from src.core.constants import (
            COMPACTION_EXTERNAL_PROVENANCE_BANNER,
            COMPACTION_SUMMARY_MARKER,
        )

        state = self._state_and_service(mock_svc_cls, mock_settings, tainted=False)
        result = await compaction_node(state, config={})

        summary_msgs = [m for m in result["messages"] if isinstance(m, SystemMessage)]
        assert len(summary_msgs) == 1
        assert summary_msgs[0].content.startswith(COMPACTION_SUMMARY_MARKER)
        assert COMPACTION_EXTERNAL_PROVENANCE_BANNER not in summary_msgs[0].content
