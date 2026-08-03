"""Listing the next runs of a routine, and re-arming it after one.

Both are cron questions with a daylight-saving edge that only shows up when you
actually run it. Measured against APScheduler 3.11 (the scheduler's own engine)
over the 2026 transitions of seven zones, including half-hour offsets, a
45-minute one, the southern hemisphere and Lord Howe — whose DST shift is 30
minutes:

- at the FALL-BACK, the wall-clock time exists twice, so the cron yields two
  distinct instants for the same local day. Listing them naively prints the
  same line twice; re-arming from "after now" fires the routine a SECOND time
  the same night (measured: 54 occurrences across the 2026 transitions);
- at the SPRING-FORWARD, the wall-clock time may not exist at all. The trigger
  still returns it carrying the OLD offset, so `02:30` is really `03:30` local.
  Rendering the returned datetime would announce an hour the run will not
  happen at; the instant must be converted back.

The routine model allows exactly one time per day, which is what makes "at most
one run per local day" a safe rule rather than a guess.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.domains.scheduled_actions.schedule_helpers import (
    compute_next_trigger_after_execution,
    compute_next_trigger_utc,
    compute_next_triggers_utc,
    compute_rearm_trigger,
)

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
DAILY = [1, 2, 3, 4, 5, 6, 7]

# 2026 European transitions: 29 March (spring forward), 25 October (fall back).
FALL_BACK_NIGHT = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # 02:30 CEST


class TestListing:
    def test_returns_the_requested_number_of_runs(self) -> None:
        runs = compute_next_triggers_utc(
            [1, 3, 5], 19, 30, "Europe/Paris", count=5, after=datetime(2026, 8, 3, 12, tzinfo=UTC)
        )

        assert len(runs) == 5
        assert all(run.tzinfo == UTC for run in runs)

    def test_runs_are_strictly_increasing(self) -> None:
        runs = compute_next_triggers_utc(
            DAILY, 9, 0, "Europe/Paris", count=5, after=datetime(2026, 8, 3, 12, tzinfo=UTC)
        )

        assert runs == sorted(runs)
        assert len(set(runs)) == len(runs)

    def test_the_repeated_hour_is_not_listed_twice(self) -> None:
        """02:30 exists twice on 25 October; the list must show it once."""
        runs = compute_next_triggers_utc(
            DAILY, 2, 30, "Europe/Paris", count=5, after=datetime(2026, 10, 23, tzinfo=UTC)
        )

        local_days = [run.astimezone(PARIS).date() for run in runs]
        assert len(set(local_days)) == len(local_days), local_days

    def test_a_non_existent_wall_clock_time_reports_the_hour_it_will_really_run(self) -> None:
        """02:30 does not exist on 29 March — the run happens at 03:30 local."""
        runs = compute_next_triggers_utc(
            DAILY, 2, 30, "Europe/Paris", count=3, after=datetime(2026, 3, 28, 12, tzinfo=UTC)
        )

        on_transition = [r for r in runs if r.astimezone(PARIS).date().day == 29]
        assert on_transition, runs
        # Converted from the INSTANT, not read off the trigger's own datetime.
        assert on_transition[0].astimezone(PARIS).hour == 3

    def test_an_offset_change_between_two_runs_is_detectable(self) -> None:
        """What the UI needs to warn "the clocks change in between"."""
        runs = compute_next_triggers_utc(
            DAILY, 9, 0, "Europe/Paris", count=5, after=datetime(2026, 10, 23, tzinfo=UTC)
        )

        offsets = {run.astimezone(PARIS).utcoffset() for run in runs}
        assert len(offsets) == 2

    def test_refuses_a_non_positive_count(self) -> None:
        with pytest.raises(ValueError, match="count"):
            compute_next_triggers_utc(DAILY, 9, 0, "Europe/Paris", count=0)


class TestReArmingAfterARun:
    def test_never_fires_twice_on_the_same_local_day(self) -> None:
        """The defect: 02:30 CEST, then 02:30 CET 59 min 55 s later."""
        executed = FALL_BACK_NIGHT
        now = executed + timedelta(seconds=5)

        nxt = compute_next_trigger_after_execution(
            DAILY, 2, 30, "Europe/Paris", executed_at=executed, now=now
        )

        assert nxt.astimezone(PARIS).date() > executed.astimezone(PARIS).date()

    def test_the_ordinary_case_is_untouched(self) -> None:
        """Everything outside the repeated hour keeps its exact behaviour."""
        executed = datetime(2026, 8, 3, 17, 30, tzinfo=UTC)  # Monday 19:30 Paris
        now = executed + timedelta(seconds=5)

        assert compute_next_trigger_after_execution(
            [1, 3, 5], 19, 30, "Europe/Paris", executed_at=executed, now=now
        ) == compute_next_trigger_utc([1, 3, 5], 19, 30, "Europe/Paris", after=now)

    def test_a_late_tick_never_schedules_in_the_past(self) -> None:
        """The poll can run long after the due time; the next run is ahead."""
        executed = datetime(2026, 8, 3, 17, 30, tzinfo=UTC)
        now = executed + timedelta(days=2, hours=3)

        nxt = compute_next_trigger_after_execution(
            DAILY, 19, 30, "Europe/Paris", executed_at=executed, now=now
        )

        assert nxt > now

    def test_the_result_is_always_after_the_run_that_triggered_it(self) -> None:
        executed = FALL_BACK_NIGHT

        nxt = compute_next_trigger_after_execution(
            DAILY, 2, 30, "Europe/Paris", executed_at=executed, now=executed
        )

        assert nxt > executed


class TestRearmingAScheduledOrManualRun:
    """`execute_single_action` serves BOTH the scheduler and the "run now"
    button, so the re-arm must tell a consumed slot from a manual test."""

    def test_a_consumed_slot_applies_the_local_day_rule(self) -> None:
        due = FALL_BACK_NIGHT
        now = due + timedelta(seconds=5)

        nxt = compute_rearm_trigger(DAILY, 2, 30, "Europe/Paris", due_at=due, now=now)

        assert nxt.astimezone(PARIS).date() > due.astimezone(PARIS).date()

    def test_a_manual_run_never_drops_the_upcoming_one(self) -> None:
        """Testing an 08:00 routine at 07:00 must NOT push it to tomorrow."""
        now = datetime(2026, 8, 3, 5, 0, tzinfo=UTC)  # 07:00 Paris
        due = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)  # 08:00 Paris, still ahead

        nxt = compute_rearm_trigger(DAILY, 8, 0, "Europe/Paris", due_at=due, now=now)

        assert nxt == due

    def test_a_manual_run_after_the_slot_still_re_arms_forward(self) -> None:
        now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        due = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)  # already passed

        nxt = compute_rearm_trigger(DAILY, 8, 0, "Europe/Paris", due_at=due, now=now)

        assert nxt > now
        assert nxt.astimezone(PARIS).date() > due.astimezone(PARIS).date()


class TestLocalizedScheduleDisplay:
    """`format_schedule_display` feeds the automation TOOLS, so its output is
    read by the model and echoed to the user. It served fr and en and gave
    ENGLISH to the four other languages."""

    @pytest.mark.parametrize(
        ("language", "expected"),
        [
            ("fr", "Tous les jours à 08:00"),
            ("en", "Every day at 08:00"),
            ("de", "Täglich um 08:00"),
            ("es", "Todos los días a las 08:00"),
            ("it", "Tutti i giorni alle 08:00"),
            ("zh", "每天 08:00"),
        ],
    )
    def test_every_day_reads_in_the_user_language(self, language: str, expected: str) -> None:
        from src.domains.scheduled_actions.schedule_helpers import format_schedule_display

        assert format_schedule_display(DAILY, 8, 0, language) == expected

    @pytest.mark.parametrize(
        ("language", "expected"),
        [
            ("fr", "Lun, Mer, Ven à 07:15"),
            ("de", "Mo, Mi, Fr um 07:15"),
            ("zh", "周一, 周三, 周五 07:15"),
        ],
    )
    def test_day_abbreviations_are_declared_not_truncated(
        self, language: str, expected: str
    ) -> None:
        """ "Mittwoch"[:3] is "Mit"; German writes "Mi"."""
        from src.domains.scheduled_actions.schedule_helpers import format_schedule_display

        assert format_schedule_display([1, 3, 5], 7, 15, language) == expected

    def test_chinese_uses_its_backend_canonical_table(self) -> None:
        """`zh` and `zh-CN` are the same language through `normalize_language`."""
        from src.domains.scheduled_actions.schedule_helpers import format_schedule_display

        assert format_schedule_display(DAILY, 8, 0, "zh") == format_schedule_display(
            DAILY, 8, 0, "zh-CN"
        )
