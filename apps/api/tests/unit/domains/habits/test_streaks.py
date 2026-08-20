"""Pure streak computation over habit activity days (Lot 1-A4).

The streak is a DISPLAY fact derived from the ledger's local dates — it
never feeds detection thresholds (ADR-214 calibration stays authoritative).
Grace rule: a day without activity YET (today) does not break the streak;
the streak is current when it ends today or yesterday.
"""

from datetime import date, timedelta

import pytest

from src.domains.habits.streaks import compute_streaks

TODAY = date(2026, 8, 19)
MILESTONES = (7, 30, 100)


def _days(*offsets: int) -> set[date]:
    """Days at the given offsets BACK from TODAY (0 = today)."""
    return {TODAY - timedelta(days=offset) for offset in offsets}


@pytest.mark.unit
class TestComputeStreaks:
    def test_empty_ledger_has_no_streaks(self):
        result = compute_streaks(set(), today=TODAY, milestones=MILESTONES)

        assert result.current == 0
        assert result.longest == 0
        assert result.milestone_reached is None
        assert result.next_milestone == 7

    def test_single_active_day_today(self):
        result = compute_streaks(_days(0), today=TODAY, milestones=MILESTONES)

        assert result.current == 1
        assert result.longest == 1

    def test_today_missing_does_not_break_a_streak_ending_yesterday(self):
        result = compute_streaks(_days(1, 2, 3), today=TODAY, milestones=MILESTONES)

        assert result.current == 3

    def test_two_day_gap_means_no_current_streak(self):
        result = compute_streaks(_days(2, 3, 4), today=TODAY, milestones=MILESTONES)

        assert result.current == 0
        assert result.longest == 3

    def test_longest_streak_found_in_history(self):
        # Current run of 2 (today + yesterday); an older run of 5.
        result = compute_streaks(
            _days(0, 1) | _days(10, 11, 12, 13, 14), today=TODAY, milestones=MILESTONES
        )

        assert result.current == 2
        assert result.longest == 5

    def test_milestone_reached_is_the_highest_at_or_below_current(self):
        result = compute_streaks(_days(*range(1, 32)), today=TODAY, milestones=MILESTONES)

        assert result.current == 31
        assert result.milestone_reached == 30
        assert result.next_milestone == 100

    def test_beyond_last_milestone_has_no_next(self):
        result = compute_streaks(_days(*range(0, 120)), today=TODAY, milestones=MILESTONES)

        assert result.milestone_reached == 100
        assert result.next_milestone is None

    def test_future_dates_are_ignored(self):
        # A corrupted or timezone-shifted row must not fabricate a streak.
        days = _days(0, 1) | {TODAY + timedelta(days=3)}

        result = compute_streaks(days, today=TODAY, milestones=MILESTONES)

        assert result.current == 2
        assert result.longest == 2

    def test_unsorted_milestones_are_handled(self):
        result = compute_streaks(_days(0, 1, 2), today=TODAY, milestones=(30, 7, 100))

        assert result.next_milestone == 7


@pytest.mark.unit
class TestOverviewStreakWiring:
    """The overview publishes the streak block computed from the ledger."""

    async def test_service_streaks_come_from_activity_dates(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from uuid import uuid4

        from src.core.config import settings
        from src.domains.habits.service import HabitsService

        dates = [TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
        repo = MagicMock()
        repo.fetch_activity_dates = AsyncMock(return_value=dates)

        with patch("src.domains.habits.service.HabitsRepository", return_value=repo):
            service = HabitsService(MagicMock())
            summary = await service.get_streaks(uuid4(), today=TODAY)

        assert summary.current == 3
        assert summary.longest == 3
        # Milestones come from settings, never hardcoded in the service.
        assert summary.next_milestone == min(settings.habits_streak_milestones)
