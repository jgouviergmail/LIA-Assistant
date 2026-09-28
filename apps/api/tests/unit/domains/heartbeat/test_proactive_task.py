"""
Unit tests for domains/heartbeat/proactive_task.py.

Tests the HeartbeatProactiveTask protocol compliance, token capture, and behavior.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
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
            sources_used=["UPCOMING_CALENDAR_EVENTS"],
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
# A skip is billed under the sweep that decided it (ADR-272, ADR-263 amendment 2026-09-27)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestASkipIsBilledUnderItsSweep:
    """The decision to say nothing belongs to the run that read the sources.

    The sweep's consultations and its embeddings were filed under the runner's
    run while the skip's tokens — and its row in the decision register — went
    under a run of their own: the reads pointed at a run that decided nothing,
    and the decision at one that read nothing.
    """

    async def test_the_skip_is_filed_under_the_run_of_the_sweep(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from src.core.context import current_tracker

        tracked = AsyncMock(return_value="run")
        token = current_tracker.set(SimpleNamespace(run_id="proactive_heartbeat_abc_12345678"))  # type: ignore[arg-type]
        try:
            with patch("src.infrastructure.proactive.tracking.track_proactive_tokens", tracked):
                await HeartbeatProactiveTask()._track_skip_tokens(uuid4(), 100, 20, 0, 0)
        finally:
            current_tracker.reset(token)

        assert tracked.await_args.kwargs["run_id"] == "proactive_heartbeat_abc_12345678"

    async def test_outside_a_sweep_the_skip_keeps_a_run_of_its_own(self) -> None:
        from unittest.mock import AsyncMock, patch

        tracked = AsyncMock(return_value="run")
        with patch("src.infrastructure.proactive.tracking.track_proactive_tokens", tracked):
            await HeartbeatProactiveTask()._track_skip_tokens(uuid4(), 100, 20, 0, 0)

        assert tracked.await_args.kwargs["run_id"] is None
