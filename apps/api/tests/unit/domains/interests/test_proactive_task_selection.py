"""Tests for select_target mode routing (ADR-131)."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.interests.proactive_task import InterestProactiveTask


def _interest(subject: str | None):
    obj = MagicMock()
    obj.id = uuid.uuid4()
    obj.topic = "some topic"
    obj.category = "technology"
    obj.subject = subject
    return obj


def _notif(interest_id, hours_ago: float):
    n = MagicMock()
    n.interest_id = interest_id
    n.created_at = datetime.now(UTC) - timedelta(hours=hours_ago)
    return n


def _patch_db():
    @asynccontextmanager
    async def _ctx():
        yield MagicMock(name="AsyncSession")

    return patch("src.domains.interests.proactive_task.get_db_context", new=_ctx)


def _settings_mock(mode: str) -> MagicMock:
    s = MagicMock()
    s.interest_selection_mode = mode
    s.interest_top_percent = 1.0
    s.interest_per_topic_cooldown_hours = 12
    s.interest_subject_cooldown_hours = 36
    s.interest_subject_rarity_gamma = 1.0
    s.interest_subject_weight_beta = 0.0
    s.interest_intra_subject_rarity_gamma = 1.0
    s.interest_rarity_lookback_days = 30
    return s


@pytest.mark.unit
class TestSelectTargetRouting:
    async def test_subject_mode_excludes_cooling_subject(self) -> None:
        ai, travel = _interest("ai"), _interest("travel")
        with (
            _patch_db(),
            patch("src.domains.interests.proactive_task.InterestRepository") as repo_cls,
            patch(
                "src.domains.interests.proactive_task.InterestNotificationRepository"
            ) as notif_cls,
            patch(
                "src.domains.interests.proactive_task.settings",
                new=_settings_mock("subject_rarity"),
            ),
        ):
            repo = repo_cls.return_value
            repo.get_top_weighted_interests = AsyncMock(return_value=[(ai, 0.9), (travel, 0.9)])
            repo.get_active_for_user = AsyncMock(return_value=[ai, travel])
            notif_cls.return_value.get_recent_for_user = AsyncMock(
                return_value=[_notif(ai.id, 2.0)]
            )
            task = InterestProactiveTask()
            for _ in range(10):
                selected = await task.select_target(uuid.uuid4())
                assert selected is travel

    async def test_uniform_mode_skips_subject_machinery(self) -> None:
        only = _interest(None)
        with (
            _patch_db(),
            patch("src.domains.interests.proactive_task.InterestRepository") as repo_cls,
            patch(
                "src.domains.interests.proactive_task.InterestNotificationRepository"
            ) as notif_cls,
            patch(
                "src.domains.interests.proactive_task.settings",
                new=_settings_mock("uniform"),
            ),
        ):
            repo_cls.return_value.get_top_weighted_interests = AsyncMock(return_value=[(only, 0.9)])
            task = InterestProactiveTask()
            assert await task.select_target(uuid.uuid4()) is only
            notif_cls.return_value.get_recent_for_user.assert_not_called()

    async def test_subject_mode_returns_none_when_no_candidates(self) -> None:
        with (
            _patch_db(),
            patch("src.domains.interests.proactive_task.InterestRepository") as repo_cls,
            patch(
                "src.domains.interests.proactive_task.settings",
                new=_settings_mock("subject_rarity"),
            ),
        ):
            repo_cls.return_value.get_top_weighted_interests = AsyncMock(return_value=[])
            task = InterestProactiveTask()
            assert await task.select_target(uuid.uuid4()) is None
