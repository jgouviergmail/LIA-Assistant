"""
Unit tests for infrastructure/proactive/eligibility.py.

Tests the EligibilityChecker cross-type cooldown logic.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.interests.models import InterestNotification
from src.infrastructure.proactive.eligibility import (
    EligibilityChecker,
    EligibilityReason,
)


def _make_user(**overrides: Any) -> MagicMock:
    """Create a mock User with default attributes."""
    user = MagicMock()
    user.id = overrides.get("id", uuid4())
    user.interests_enabled = overrides.get("interests_enabled", True)
    user.interests_notify_start_hour = overrides.get("start_hour", 8)
    user.interests_notify_end_hour = overrides.get("end_hour", 22)
    user.interests_notify_min_per_day = overrides.get("min_per_day", 1)
    user.interests_notify_max_per_day = overrides.get("max_per_day", 5)
    user.timezone = overrides.get("timezone", "UTC")
    return user


@pytest.mark.unit
class TestCrossTypeCooldown:
    """Tests for _check_cross_type_cooldown()."""

    @pytest.fixture
    def checker_with_cross_type(self) -> EligibilityChecker:
        """EligibilityChecker (heartbeat) with cross-type cooldown from interests."""
        return EligibilityChecker(
            task_type="heartbeat",
            enabled_field="interests_enabled",
            start_hour_field="interests_notify_start_hour",
            end_hour_field="interests_notify_end_hour",
            min_per_day_field="interests_notify_min_per_day",
            max_per_day_field="interests_notify_max_per_day",
            # Use real model so SQLAlchemy select() works on model.created_at
            cross_type_models=[InterestNotification],
            cross_type_cooldown_minutes=30,
        )

    @pytest.fixture
    def checker_no_cross_type(self) -> EligibilityChecker:
        """EligibilityChecker without cross-type cooldown."""
        return EligibilityChecker(
            task_type="heartbeat",
            enabled_field="interests_enabled",
            start_hour_field="interests_notify_start_hour",
            end_hour_field="interests_notify_end_hour",
            min_per_day_field="interests_notify_min_per_day",
            max_per_day_field="interests_notify_max_per_day",
        )

    @pytest.mark.asyncio
    async def test_no_cross_type_models_passes(
        self, checker_no_cross_type: EligibilityChecker
    ) -> None:
        """When no cross_type_models configured, check always passes."""
        user = _make_user()
        db = AsyncMock()
        now = datetime.now(UTC)

        result = await checker_no_cross_type._check_cross_type_cooldown(user, db, now)
        assert result.eligible

    @pytest.mark.asyncio
    async def test_no_recent_cross_notification_passes(
        self, checker_with_cross_type: EligibilityChecker
    ) -> None:
        """When no recent cross-type notification exists, check passes."""
        user = _make_user()
        db = AsyncMock()
        now = datetime.now(UTC)

        # Mock DB: no results
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await checker_with_cross_type._check_cross_type_cooldown(user, db, now)
        assert result.eligible

    @pytest.mark.asyncio
    async def test_recent_cross_notification_blocks(
        self, checker_with_cross_type: EligibilityChecker
    ) -> None:
        """When a recent cross-type notification exists within cooldown, check fails."""
        user = _make_user()
        db = AsyncMock()
        now = datetime.now(UTC)

        # Mock DB: notification 10 minutes ago (within 30 min cooldown)
        recent_time = now - timedelta(minutes=10)
        mock_result = MagicMock()
        mock_result.scalar.return_value = recent_time
        db.execute = AsyncMock(return_value=mock_result)

        result = await checker_with_cross_type._check_cross_type_cooldown(user, db, now)
        assert not result.eligible
        assert result.reason == EligibilityReason.CROSS_TYPE_COOLDOWN
        assert result.details is not None
        assert result.details["cooldown_minutes"] == 30
        assert result.details["cross_model"] == "interest_notifications"

    @pytest.mark.asyncio
    async def test_old_cross_notification_passes(
        self, checker_with_cross_type: EligibilityChecker
    ) -> None:
        """When cross-type notification is older than cooldown, check passes."""
        user = _make_user()
        db = AsyncMock()
        now = datetime.now(UTC)

        # Mock DB: no result (the WHERE clause filters out old notifications)
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await checker_with_cross_type._check_cross_type_cooldown(user, db, now)
        assert result.eligible

    def test_cross_type_cooldown_reason_exists(self) -> None:
        """Verify CROSS_TYPE_COOLDOWN is a valid EligibilityReason."""
        assert hasattr(EligibilityReason, "CROSS_TYPE_COOLDOWN")
        assert EligibilityReason.CROSS_TYPE_COOLDOWN.value == "cross_type_cooldown"

    def test_default_cross_type_models_empty(self) -> None:
        """Default cross_type_models should be empty list."""
        checker = EligibilityChecker(
            task_type="test",
            enabled_field="test_enabled",
            start_hour_field="test_start",
            end_hour_field="test_end",
            min_per_day_field="test_min",
            max_per_day_field="test_max",
        )
        assert checker.cross_type_models == []
        assert checker.cross_type_cooldown_minutes == 30

    def test_symmetric_configuration(self) -> None:
        """Verify both task types can reference each other's models."""
        heartbeat_checker = EligibilityChecker(
            task_type="heartbeat",
            enabled_field="heartbeat_enabled",
            start_hour_field="heartbeat_notify_start_hour",
            end_hour_field="heartbeat_notify_end_hour",
            notification_model=HeartbeatNotification,
            cross_type_models=[InterestNotification],
            cross_type_cooldown_minutes=30,
        )
        interest_checker = EligibilityChecker(
            task_type="interest",
            enabled_field="interests_enabled",
            start_hour_field="interests_notify_start_hour",
            end_hour_field="interests_notify_end_hour",
            min_per_day_field="interests_notify_min_per_day",
            max_per_day_field="interests_notify_max_per_day",
            notification_model=InterestNotification,
            cross_type_models=[HeartbeatNotification],
            cross_type_cooldown_minutes=30,
        )
        # Both checkers have the other's model as cross-type
        assert heartbeat_checker.cross_type_models == [InterestNotification]
        assert interest_checker.cross_type_models == [HeartbeatNotification]


def _session_counting(today: int) -> AsyncMock:
    """A session answering every daily COUNT with ``today`` and nothing else.

    The cooldown lookups find no earlier notification, so the only thing that
    can refuse is the day's count — which is exactly what is under test.
    """

    async def execute(statement: Any) -> MagicMock:
        result = MagicMock()
        result.scalar.return_value = today if _is_count(statement) else None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute)
    return db


def _is_count(statement: Any) -> bool:
    return "count(" in str(statement).lower()


def _counted(db: AsyncMock) -> bool:
    return any(_is_count(call.args[0]) for call in db.execute.await_args_list)


def _unbounded(**kwargs: Any) -> EligibilityChecker:
    return EligibilityChecker(
        task_type="heartbeat",
        enabled_field="interests_enabled",
        start_hour_field="interests_notify_start_hour",
        end_hour_field="interests_notify_end_hour",
        notification_model=HeartbeatNotification,
        **kwargs,
    )


@pytest.mark.unit
class TestADailyBoundIsOptional:
    """ADR-328: the heartbeat has no daily bound — the decision is the model's.

    A checker given no per-day fields neither refuses past a count nor counts
    the day at all; one given both keeps refusing at its maximum (interests).
    """

    async def test_without_bounds_the_day_is_never_counted(self) -> None:
        db = _session_counting(today=50)
        user = _make_user(start_hour=0, end_hour=24)

        result = await _unbounded().check(user, db, datetime.now(UTC))

        assert result.eligible
        assert not _counted(db)

    async def test_with_bounds_the_same_day_is_refused(self) -> None:
        db = _session_counting(today=50)
        user = _make_user(start_hour=0, end_hour=24, max_per_day=8)
        checker = _unbounded(
            min_per_day_field="interests_notify_min_per_day",
            max_per_day_field="interests_notify_max_per_day",
        )

        result = await checker.check(user, db, datetime.now(UTC))

        assert result.reason == EligibilityReason.QUOTA_EXCEEDED

    def test_bounds_are_both_given_or_neither(self) -> None:
        assert not _unbounded().has_daily_bounds
        assert _unbounded(
            min_per_day_field="interests_notify_min_per_day",
            max_per_day_field="interests_notify_max_per_day",
        ).has_daily_bounds
        with pytest.raises(ValueError, match="both"):
            _unbounded(max_per_day_field="interests_notify_max_per_day")

    def test_the_heartbeat_scheduler_bounds_no_day(self) -> None:
        """Ticks, push wakes and anticipated moments share this checker."""
        from src.infrastructure.scheduler.heartbeat_notification import (
            _create_heartbeat_eligibility_checker,
        )

        checker = _create_heartbeat_eligibility_checker()

        assert not checker.has_daily_bounds
        # Every other gate stays: the window, the cooldowns, the activity probe.
        assert checker.notification_model is HeartbeatNotification
        assert checker.cross_type_models == [InterestNotification]
        assert checker.activity_probe is not None
