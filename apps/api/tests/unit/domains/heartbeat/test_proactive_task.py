"""
Unit tests for domains/heartbeat/proactive_task.py.

Tests the HeartbeatProactiveTask protocol compliance, token capture, and behavior.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from langchain_core.outputs import ChatGeneration, LLMResult

from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
from src.domains.heartbeat.prompts import _TokenCaptureHandler
from src.domains.heartbeat.schemas import (
    HeartbeatContext,
    HeartbeatDecision,
    HeartbeatTarget,
)
from src.infrastructure.proactive.base import ContentSource

# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatProactiveTaskProtocol:
    """Tests for Protocol compliance and basic behavior."""

    def test_task_type(self):
        """Test that task_type is correctly set."""
        task = HeartbeatProactiveTask()
        assert task.task_type == "heartbeat"

    def test_has_required_methods(self):
        """Test that all ProactiveTask Protocol methods exist."""
        task = HeartbeatProactiveTask()

        assert callable(task.check_eligibility)
        assert callable(task.select_target)
        assert callable(task.generate_content)
        assert callable(task.on_feedback)
        assert callable(task.on_notification_sent)


# ---------------------------------------------------------------------------
# check_eligibility
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckEligibility:
    """Tests for check_eligibility method."""

    @pytest.mark.asyncio
    async def test_eligible_when_heartbeat_enabled(self):
        """Test user is eligible when heartbeat_enabled is True."""
        task = HeartbeatProactiveTask()
        user_settings = {"heartbeat_enabled": True}

        result = await task.check_eligibility(
            user_id=uuid4(), user_settings=user_settings, now=datetime.now(UTC)
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_not_eligible_when_heartbeat_disabled(self):
        """Test user is not eligible when heartbeat_enabled is False."""
        task = HeartbeatProactiveTask()
        user_settings = {"heartbeat_enabled": False}

        result = await task.check_eligibility(
            user_id=uuid4(), user_settings=user_settings, now=datetime.now(UTC)
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_not_eligible_when_heartbeat_missing(self):
        """Test user is not eligible when heartbeat_enabled key is missing."""
        task = HeartbeatProactiveTask()
        user_settings = {}

        result = await task.check_eligibility(
            user_id=uuid4(), user_settings=user_settings, now=datetime.now(UTC)
        )

        assert result is False


# ---------------------------------------------------------------------------
# HeartbeatTarget construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHeartbeatTargetConstruction:
    """Tests for HeartbeatTarget construction and token aggregation."""

    def test_target_carries_context_and_decision(self):
        """Test that target carries both context and decision."""
        context = HeartbeatContext(
            calendar_events=[{"summary": "Meeting"}],
            available_sources=["calendar"],
        )
        decision = HeartbeatDecision(
            action="notify",
            reason="Upcoming meeting",
            message_draft="You have a meeting soon.",
            sources_used=["calendar"],
        )
        target = HeartbeatTarget(
            context=context,
            decision=decision,
            decision_tokens_in=150,
            decision_tokens_out=75,
            decision_tokens_cache=10,
        )

        assert target.context is context
        assert target.decision is decision
        assert target.decision_tokens_in == 150
        assert target.decision_tokens_out == 75
        assert target.decision_tokens_cache == 10

    def test_token_defaults(self):
        """Test default token values are zero."""
        context = HeartbeatContext()
        decision = HeartbeatDecision(action="skip", reason="test")
        target = HeartbeatTarget(context=context, decision=decision)

        assert target.decision_tokens_in == 0
        assert target.decision_tokens_out == 0
        assert target.decision_tokens_cache == 0


# ---------------------------------------------------------------------------
# ContentSource integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContentSourceIntegration:
    """Tests for ContentSource enum integration."""

    def test_heartbeat_content_source_exists(self):
        """Test that HEARTBEAT is a valid ContentSource."""
        assert hasattr(ContentSource, "HEARTBEAT")
        assert ContentSource.HEARTBEAT == "heartbeat"

    def test_heartbeat_content_source_value(self):
        """Test that ContentSource.HEARTBEAT matches task_type."""
        task = HeartbeatProactiveTask()
        assert ContentSource.HEARTBEAT.value == task.task_type


# ---------------------------------------------------------------------------
# _TokenCaptureHandler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTokenCaptureHandler:
    """Tests for _TokenCaptureHandler callback."""

    def test_initial_state_zero(self):
        """Test that handler starts with zero tokens."""
        handler = _TokenCaptureHandler()
        assert handler.tokens_in == 0
        assert handler.tokens_out == 0
        assert handler.tokens_cache == 0

    def test_captures_tokens_from_usage_metadata(self):
        """Test that on_llm_end extracts tokens from AIMessage usage_metadata."""
        handler = _TokenCaptureHandler()

        # Build a mock LLMResult with ChatGeneration containing usage_metadata
        mock_message = MagicMock()
        mock_message.usage_metadata = {
            "input_tokens": 500,
            "output_tokens": 120,
            "cache_read_input_tokens": 50,
        }
        mock_gen = MagicMock(spec=ChatGeneration)
        mock_gen.message = mock_message

        result = LLMResult(generations=[[mock_gen]])
        handler.on_llm_end(result)

        assert handler.tokens_in == 500
        assert handler.tokens_out == 120
        assert handler.tokens_cache == 50

    def test_accumulates_across_multiple_calls(self):
        """Test that tokens accumulate across multiple on_llm_end calls."""
        handler = _TokenCaptureHandler()

        for _ in range(3):
            mock_message = MagicMock()
            mock_message.usage_metadata = {
                "input_tokens": 100,
                "output_tokens": 30,
                "cache_read_input_tokens": 10,
            }
            mock_gen = MagicMock(spec=ChatGeneration)
            mock_gen.message = mock_message
            result = LLMResult(generations=[[mock_gen]])
            handler.on_llm_end(result)

        assert handler.tokens_in == 300
        assert handler.tokens_out == 90
        assert handler.tokens_cache == 30

    def test_handles_missing_usage_metadata_gracefully(self):
        """Test that handler doesn't crash when usage_metadata is None."""
        handler = _TokenCaptureHandler()

        mock_message = MagicMock()
        mock_message.usage_metadata = None
        mock_gen = MagicMock(spec=ChatGeneration)
        mock_gen.message = mock_message

        result = LLMResult(generations=[[mock_gen]])
        handler.on_llm_end(result)

        assert handler.tokens_in == 0
        assert handler.tokens_out == 0
        assert handler.tokens_cache == 0

    def test_handles_missing_message_gracefully(self):
        """Test that handler doesn't crash when generation has no message."""
        handler = _TokenCaptureHandler()

        mock_gen = MagicMock(spec=ChatGeneration)
        # Simulate missing message attribute
        del mock_gen.message

        result = LLMResult(generations=[[mock_gen]])
        handler.on_llm_end(result)

        assert handler.tokens_in == 0

    def test_handles_empty_generations(self):
        """Test that handler handles empty generations list."""
        handler = _TokenCaptureHandler()

        result = LLMResult(generations=[])
        handler.on_llm_end(result)

        assert handler.tokens_in == 0


# ---------------------------------------------------------------------------
# _track_skip_tokens
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTrackSkipTokens:
    """Tests for HeartbeatProactiveTask._track_skip_tokens()."""

    def test_method_exists(self):
        """Test that _track_skip_tokens method exists."""
        task = HeartbeatProactiveTask()
        assert callable(task._track_skip_tokens)

    @pytest.mark.asyncio
    async def test_skips_when_no_tokens(self):
        """Test that tracking is skipped when tokens are zero."""
        task = HeartbeatProactiveTask()
        # Should not raise — early return when tokens_in=0 and tokens_out=0
        await task._track_skip_tokens(
            user_id=uuid4(),
            tokens_in=0,
            tokens_out=0,
            tokens_cache=0,
        )
