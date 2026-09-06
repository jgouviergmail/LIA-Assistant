"""What the DOMAIN does with the instants the engine computes.

`core/recurrence` answers "when does this fire"; this module answers the
questions only a routine asks — which week, which slot a run served, and what
to arm next. The calculation is never re-implemented here.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.core.recurrence.schedule import (
    day_slots,
    rearm_after,
    served_slot,
    week_slots,
    week_start,
)

PARIS = "Europe/Paris"
TZ = ZoneInfo(PARIS)


def at(*pairs: tuple[int, int]) -> DailyTimes:
    return DailyTimes(mode="at", at=tuple(TimeOfDay(hour=h, minute=m) for h, m in pairs))


def daily(*pairs: tuple[int, int], anchor: date = date(2026, 9, 1)) -> RecurrenceSpec:
    return RecurrenceSpec(freq="daily", times=at(*pairs), anchor_date=anchor)


def local(instants: list[datetime]) -> list[str]:
    return [i.astimezone(TZ).strftime("%d/%m %H:%M") for i in instants]


# --- the ISO week -----------------------------------------------------------


def test_week_start_is_the_local_monday() -> None:
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)  # a Sunday
    assert week_start(TZ, now=now) == date(2026, 8, 31)


def test_week_start_reads_the_routine_zone_not_the_server() -> None:
    """Auckland is already on Monday while Paris is still on Sunday."""
    now = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)
    assert week_start(ZoneInfo("Pacific/Auckland"), now=now) == date(2026, 9, 7)
    assert week_start(TZ, now=now) == date(2026, 8, 31)


def test_week_slots_covers_the_whole_current_week_past_days_included() -> None:
    spec = RecurrenceSpec(
        freq="weekly", times=at((8, 0)), anchor_date=date(2026, 9, 7), byweekday=(1, 3, 5)
    )
    got = week_slots(spec, PARIS, now=datetime(2026, 9, 9, 12, 0, tzinfo=UTC))
    assert local(got) == ["07/09 08:00", "09/09 08:00", "11/09 08:00"]


def test_week_slots_returns_every_instant_of_a_multi_slot_day() -> None:
    spec = RecurrenceSpec(
        freq="weekly",
        times=at((8, 0), (18, 0)),
        anchor_date=date(2026, 9, 7),
        byweekday=(1,),
    )
    got = week_slots(spec, PARIS, now=datetime(2026, 9, 9, 12, 0, tzinfo=UTC))
    assert local(got) == ["07/09 08:00", "07/09 18:00"]


def test_week_slots_is_empty_when_nothing_falls_in_the_week() -> None:
    spec = RecurrenceSpec(
        freq="monthly", times=at((9, 0)), anchor_date=date(2026, 9, 1), bymonthday=(20,)
    )
    assert week_slots(spec, PARIS, now=datetime(2026, 9, 9, 12, 0, tzinfo=UTC)) == []


# --- one local day ----------------------------------------------------------


def test_day_slots_returns_a_list_a_day_may_hold_several() -> None:
    spec = daily((8, 0), (12, 30), (19, 0))
    assert local(day_slots(spec, PARIS, day=date(2026, 9, 8))) == [
        "08/09 08:00",
        "08/09 12:30",
        "08/09 19:00",
    ]


def test_day_slots_is_empty_on_a_day_the_routine_skips() -> None:
    spec = RecurrenceSpec(
        freq="weekly", times=at((8, 0)), anchor_date=date(2026, 9, 7), byweekday=(1,)
    )
    assert day_slots(spec, PARIS, day=date(2026, 9, 8)) == []


def test_day_slots_on_a_short_local_day() -> None:
    """29/03 lasts 23 hours in Paris: an hourly rule fires 23 times, not 24."""
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=60,
            start=TimeOfDay(hour=0, minute=0),
            end=TimeOfDay(hour=23, minute=0),
        ),
        anchor_date=date(2026, 3, 1),
    )
    assert len(day_slots(spec, PARIS, day=date(2026, 3, 29))) == 23


# --- which slot a run served (spec 4.11) ------------------------------------


def test_a_due_run_serves_its_due_instant() -> None:
    spec = daily((8, 0))
    due = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)
    assert served_slot(spec, PARIS, due_at=due, now=due + timedelta(minutes=3)) == due


def test_a_manual_run_before_any_slot_is_a_rehearsal() -> None:
    spec = daily((8, 0))
    now = datetime(2026, 9, 8, 7, 0, tzinfo=TZ).astimezone(UTC)
    assert served_slot(spec, PARIS, due_at=now + timedelta(hours=5), now=now) is None


def test_a_manual_run_serves_the_LATEST_passed_slot_of_the_day() -> None:
    spec = daily((8, 0), (12, 30), (19, 0))
    now = datetime(2026, 9, 8, 14, 0, tzinfo=TZ).astimezone(UTC)
    got = served_slot(spec, PARIS, due_at=now + timedelta(hours=5), now=now)
    assert got is not None
    assert got.astimezone(TZ).strftime("%H:%M") == "12:30"


def test_a_manual_run_on_a_day_the_routine_skips_serves_nothing() -> None:
    spec = RecurrenceSpec(
        freq="weekly", times=at((8, 0)), anchor_date=date(2026, 9, 7), byweekday=(1,)
    )
    now = datetime(2026, 9, 8, 14, 0, tzinfo=TZ).astimezone(UTC)
    assert served_slot(spec, PARIS, due_at=now + timedelta(hours=5), now=now) is None


# --- re-arming (spec 4.7) ---------------------------------------------------


def test_rearm_moves_strictly_past_the_slot_just_served() -> None:
    spec = daily((8, 0))
    due = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)
    got = rearm_after(spec, PARIS, due_at=due, now=due + timedelta(seconds=30))
    assert got is not None and got > due
    assert got.astimezone(TZ).strftime("%d/%m %H:%M") == "09/09 08:00"


def test_rearm_after_an_outage_fires_once_never_a_catch_up_storm() -> None:
    """Measured 2026-09-06: re-arming from `due_at` fired 145 runs after a
    three-day outage; from `max(due, now)`, exactly one. A missed slot is
    missed — the system never replays three days of agent pipelines."""
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=30,
            start=TimeOfDay(hour=0, minute=0),
            end=TimeOfDay(hour=23, minute=30),
        ),
        anchor_date=date(2026, 1, 1),
    )
    due = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    now = due + timedelta(days=3)
    fired = 0
    armed: datetime | None = due
    while armed is not None and armed <= now and fired < 500:
        fired += 1
        armed = rearm_after(spec, PARIS, due_at=armed, now=now)
    assert fired == 1


def test_rearm_of_an_exhausted_series_is_none() -> None:
    spec = RecurrenceSpec(freq="once", times=at((9, 0)), anchor_date=date(2026, 9, 8))
    due = datetime(2026, 9, 8, 7, 0, tzinfo=UTC)
    assert rearm_after(spec, PARIS, due_at=due, now=due) is None


def test_a_manual_run_ahead_of_schedule_keeps_the_upcoming_slot() -> None:
    """Testing an 08:00 routine at 07:00 must not push it to tomorrow."""
    spec = daily((8, 0))
    now = datetime(2026, 9, 8, 7, 0, tzinfo=TZ).astimezone(UTC)
    due = datetime(2026, 9, 8, 8, 0, tzinfo=TZ).astimezone(UTC)
    got = rearm_after(spec, PARIS, due_at=due, now=now)
    assert got == due


@pytest.mark.parametrize("zone", ["Europe/Paris", "America/Santiago", "Pacific/Auckland"])
def test_rearm_never_returns_the_instant_it_was_given(zone: str) -> None:
    spec = daily((2, 30))
    now = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    due = now
    for _ in range(20):
        nxt = rearm_after(spec, zone, due_at=due, now=due)
        assert nxt is not None and nxt > due
        due = nxt
