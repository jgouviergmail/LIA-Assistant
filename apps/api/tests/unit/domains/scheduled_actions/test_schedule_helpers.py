"""
Unit tests for schedule_helpers.

Tests compute_next_trigger_utc, validate_days_of_week, format_schedule_display.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.domains.scheduled_actions.schedule_helpers import (
    _cron,
    compute_next_trigger_after_execution,
    compute_next_trigger_utc,
    compute_next_triggers_utc,
    format_schedule_display,
    local_day_slot,
    served_slot,
    validate_days_of_week,
    week_slots,
    week_start,
)


class TestComputeNextTriggerUtc:
    """Tests for compute_next_trigger_utc."""

    def test_basic_next_trigger(self) -> None:
        """Should return a future UTC datetime."""
        result = compute_next_trigger_utc(
            days_of_week=[1, 3, 5],  # Mon, Wed, Fri
            hour=19,
            minute=30,
            user_timezone="Europe/Paris",
        )
        assert result is not None
        assert result.tzinfo is not None
        assert result > datetime.now(UTC)

    def test_every_day(self) -> None:
        """Should handle all 7 days."""
        result = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            hour=8,
            minute=0,
            user_timezone="Europe/Paris",
        )
        assert result is not None

    def test_single_day(self) -> None:
        """Should handle a single day."""
        result = compute_next_trigger_utc(
            days_of_week=[6],  # Saturday only
            hour=10,
            minute=0,
            user_timezone="America/New_York",
        )
        assert result is not None
        # Should land on a Saturday
        local_result = result.astimezone(ZoneInfo("America/New_York"))
        assert local_result.isoweekday() == 6

    def test_different_timezone(self) -> None:
        """Different timezones should produce different UTC times for the same local time."""
        paris = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            hour=12,
            minute=0,
            user_timezone="Europe/Paris",
        )
        tokyo = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            hour=12,
            minute=0,
            user_timezone="Asia/Tokyo",
        )
        # Same local time but different UTC offsets
        assert paris != tokyo

    def test_with_reference_after(self) -> None:
        """Should compute next trigger after the given reference time."""
        reference = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)  # Monday noon UTC
        result = compute_next_trigger_utc(
            days_of_week=[1],  # Monday
            hour=19,
            minute=30,
            user_timezone="Europe/Paris",
            after=reference,
        )
        assert result > reference

    def test_midnight_boundary(self) -> None:
        """Should handle midnight correctly."""
        result = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5],
            hour=0,
            minute=0,
            user_timezone="Europe/Paris",
        )
        assert result is not None

    def test_end_of_day(self) -> None:
        """Should handle 23:59 correctly."""
        result = compute_next_trigger_utc(
            days_of_week=[1],
            hour=23,
            minute=59,
            user_timezone="Europe/Paris",
        )
        assert result is not None

    def test_returns_utc_timezone(self) -> None:
        """Must return datetime in UTC, not in user timezone."""
        result = compute_next_trigger_utc(
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            hour=12,
            minute=0,
            user_timezone="Europe/Paris",
        )
        # Verify the tzinfo is UTC, not Europe/Paris
        assert result.tzinfo == UTC

    def test_utc_offset_is_correct(self) -> None:
        """19:30 Paris (CET, UTC+1) should be stored as 18:30 UTC in winter."""
        # Use a known Monday in January (winter, CET = UTC+1)
        reference = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)  # Monday 10:00 UTC
        result = compute_next_trigger_utc(
            days_of_week=[1],  # Monday
            hour=19,
            minute=30,
            user_timezone="Europe/Paris",
            after=reference,
        )
        # 19:30 Paris = 18:30 UTC (CET is UTC+1 in winter)
        assert result.hour == 18
        assert result.minute == 30
        assert result.tzinfo == UTC


class TestValidateDaysOfWeek:
    """Tests for validate_days_of_week."""

    def test_valid_single_day(self) -> None:
        assert validate_days_of_week([1]) is True

    def test_valid_all_days(self) -> None:
        assert validate_days_of_week([1, 2, 3, 4, 5, 6, 7]) is True

    def test_valid_weekdays(self) -> None:
        assert validate_days_of_week([1, 2, 3, 4, 5]) is True

    def test_empty_list(self) -> None:
        assert validate_days_of_week([]) is False

    def test_invalid_day_zero(self) -> None:
        assert validate_days_of_week([0]) is False

    def test_invalid_day_eight(self) -> None:
        assert validate_days_of_week([8]) is False

    def test_duplicates(self) -> None:
        assert validate_days_of_week([1, 1, 2]) is False

    def test_mixed_valid_invalid(self) -> None:
        assert validate_days_of_week([1, 8]) is False


class TestFormatScheduleDisplay:
    """Tests for format_schedule_display."""

    def test_french_specific_days(self) -> None:
        result = format_schedule_display([1, 3, 5], 19, 30, "fr")
        assert result == "Lun, Mer, Ven à 19:30"

    def test_english_specific_days(self) -> None:
        result = format_schedule_display([1, 3, 5], 19, 30, "en")
        assert result == "Mon, Wed, Fri at 19:30"

    def test_french_every_day(self) -> None:
        result = format_schedule_display([1, 2, 3, 4, 5, 6, 7], 8, 0, "fr")
        assert result == "Tous les jours à 08:00"

    def test_english_every_day(self) -> None:
        result = format_schedule_display([1, 2, 3, 4, 5, 6, 7], 8, 0, "en")
        assert result == "Every day at 08:00"

    def test_french_weekdays(self) -> None:
        result = format_schedule_display([1, 2, 3, 4, 5], 9, 0, "fr")
        assert result == "Lun-Ven à 09:00"

    def test_english_weekdays(self) -> None:
        result = format_schedule_display([1, 2, 3, 4, 5], 9, 0, "en")
        assert result == "Mon-Fri at 09:00"

    def test_french_weekend(self) -> None:
        result = format_schedule_display([6, 7], 10, 30, "fr")
        assert result == "Sam-Dim à 10:30"

    def test_single_day(self) -> None:
        result = format_schedule_display([3], 14, 0, "fr")
        assert result == "Mer à 14:00"

    def test_time_zero_padded(self) -> None:
        result = format_schedule_display([1], 0, 5, "fr")
        assert result == "Lun à 00:05"

    def test_unsorted_days_are_sorted(self) -> None:
        result = format_schedule_display([5, 1, 3], 12, 0, "en")
        assert result == "Mon, Wed, Fri at 12:00"


class TestMidnightGap:
    """A spring-forward that starts at MIDNIGHT must shift, never skip.

    APScheduler 3.11 shifts a non-existent wall-clock time forward by the gap
    (Paris 02:30 on 2026-03-29 fires at 03:30) — except when the gap opens at
    00:00, where it skips the whole local day: measured over every IANA zone
    and every 2026 transition, 2 112 slots shifted and 72 skipped, all 72 in
    the 00:00-00:59 hour of the six zones that change their clocks at
    midnight (Santiago, Havana, Cairo, Beirut, …). A routine scheduled at
    00:30 there silently missed one run a year. These pin the repaired
    behaviour: the run happens on its day, at the first instant that exists.
    """

    SANTIAGO = "America/Santiago"  # 2026-09-06: 00:00 → 01:00
    HAVANA = "America/Havana"  # 2026-03-08: 00:00 → 01:00

    def test_the_skipped_day_runs_at_the_first_instant_after_the_gap(self) -> None:
        reference = datetime(2026, 9, 5, 15, 0, tzinfo=UTC)  # Saturday
        result = compute_next_trigger_utc([7], 0, 30, self.SANTIAGO, after=reference)
        local = result.astimezone(ZoneInfo(self.SANTIAGO))
        assert (local.date().isoformat(), local.hour, local.minute) == ("2026-09-06", 1, 30)

    def test_the_whole_gap_hour_is_shifted_not_only_midnight(self) -> None:
        reference = datetime(2026, 3, 7, 15, 0, tzinfo=UTC)
        for minute in (0, 25, 55):
            result = compute_next_trigger_utc([7], 0, minute, self.HAVANA, after=reference)
            local = result.astimezone(ZoneInfo(self.HAVANA))
            assert local.date().isoformat() == "2026-03-08", minute
            assert (local.hour, local.minute) == (1, minute)

    def test_a_reference_after_the_shifted_instant_moves_on_to_the_next_week(self) -> None:
        # 01:30 local on the transition day has already passed: nothing was skipped.
        reference = datetime(2026, 9, 6, 5, 0, tzinfo=UTC)  # 02:00 local (-03:00)
        result = compute_next_trigger_utc([7], 0, 30, self.SANTIAGO, after=reference)
        assert result.astimezone(ZoneInfo(self.SANTIAGO)).date().isoformat() == "2026-09-13"

    def test_the_week_listing_keeps_the_transition_day(self) -> None:
        reference = datetime(2026, 8, 31, 3, 0, tzinfo=UTC)  # Monday 00:00 local
        runs = compute_next_triggers_utc([7], 0, 0, self.SANTIAGO, count=2, after=reference)
        days = [r.astimezone(ZoneInfo(self.SANTIAGO)).date().isoformat() for r in runs]
        assert days == ["2026-09-06", "2026-09-13"]

    def test_re_arming_after_the_shifted_run_lands_on_the_next_week(self) -> None:
        executed = datetime(2026, 9, 6, 4, 30, tzinfo=UTC)  # the shifted 01:30 local run
        result = compute_next_trigger_after_execution(
            [7], 0, 30, self.SANTIAGO, executed_at=executed, now=executed
        )
        assert result.astimezone(ZoneInfo(self.SANTIAGO)).date().isoformat() == "2026-09-13"

    @pytest.mark.parametrize(
        ("tz_name", "days", "hour", "minute"),
        [
            ("Europe/Paris", [1, 2, 3, 4, 5, 6, 7], 8, 0),
            ("Europe/Paris", [7], 2, 30),  # the ordinary shifted gap
            ("Europe/Paris", [7], 2, 30),  # and the repeated hour, same schedule
            ("Pacific/Auckland", [1, 3, 5], 2, 45),
            ("America/St_Johns", [6, 7], 0, 15),  # half-hour zone, gap at 02:00
            ("Asia/Tokyo", [1], 23, 55),  # no DST at all
        ],
    )
    def test_everything_outside_a_midnight_gap_is_untouched(
        self, tz_name: str, days: list[int], hour: int, minute: int
    ) -> None:
        # Differential: week by week over 2026, the repaired helper must agree
        # with the raw cron wherever the cron was already right.
        trigger = _cron(days, hour, minute, ZoneInfo(tz_name))
        reference = datetime(2026, 1, 1, tzinfo=UTC)
        for _ in range(120):
            raw = trigger.get_next_fire_time(None, reference)
            assert raw is not None
            repaired = compute_next_trigger_utc(days, hour, minute, tz_name, after=reference)
            assert repaired == raw.astimezone(UTC)
            reference = repaired + timedelta(microseconds=1)


class TestWeekSlots:
    """The seven instants of ONE ISO week, in the routine's zone (ADR-265).

    The weekly timeline colours a cell from the run whose ``slot_at`` equals
    the week's instant for that day — never from a tolerance window — so the
    instants must come from the same engine that armed the runs.
    """

    PARIS = "Europe/Paris"

    def test_one_instant_per_configured_day_of_the_week_containing_now(self) -> None:
        now = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)  # Wednesday
        slots = week_slots([1, 3, 5], 8, 0, self.PARIS, now=now)
        local = [s.astimezone(ZoneInfo(self.PARIS)) for s in slots]
        assert [x.date().isoformat() for x in local] == ["2026-08-03", "2026-08-05", "2026-08-07"]
        assert all((x.hour, x.minute) == (8, 0) for x in local)

    def test_past_days_of_the_week_are_included(self) -> None:
        now = datetime(2026, 8, 9, 20, 0, tzinfo=UTC)  # Sunday evening
        slots = week_slots([1, 2, 3, 4, 5, 6, 7], 8, 0, self.PARIS, now=now)
        assert len(slots) == 7
        assert slots[0].astimezone(ZoneInfo(self.PARIS)).date().isoformat() == "2026-08-03"

    def test_a_sunday_slot_is_still_in_the_week_that_started_the_previous_monday(self) -> None:
        # Monday 00:10 local is inside the week that starts that Monday.
        now = datetime(2026, 8, 2, 22, 10, tzinfo=UTC)  # Monday 00:10 CEST
        slots = week_slots([7], 23, 0, self.PARIS, now=now)
        assert slots[0].astimezone(ZoneInfo(self.PARIS)).date().isoformat() == "2026-08-09"

    def test_the_repeated_hour_yields_one_slot_the_first_instant(self) -> None:
        now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
        slots = week_slots([7], 2, 30, self.PARIS, now=now)
        assert len(slots) == 1
        assert slots[0] == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 02:30 CEST

    def test_the_midnight_gap_day_keeps_its_slot(self) -> None:
        now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
        slots = week_slots([7], 0, 30, "America/Santiago", now=now)
        assert [s.astimezone(ZoneInfo("America/Santiago")).isoformat() for s in slots] == [
            "2026-09-06T01:30:00-03:00"
        ]

    def test_week_start_is_the_local_monday(self) -> None:
        # Sunday 23:30 in Auckland is still Sunday: the week started six days ago.
        now = datetime(2026, 8, 9, 11, 30, tzinfo=UTC)  # Sunday 23:30 NZST
        start = week_start(ZoneInfo("Pacific/Auckland"), now=now)
        assert start.isoformat() == "2026-08-03"


class TestLocalDaySlot:
    PARIS = "Europe/Paris"

    def test_the_slot_of_a_configured_day(self) -> None:
        slot = local_day_slot([1, 3], 8, 0, self.PARIS, day=date(2026, 8, 5))
        assert slot == datetime(2026, 8, 5, 6, 0, tzinfo=UTC)

    def test_none_on_a_day_the_routine_does_not_run(self) -> None:
        assert local_day_slot([1, 3], 8, 0, self.PARIS, day=date(2026, 8, 4)) is None

    def test_agrees_with_the_week_listing_on_every_day_of_a_transition_week(self) -> None:
        now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
        for tz_name in (self.PARIS, "America/Santiago", "Pacific/Auckland"):
            for hour, minute in ((0, 30), (2, 30), (23, 55)):
                listed = week_slots([1, 2, 3, 4, 5, 6, 7], hour, minute, tz_name, now=now)
                per_day = [
                    local_day_slot(
                        [1, 2, 3, 4, 5, 6, 7],
                        hour,
                        minute,
                        tz_name,
                        day=s.astimezone(ZoneInfo(tz_name)).date(),
                    )
                    for s in listed
                ]
                assert per_day == listed, (tz_name, hour, minute)


class TestServedSlot:
    """Which week cell a run belongs to.

    A DUE run served its due instant. A MANUAL run ("Test now") served the
    day's slot only when that slot has already passed — a test at 07:00 of an
    08:00 routine is a rehearsal, not the day's execution — and nothing at all
    on a day the routine does not run.
    """

    PARIS = "Europe/Paris"
    DAILY = [1, 2, 3, 4, 5, 6, 7]

    def test_a_due_run_serves_its_due_instant(self) -> None:
        due = datetime(2026, 8, 5, 6, 0, tzinfo=UTC)
        now = datetime(2026, 8, 5, 6, 0, 40, tzinfo=UTC)
        assert served_slot(self.DAILY, 8, 0, self.PARIS, due_at=due, now=now) == due

    def test_a_manual_run_after_the_slot_serves_that_slot(self) -> None:
        due = datetime(2026, 8, 6, 6, 0, tzinfo=UTC)  # tomorrow: nothing due
        now = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)  # 12:00 local, after 08:00
        assert served_slot(self.DAILY, 8, 0, self.PARIS, due_at=due, now=now) == datetime(
            2026, 8, 5, 6, 0, tzinfo=UTC
        )

    def test_a_manual_run_before_the_slot_serves_nothing(self) -> None:
        due = datetime(2026, 8, 5, 6, 0, tzinfo=UTC)
        now = datetime(2026, 8, 5, 5, 0, tzinfo=UTC)  # 07:00 local
        assert served_slot(self.DAILY, 8, 0, self.PARIS, due_at=due, now=now) is None

    def test_a_manual_run_on_an_unscheduled_day_serves_nothing(self) -> None:
        due = datetime(2026, 8, 10, 6, 0, tzinfo=UTC)  # next Monday
        now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)  # Saturday
        assert served_slot([1], 8, 0, self.PARIS, due_at=due, now=now) is None

    def test_a_manual_run_in_the_repeated_hour_serves_the_first_instant(self) -> None:
        # 02:45 CET on 25 October, i.e. after BOTH 02:30s; the day's slot is the CEST one.
        now = datetime(2026, 10, 25, 1, 45, tzinfo=UTC)
        due = datetime(2026, 11, 1, 1, 30, tzinfo=UTC)
        assert served_slot([7], 2, 30, self.PARIS, due_at=due, now=now) == datetime(
            2026, 10, 25, 0, 30, tzinfo=UTC
        )
