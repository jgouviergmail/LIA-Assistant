"""When a postponed reminder comes back (ADR-268 amendment 2026-11-16).

Pure arithmetic, but on a person's wall clock: « tomorrow morning » is read in
the account's zone, through ``WallTime`` (ADR-380), and proven in zones away
from UTC — including the night the clocks change, where an instant computed
by adding hours to a UTC value lands an hour off.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.core.constants import REMINDER_SNOOZE_NIGHT_END_HOUR
from src.domains.reminders.firings import (
    SnoozeChoice,
    SnoozeDelays,
    collides_with,
    snooze_instant,
)

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
NEW_YORK = ZoneInfo("America/New_York")
DELAYS = SnoozeDelays(short_minutes=10, long_minutes=60, morning_hour=9)


def _paris(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """An instant, written as a Paris wall clock shows it."""
    return datetime(year, month, day, hour, minute, tzinfo=PARIS).astimezone(UTC)


class TestTheTwoDelays:
    def test_short_and_long_are_durations_from_the_press(self) -> None:
        now = _paris(2026, 11, 16, 14, 7)

        assert snooze_instant(SnoozeChoice.SHORT, now=now, zone=PARIS, delays=DELAYS) == now + (
            timedelta(minutes=10)
        )
        assert snooze_instant(SnoozeChoice.LONG, now=now, zone=PARIS, delays=DELAYS) == now + (
            timedelta(minutes=60)
        )

    def test_a_duration_is_elapsed_time_even_across_a_clock_change(self) -> None:
        """« In 1 h » at 02:30 on the night clocks go back is one hour of life."""
        now = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 02:30 CEST, before the change

        later = snooze_instant(SnoozeChoice.LONG, now=now, zone=PARIS, delays=DELAYS)

        assert later - now == timedelta(hours=1)

    def test_the_delays_are_read_from_the_settings(self) -> None:
        delays = SnoozeDelays.from_settings()

        assert delays.short_minutes == settings.reminder_snooze_short_minutes
        assert delays.long_minutes == settings.reminder_snooze_long_minutes
        assert delays.morning_hour == settings.reminder_snooze_morning_hour


class TestTomorrowMorning:
    def test_in_the_afternoon_it_is_the_next_day(self) -> None:
        now = _paris(2026, 11, 16, 15, 40)

        target = snooze_instant(SnoozeChoice.MORNING, now=now, zone=PARIS, delays=DELAYS)

        assert target == _paris(2026, 11, 17, 9)

    def test_after_midnight_it_is_the_morning_that_comes(self) -> None:
        """Pressed at 01:00, « tomorrow morning » is the end of THIS night."""
        now = _paris(2026, 11, 17, 1, 0)

        target = snooze_instant(SnoozeChoice.MORNING, now=now, zone=PARIS, delays=DELAYS)

        assert target == _paris(2026, 11, 17, 9)

    def test_the_night_ends_at_its_declared_hour(self) -> None:
        last_minute = _paris(2026, 11, 17, REMINDER_SNOOZE_NIGHT_END_HOUR - 1, 59)
        first_minute = _paris(2026, 11, 17, REMINDER_SNOOZE_NIGHT_END_HOUR, 0)

        assert snooze_instant(
            SnoozeChoice.MORNING, now=last_minute, zone=PARIS, delays=DELAYS
        ) == _paris(2026, 11, 17, 9)
        assert snooze_instant(
            SnoozeChoice.MORNING, now=first_minute, zone=PARIS, delays=DELAYS
        ) == _paris(2026, 11, 18, 9)

    def test_a_morning_already_behind_the_press_is_the_next_one(self) -> None:
        """A configured morning before the night's end never lands in the past."""
        early = SnoozeDelays(short_minutes=10, long_minutes=60, morning_hour=4)
        now = _paris(2026, 11, 17, 4, 30)

        target = snooze_instant(SnoozeChoice.MORNING, now=now, zone=PARIS, delays=early)

        assert target == _paris(2026, 11, 18, 4)

    def test_it_is_read_on_the_accounts_wall_not_in_utc(self) -> None:
        """23:30 in New York is already the next day in UTC: the wall decides."""
        now = datetime(2026, 11, 16, 23, 30, tzinfo=NEW_YORK).astimezone(UTC)

        target = snooze_instant(SnoozeChoice.MORNING, now=now, zone=NEW_YORK, delays=DELAYS)

        assert target == datetime(2026, 11, 17, 9, 0, tzinfo=NEW_YORK).astimezone(UTC)
        assert target.hour == 14  # 09:00 EST is 14:00 UTC

    def test_the_morning_after_the_clocks_go_forward_keeps_its_wall_clock(self) -> None:
        """Nine o'clock the day summer time starts is 07:00 UTC, not 08:00."""
        now = _paris(2026, 3, 28, 22, 0)

        target = snooze_instant(SnoozeChoice.MORNING, now=now, zone=PARIS, delays=DELAYS)

        assert target == datetime(2026, 3, 29, 7, 0, tzinfo=UTC)

    def test_every_choice_lands_after_the_press(self) -> None:
        now = _paris(2026, 11, 16, 8, 59)
        for choice in SnoozeChoice:
            assert snooze_instant(choice, now=now, zone=PARIS, delays=DELAYS) > now


class TestASeriesAlreadyComingBack:
    def test_a_postponement_reaching_the_next_occurrence_collides(self) -> None:
        upcoming = _paris(2026, 11, 17, 9)

        assert collides_with(_paris(2026, 11, 17, 9), upcoming)
        assert collides_with(_paris(2026, 11, 17, 10), upcoming)

    def test_one_landing_before_it_does_not(self) -> None:
        assert not collides_with(_paris(2026, 11, 17, 8, 59), _paris(2026, 11, 17, 9))

    def test_nothing_coming_back_never_collides(self) -> None:
        assert not collides_with(_paris(2026, 11, 17, 9), None)
