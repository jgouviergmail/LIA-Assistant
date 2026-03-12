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
    user.last_chat_activity_at = overrides.get("last_activity", None)
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
            min_per_day_field="heartbeat_min_per_day",
            max_per_day_field="heartbeat_max_per_day",
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
