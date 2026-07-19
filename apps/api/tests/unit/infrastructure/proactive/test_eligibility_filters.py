"""Eligibility filter tests (ADR-135).

Heartbeat ledger rows (`InterestNotification.source == "heartbeat"`) must feed
the interest flow's VARIETY (rarity, subject cooldown) without consuming its
ELIGIBILITY budget (daily quota, global cooldown), and must never self-block
the heartbeat flow through the cross-type burst check.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.interests.models import InterestNotification
from src.infrastructure.proactive.eligibility import EligibilityChecker

HEARTBEAT_LEDGER_FILTER = InterestNotification.source != "heartbeat"


def _user(**kwargs):
    user = MagicMock()
    user.id = "00000000-0000-0000-0000-000000000001"
    user.timezone = "UTC"
    for key, value in kwargs.items():
        setattr(user, key, value)
    return user


def _db_returning(scalar_value):
    db = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = scalar_value
    db.execute.return_value = result
    return db


def _checker(**overrides) -> EligibilityChecker:
    params = {
        "task_type": "interest",
        "enabled_field": "interests_enabled",
        "start_hour_field": "start_h",
        "end_hour_field": "end_h",
        "min_per_day_field": "min_pd",
        "max_per_day_field": "max_pd",
        "notification_model": InterestNotification,
    }
    params.update(overrides)
    return EligibilityChecker(**params)


@pytest.mark.unit
class TestNotificationFilter:
    async def test_daily_quota_query_carries_filter(self) -> None:
        checker = _checker(notification_filter=HEARTBEAT_LEDGER_FILTER)
        db = _db_returning(0)

        await checker._check_daily_quota(_user(max_pd=3), db, datetime.now(UTC))

        compiled = str(db.execute.call_args[0][0])
        assert "source" in compiled

    async def test_daily_quota_unchanged_without_filter(self) -> None:
        checker = _checker()
        db = _db_returning(0)

        await checker._check_daily_quota(_user(max_pd=3), db, datetime.now(UTC))

        compiled = str(db.execute.call_args[0][0])
        assert "source" not in compiled

    async def test_global_cooldown_query_carries_filter(self) -> None:
        checker = _checker(notification_filter=HEARTBEAT_LEDGER_FILTER)
        db = _db_returning(None)

        await checker._check_global_cooldown(_user(), db, datetime.now(UTC))

        compiled = str(db.execute.call_args[0][0])
        assert "source" in compiled

    async def test_global_cooldown_unchanged_without_filter(self) -> None:
        checker = _checker()
        db = _db_returning(None)

        await checker._check_global_cooldown(_user(), db, datetime.now(UTC))

        compiled = str(db.execute.call_args[0][0])
        assert "source" not in compiled


@pytest.mark.unit
class TestCrossTypeFilter:
    async def test_cross_type_filter_applied(self) -> None:
        checker = _checker(
            task_type="heartbeat",
            enabled_field="heartbeat_enabled",
            notification_model=None,
            cross_type_models=[InterestNotification],
            cross_type_filters={InterestNotification: HEARTBEAT_LEDGER_FILTER},
        )
        db = _db_returning(None)

        await checker._check_cross_type_cooldown(_user(), db, datetime.now(UTC))

        compiled = str(db.execute.call_args[0][0])
        assert "source" in compiled

    async def test_cross_type_unchanged_without_filters(self) -> None:
        checker = _checker(
            task_type="heartbeat",
            enabled_field="heartbeat_enabled",
            notification_model=None,
            cross_type_models=[InterestNotification],
        )
        db = _db_returning(None)

        await checker._check_cross_type_cooldown(_user(), db, datetime.now(UTC))

        compiled = str(db.execute.call_args[0][0])
        assert "source" not in compiled


@pytest.mark.unit
class TestDefaultsUnchanged:
    def test_new_params_default_to_none(self) -> None:
        checker = _checker()
        assert checker.notification_filter is None
        assert checker.cross_type_filters == {}
