"""Unit tests for CompactionService.

Tests:
- compute_effective_threshold (dynamic ratio + absolute override)
- should_compact (fast-path, threshold, disabled)
- is_safe_to_compact (3 HITL safety conditions)
- _extract_identifiers (UUID, URL, email, Google People IDs)
- _split_into_chunks (single, multi, oversized message)
- compact (single chunk, multi chunk, LLM failure fallback)

Phase: F4 — Intelligent Context Compaction
Created: 2026-03-16
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.domains.agents.services.compaction_service import CompactionService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def service():
    """CompactionService with a mocked token counter."""
    svc = CompactionService()
    svc._token_counter = MagicMock()
    svc._token_counter.count_messages_tokens.return_value = 0
    svc._token_counter.count_message_tokens.side_effect = lambda m: 100
    svc._token_counter.count_tokens.side_effect = lambda t: len(t) // 4
    return svc


def _make_messages(n: int, with_system: bool = True) -> list:
    """Create n messages for testing."""
    msgs = []
    if with_system:
        msgs.append(SystemMessage(content="You are a helpful assistant."))
    for i in range(n):
        if i % 2 == 0:
            msgs.append(HumanMessage(content=f"User message {i}", id=f"human_{i}"))
        else:
            msgs.append(AIMessage(content=f"AI response {i}", id=f"ai_{i}"))
    return msgs


# ============================================================================
# compute_effective_threshold
# ============================================================================


class TestComputeEffectiveThreshold:
    """Tests for dynamic threshold computation."""

    @patch("src.domains.agents.services.compaction_service.settings")
    @patch("src.domains.agents.services.compaction_service.get_llm_config_for_agent")
    @patch("src.domains.agents.services.compaction_service.get_model_context_window")
    def test_dynamic_ratio(self, mock_ctx_window, mock_config, mock_settings, service):
        """Threshold = context_window * ratio when no absolute override."""
        mock_settings.compaction_token_threshold = 0
        mock_settings.compaction_threshold_ratio = 0.4
        mock_config.return_value = MagicMock(model="claude-sonnet-4-6")
        mock_ctx_window.return_value = 200_000

        result = service.compute_effective_threshold()
        assert result == 80_000

    @patch("src.domains.agents.services.compaction_service.settings")
    def test_absolute_override(self, mock_settings, service):
        """Absolute threshold takes priority when > 0."""
        mock_settings.compaction_token_threshold = 60_000

        result = service.compute_effective_threshold()
        assert result == 60_000


# ============================================================================
# should_compact
# ============================================================================


class TestShouldCompact:
    """Tests for compaction trigger logic."""

    @patch("src.domains.agents.services.compaction_service.settings")
    def test_disabled(self, mock_settings, service):
        """Returns False when compaction is disabled."""
        mock_settings.compaction_enabled = False
        assert service.should_compact(_make_messages(30)) is False

    @patch("src.domains.agents.services.compaction_service.settings")
    def test_too_few_messages(self, mock_settings, service):
        """Fast-path: skip when fewer messages than min threshold."""
        mock_settings.compaction_enabled = True
        mock_settings.compaction_min_messages = 20
        assert service.should_compact(_make_messages(5)) is False

    @patch("src.domains.agents.services.compaction_service.settings")
    def test_below_threshold(self, mock_settings, service):
        """Returns False when token count is below threshold."""
        mock_settings.compaction_enabled = True
        mock_settings.compaction_min_messages = 5
        mock_settings.compaction_token_threshold = 60_000
        service._token_counter.count_messages_tokens.return_value = 30_000

        assert service.should_compact(_make_messages(25)) is False

    @patch("src.domains.agents.services.compaction_service.settings")
    def test_above_threshold(self, mock_settings, service):
        """Returns True when token count exceeds threshold."""
        mock_settings.compaction_enabled = True
        mock_settings.compaction_min_messages = 5
        mock_settings.compaction_token_threshold = 60_000
        service._token_counter.count_messages_tokens.return_value = 70_000

        assert service.should_compact(_make_messages(25)) is True


# ============================================================================
# is_safe_to_compact
# ============================================================================


class TestIsSafeToCompact:
    """Tests for HITL safety conditions."""

    def test_safe_when_no_hitl(self, service):
        """Safe when no HITL state is pending."""
        state = {
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }
        result = service.is_safe_to_compact(state)
        assert result.safe is True

    def test_unsafe_pending_draft(self, service):
        """Unsafe when draft critique is pending."""
        state = {
            "pending_draft_critique": {"draft_id": "123"},
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
        }
        result = service.is_safe_to_compact(state)
        assert result.safe is False
        assert result.reason == "hitl_pending_draft"

    def test_unsafe_pending_disambiguation(self, service):
        """Unsafe when entity disambiguation is pending."""
        state = {
            "pending_draft_critique": None,
            "pending_entity_disambiguation": {"entity": "Jean"},
            "pending_disambiguations_queue": [],
        }
        result = service.is_safe_to_compact(state)
        assert result.safe is False
        assert result.reason == "hitl_pending_disambiguation"

    def test_unsafe_pending_queue(self, service):
        """Unsafe when disambiguation queue is non-empty."""
        state = {
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [{"entity": "Marie"}],
        }
        result = service.is_safe_to_compact(state)
        assert result.safe is False
        assert result.reason == "hitl_pending_queue"

    def test_unsafe_pending_tool_confirmation(self, service):
        """Unsafe when tool confirmation is pending."""
        state = {
            "pending_draft_critique": None,
            "pending_entity_disambiguation": None,
            "pending_disambiguations_queue": [],
            "pending_tool_confirmation": {"tool": "delete_contact", "args": {}},
        }
        result = service.is_safe_to_compact(state)
        assert result.safe is False
        assert result.reason == "hitl_pending_tool_confirmation"


# ============================================================================
# _extract_identifiers
# ============================================================================


class TestExtractIdentifiers:
    """Tests for identifier extraction from messages."""

    def test_extracts_uuid(self, service):
        """Extracts UUIDs from messages."""
        msgs = [HumanMessage(content="Contact id: 550e8400-e29b-41d4-a716-446655440000")]
        ids = service._extract_identifiers(msgs)
        assert "550e8400-e29b-41d4-a716-446655440000" in ids

    def test_extracts_url(self, service):
        """Extracts URLs from messages."""
        msgs = [AIMessage(content="Found at https://example.com/page?id=42")]
        ids = service._extract_identifiers(msgs)
        assert any("https://example.com" in i for i in ids)

    def test_extracts_email(self, service):
        """Extracts email addresses from messages."""
        msgs = [HumanMessage(content="Send to user@example.com")]
        ids = service._extract_identifiers(msgs)
        assert "user@example.com" in ids

    def test_extracts_google_people_id(self, service):
        """Extracts Google People resource names."""
        msgs = [AIMessage(content="Contact: people/c12345678")]
        ids = service._extract_identifiers(msgs)
        assert "people/c12345678" in ids

    def test_extracts_tool_call_id(self, service):
        """Extracts tool call IDs."""
        msgs = [AIMessage(content="Called tool_call_abc123")]
        ids = service._extract_identifiers(msgs)
        assert "tool_call_abc123" in ids


# ============================================================================
# _split_into_chunks
# ============================================================================


class TestSplitIntoChunks:
    """Tests for message chunking."""

    def test_single_chunk(self, service):
        """All messages fit in one chunk."""
        msgs = _make_messages(5, with_system=False)
        service._token_counter.count_message_tokens.side_effect = lambda m: 100
        chunks = service._split_into_chunks(msgs, max_tokens_per_chunk=1000)
        assert len(chunks) == 1
        assert len(chunks[0]) == 5

    def test_multi_chunk(self, service):
        """Messages split across multiple chunks."""
        msgs = _make_messages(10, with_system=False)
        service._token_counter.count_message_tokens.side_effect = lambda m: 100
        chunks = service._split_into_chunks(msgs, max_tokens_per_chunk=300)
        assert len(chunks) >= 3
        # All messages accounted for
        total = sum(len(c) for c in chunks)
        assert total == 10

    def test_oversized_single_message(self, service):
        """A single message exceeding chunk limit gets its own chunk."""
        msgs = [HumanMessage(content="x" * 50000, id="big")]
        service._token_counter.count_message_tokens.side_effect = lambda m: 25000
        chunks = service._split_into_chunks(msgs, max_tokens_per_chunk=20000)
        assert len(chunks) == 1
        assert len(chunks[0]) == 1


# ============================================================================
# compact
# ============================================================================


class TestCompact:
    """Tests for the main compact() method."""

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.compaction_service.settings")
    @patch("src.domains.agents.services.compaction_service.get_llm")
    @patch("src.domains.agents.services.compaction_service.load_prompt")
    async def test_compact_single_chunk(
        self, mock_load_prompt, mock_get_llm, mock_settings, service
    ):
        """Compact with a single chunk produces a summary."""
        mock_settings.compaction_chunk_max_tokens = 100000
        mock_load_prompt.return_value = "Summarize this."

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = "## Summary\nUser asked about contacts."
        mock_response.usage_metadata = MagicMock(input_tokens=500, output_tokens=100)
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        msgs = _make_messages(20, with_system=True)
        result = await service.compact(msgs, preserve_recent_n=5, language="en")

        assert result.strategy == "single_chunk"
        assert "Summary" in result.summary
        assert result.cost_prompt_tokens == 500
        assert result.cost_completion_tokens == 100

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.compaction_service.settings")
    @patch("src.domains.agents.services.compaction_service.get_llm")
    @patch("src.domains.agents.services.compaction_service.load_prompt")
    async def test_compact_nothing_to_compact(
        self, mock_load_prompt, mock_get_llm, mock_settings, service
    ):
        """Returns noop when preserve_recent_n >= non-system messages."""
        msgs = _make_messages(5, with_system=True)
        result = await service.compact(msgs, preserve_recent_n=10, language="en")

        assert result.strategy == "noop"
        assert result.tokens_saved == 0

    @pytest.mark.asyncio
    @patch("src.domains.agents.services.compaction_service.settings")
    @patch("src.domains.agents.services.compaction_service.get_llm")
    @patch("src.domains.agents.services.compaction_service.load_prompt")
    async def test_compact_llm_failure_fallback(
        self, mock_load_prompt, mock_get_llm, mock_settings, service
    ):
        """Falls back to descriptive note when LLM fails."""
        mock_settings.compaction_chunk_max_tokens = 100000
        mock_load_prompt.return_value = "Summarize this."

        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = Exception("LLM timeout")
        mock_get_llm.return_value = mock_llm

        msgs = _make_messages(20, with_system=True)
        result = await service.compact(msgs, preserve_recent_n=5, language="en")

        assert result.strategy == "descriptive_fallback"
        assert "compacted" in result.summary.lower()
