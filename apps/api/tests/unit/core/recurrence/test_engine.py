"""The engine: coverage, DST, ordering, end of series, cost.

Every assertion here is a measurement recorded in the design document
(`docs/superpowers/specs/2026-09-06-generic-recurrence-design.md`).
"""

import time as perf
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import (
    DailyTimes,
    RecurrenceSpec,
    SeriesEnd,
    TimeOfDay,
    next_occurrence,
    occurrences,
    slots_between,
)

PARIS = "Europe/Paris"
TZ = ZoneInfo(PARIS)
NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def at(*pairs: tuple[int, int]) -> DailyTimes:
    return DailyTimes(mode="at", at=tuple(TimeOfDay(hour=h, minute=m) for h, m in pairs))


def local(instants: list[datetime], fmt: str = "%d/%m %H:%M") -> list[str]:
    return [i.astimezone(TZ).strftime(fmt) for i in instants]


# --- Coverage of the requested corpus -------------------------------------


def test_single_occurrence() -> None:
    spec = RecurrenceSpec(freq="once", times=at((9, 0)), anchor_date=date(2026, 9, 12))
    assert local(occurrences(spec, PARIS, after=NOW, count=3)) == ["12/09 09:00"]


def test_several_fixed_times_a_day() -> None:
    spec = RecurrenceSpec(
        freq="daily", times=at((8, 0), (12, 30), (19, 0)), anchor_date=date(2026, 9, 7)
    )
    assert local(occurrences(spec, PARIS, after=NOW, count=4)) == [
        "07/09 08:00",
        "07/09 12:30",
        "07/09 19:00",
        "08/09 08:00",
    ]


def test_a_step_from_a_start_time() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=120,
            start=TimeOfDay(hour=8, minute=0),
            end=TimeOfDay(hour=14, minute=0),
        ),
        anchor_date=date(2026, 9, 7),
    )
    assert local(occurrences(spec, PARIS, after=NOW, count=4)) == [
        "07/09 08:00",
        "07/09 10:00",
        "07/09 12:00",
        "07/09 14:00",
    ]


def test_every_other_week_on_two_weekdays() -> None:
    spec = RecurrenceSpec(
        freq="weekly",
        times=at((9, 0)),
        anchor_date=date(2026, 9, 7),
        interval=2,
        byweekday=(1, 4),
    )
    assert local(occurrences(spec, PARIS, after=NOW, count=4)) == [
        "07/09 09:00",
        "10/09 09:00",
        "21/09 09:00",
        "24/09 09:00",
    ]


def test_a_day_of_the_month() -> None:
    spec = RecurrenceSpec(
        freq="monthly", times=at((10, 0)), anchor_date=date(2026, 9, 1), bymonthday=(15,)
    )
    assert local(occurrences(spec, PARIS, after=NOW, count=3)) == [
        "15/09 10:00",
        "15/10 10:00",
        "15/11 10:00",
    ]


def test_the_last_day_of_the_month() -> None:
    spec = RecurrenceSpec(
        freq="monthly", times=at((23, 30)), anchor_date=date(2026, 9, 1), bymonthday=(-1,)
    )
    assert local(occurrences(spec, PARIS, after=NOW, count=3)) == [
        "30/09 23:30",
        "31/10 23:30",
        "30/11 23:30",
    ]


def test_the_nth_weekday_of_the_month() -> None:
    spec = RecurrenceSpec(
        freq="monthly", times=at((14, 0)), anchor_date=date(2026, 9, 1), nth_weekday=(2, 2)
    )
    assert local(occurrences(spec, PARIS, after=NOW, count=3)) == [
        "08/09 14:00",
        "13/10 14:00",
        "10/11 14:00",
    ]


def test_quarterly_is_monthly_times_three() -> None:
    spec = RecurrenceSpec(
        freq="monthly",
        times=at((9, 0)),
        anchor_date=date(2026, 10, 1),
        interval=3,
        bymonthday=(1,),
    )
    assert local(occurrences(spec, PARIS, after=NOW, count=3), "%d/%m/%Y") == [
        "01/10/2026",
        "01/01/2027",
        "01/04/2027",
    ]


def test_yearly_on_a_leap_day() -> None:
    spec = RecurrenceSpec(
        freq="yearly",
        times=at((8, 0)),
        anchor_date=date(2024, 2, 29),
        bymonth=(2,),
        bymonthday=(29,),
    )
    assert local(occurrences(spec, PARIS, after=NOW, count=2), "%d/%m/%Y") == [
        "29/02/2028",
        "29/02/2032",
    ]


# --- The series is ONE series (spec 4.1) ----------------------------------


@pytest.mark.parametrize(
    "spec",
    [
        RecurrenceSpec(
            freq="weekly",
            times=at((9, 0)),
            anchor_date=date(2026, 9, 8),
            interval=2,
            byweekday=(2,),
        ),
        RecurrenceSpec(freq="daily", times=at((9, 0)), anchor_date=date(2026, 9, 6), interval=3),
    ],
)
def test_the_series_does_not_drift_with_the_reference(spec: RecurrenceSpec) -> None:
    reference = occurrences(spec, PARIS, after=NOW, count=40)
    universe = set(reference)
    for offset in range(0, 300, 7):
        for instant in occurrences(spec, PARIS, after=NOW + timedelta(days=offset), count=3):
            if instant <= reference[-1]:
                assert instant in universe


# --- Daylight saving (spec 4.3, 4.4) --------------------------------------


def test_the_wall_clock_survives_the_spring_transition() -> None:
    spec = RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 3, 27))
    got = occurrences(spec, PARIS, after=datetime(2026, 3, 27, 0, 0, tzinfo=UTC), count=4)
    assert local(got) == ["27/03 08:00", "28/03 08:00", "29/03 08:00", "30/03 08:00"]


def test_the_day_the_current_engine_skips_is_served() -> None:
    """Europe/Paris, 00:30: APScheduler jumps from 29/03 to 31/03 (measured)."""
    spec = RecurrenceSpec(freq="daily", times=at((0, 30)), anchor_date=date(2026, 3, 20))
    got = occurrences(spec, PARIS, after=datetime(2026, 3, 28, 12, 0, tzinfo=UTC), count=3)
    assert local(got) == ["29/03 00:30", "30/03 00:30", "31/03 00:30"]


def test_a_sub_daily_rule_never_goes_backwards_or_repeats() -> None:
    """02:30 -> 01:30Z then 03:00 -> 01:00Z: ordering by wall clock would
    fire twice and go backwards (measured)."""
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=30,
            start=TimeOfDay(hour=0, minute=0),
            end=TimeOfDay(hour=23, minute=30),
        ),
        anchor_date=date(2026, 3, 29),
    )
    # A local day is NOT 24 hours: 29/03 lasts 23 h in Paris, so `start + 1 day`
    # would spill onto the 30th and count two extra moments (measured: 48
    # instead of 46). Both bounds are built from the local calendar.
    start = datetime(2026, 3, 29, 0, 0, tzinfo=TZ).astimezone(UTC)
    end = datetime(2026, 3, 30, 0, 0, tzinfo=TZ).astimezone(UTC)
    got = slots_between(spec, PARIS, start=start, end=end)
    assert got == sorted(got)
    assert len(got) == len(set(got))
    # 46, not 48: the clocks skip an hour, so two half-hour moments
    # collapse. Measured 2026-09-06 — a preference would not survive here.
    assert len(got) == 46


def test_the_midnight_gap_day_is_served() -> None:
    """America/Santiago changes at midnight; the cron skipped the whole day."""
    spec = RecurrenceSpec(freq="daily", times=at((0, 30)), anchor_date=date(2026, 9, 1))
    zone = "America/Santiago"
    got = occurrences(spec, zone, after=datetime(2026, 9, 4, 12, 0, tzinfo=UTC), count=3)
    days = [i.astimezone(ZoneInfo(zone)).day for i in got]
    assert days == [5, 6, 7]


# --- End of series (spec 4.7 traps) ---------------------------------------


def test_after_count_counts_instants_not_days() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=at((8, 0), (12, 30), (19, 0)),
        anchor_date=date(2026, 9, 7),
        end=SeriesEnd(kind="after_count", after_count=10),
    )
    got = occurrences(spec, PARIS, after=NOW, count=50)
    assert len(got) == 10
    assert local(got[-1:]) == ["10/09 08:00"]


def test_on_date_includes_the_last_local_day() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=at((23, 30)),
        anchor_date=date(2026, 12, 1),
        end=SeriesEnd(kind="on_date", on_date=date(2026, 12, 31)),
    )
    got = occurrences(spec, PARIS, after=datetime(2026, 12, 28, 12, 0, tzinfo=UTC), count=50)
    assert local(got[-1:]) == ["31/12 23:30"]


def test_an_exhausted_series_yields_nothing() -> None:
    spec = RecurrenceSpec(
        freq="weekly",
        times=at((9, 0)),
        anchor_date=date(2026, 9, 8),
        interval=2,
        byweekday=(2,),
        end=SeriesEnd(kind="after_count", after_count=3),
    )
    got = occurrences(spec, PARIS, after=NOW, count=50)
    assert len(got) == 3
    assert next_occurrence(spec, PARIS, after=got[-1]) is None


def test_a_past_single_occurrence_yields_nothing() -> None:
    spec = RecurrenceSpec(freq="once", times=at((9, 0)), anchor_date=date(2026, 9, 1))
    assert occurrences(spec, PARIS, after=NOW, count=3) == []
    assert next_occurrence(spec, PARIS, after=NOW) is None


# --- Contracts the consumers depend on ------------------------------------


def test_the_bound_is_strict() -> None:
    """One convention: production mixes inclusive and strict today."""
    spec = RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 9, 7))
    first = occurrences(spec, PARIS, after=NOW, count=1)[0]
    assert occurrences(spec, PARIS, after=first, count=1)[0] > first


def test_slots_between_agrees_with_occurrences() -> None:
    """The ADR-265 equality depends on this: a cell is coloured by
    `slot_at == the week's instant`."""
    spec = RecurrenceSpec(
        freq="weekly",
        times=at((8, 0), (18, 0)),
        anchor_date=date(2026, 9, 7),
        byweekday=(1, 2, 3, 4, 5),
    )
    start = datetime(2026, 9, 7, 0, 0, tzinfo=TZ).astimezone(UTC)
    end = start + timedelta(days=7)
    window = slots_between(spec, PARIS, start=start, end=end)
    walked = [
        i
        for i in occurrences(spec, PARIS, after=start - timedelta(microseconds=1), count=200)
        if i < end
    ]
    assert window == walked


def test_a_four_year_old_anchor_stays_cheap() -> None:
    """The anchor is a phase, never a starting point to iterate from
    (measured: 60 ms without the fast-forward, 35.8 ms with it)."""
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=60,
            start=TimeOfDay(hour=8, minute=0),
            end=TimeOfDay(hour=19, minute=0),
        ),
        anchor_date=date(2022, 1, 1),
    )
    start = datetime(2026, 9, 7, 0, 0, tzinfo=TZ).astimezone(UTC)
    began = perf.perf_counter()
    got = slots_between(spec, PARIS, start=start, end=start + timedelta(days=7))
    elapsed_ms = (perf.perf_counter() - began) * 1000
    assert len(got) == 84
    assert elapsed_ms < 50


# --- Adversarial review, 2026-09-06 ----------------------------------------


def test_a_civil_day_that_never_existed_is_absorbed() -> None:
    """Pacific/Apia deleted 30 December 2011 to cross the date line.

    The wall clock of a deleted day resolves to the same instant as the next
    day's, so ONLY the de-duplication by instant keeps the series strictly
    increasing. Nothing else in the engine notices such a day.
    """
    spec = RecurrenceSpec(freq="daily", times=at((9, 0)), anchor_date=date(2011, 12, 28))
    zone = "Pacific/Apia"
    got = occurrences(spec, zone, after=datetime(2011, 12, 28, 0, 0, tzinfo=UTC), count=5)
    days = [i.astimezone(ZoneInfo(zone)).day for i in got]
    assert days == [28, 29, 31, 1, 2]
    assert got == sorted(got)
    assert len(set(got)) == len(got)


def test_a_long_request_is_served_in_full_never_truncated_in_silence() -> None:
    """A scan budget must guard against a rule that produces nothing — never
    cut a legitimate answer short.

    Measured 2026-09-06: a fixed budget of 4 000 scanned days returned 3 999 of
    5 000 requested occurrences with no signal at all. A caller cannot tell a
    short series from a truncated one, which is the silent-defect class the
    impossible-date rule (spec 4.8) exists to remove.
    """
    spec = RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2020, 1, 1))
    got = occurrences(spec, PARIS, after=datetime(2026, 9, 6, tzinfo=UTC), count=5000)
    assert len(got) == 5000


# --- carried over from test_occurrences.py, whose engine this replaces ------


def test_a_non_positive_count_is_refused() -> None:
    """A caller asking for zero occurrences has a bug, and a silent empty list
    would hide it."""
    spec = RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 9, 7))
    with pytest.raises(ValueError):
        occurrences(spec, PARIS, after=NOW, count=0)
    with pytest.raises(ValueError):
        occurrences(spec, PARIS, after=NOW, count=-1)


def test_the_repeated_autumn_hour_is_served_once_not_twice() -> None:
    """At the fall-back the wall clock exists twice. `fold=0` keeps the FIRST
    occurrence, so a routine at 02:30 fires once on 25/10 — the cron engine
    needed a whole local-day de-duplication rule to reach the same answer."""
    spec = RecurrenceSpec(freq="daily", times=at((2, 30)), anchor_date=date(2026, 10, 20))
    start = datetime(2026, 10, 25, 0, 0, tzinfo=TZ).astimezone(UTC)
    end = datetime(2026, 10, 26, 0, 0, tzinfo=TZ).astimezone(UTC)
    got = slots_between(spec, PARIS, start=start, end=end)
    assert len(got) == 1
    assert got[0].isoformat() == "2026-10-25T00:30:00+00:00"


def test_an_offset_change_between_two_runs_is_visible_on_the_instants() -> None:
    """The wall clock is unchanged across a transition but the instant shifts
    by the offset — which is what lets a client flag a clock change."""
    spec = RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 10, 20))
    got = occurrences(spec, PARIS, after=datetime(2026, 10, 24, 0, 0, tzinfo=UTC), count=3)
    offsets = {i.astimezone(TZ).utcoffset() for i in got}
    assert len(offsets) == 2  # CEST then CET
    assert {i.astimezone(TZ).strftime("%H:%M") for i in got} == {"08:00"}
