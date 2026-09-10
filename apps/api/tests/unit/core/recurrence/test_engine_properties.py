"""What the engine must hold for EVERY recurrence, not just the ones we listed.

The package is already pinned by a golden corpus and by hand-written cases, and
both share one blind spot: they can only fail on a shape somebody thought of.
The properties below are checked against a seeded random walk of the whole
vocabulary — five frequencies, both time modes, three end kinds, every day
selector — in zones chosen for the calendars that break naive engines:
``Pacific/Apia`` deleted a civil day outright, ``Australia/Lord_Howe`` shifts by
THIRTY minutes, ``Pacific/Chatham`` by 45, and the two hemispheres transition in
opposite directions.

Seeded, so a failure is reproducible and a green run means the same thing
twice. Measured over 4 000 specs when this was written (2026-09-10): zero
violations — which is the point. A property test earns its place by being able
to fail on a shape no fixture names.
"""

from __future__ import annotations

import itertools
import random
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import (
    DailyTimes,
    RecurrenceError,
    RecurrenceSpec,
    SeriesEnd,
    TimeOfDay,
)
from src.core.recurrence.engine import next_occurrence, occurrences, series, slots_between

pytestmark = pytest.mark.unit

#: Zones whose calendars break a naive engine, plus one ordinary one.
ZONES = (
    "Europe/Paris",
    "America/New_York",
    "Pacific/Apia",
    "Australia/Lord_Howe",
    "Pacific/Chatham",
    "UTC",
)

#: Kept small enough to stay a unit test; large enough to walk the vocabulary.
SAMPLE = 400
SEED = 20260910


def _times(rng: random.Random) -> DailyTimes:
    """A random day, in either mode."""
    if rng.random() < 0.25:
        first, last = sorted(rng.sample(range(24), 2))
        return DailyTimes(
            mode="every",
            step_minutes=rng.choice([15, 30, 60, 120]),
            start=TimeOfDay(hour=first, minute=0),
            end=TimeOfDay(hour=last, minute=0),
        )
    return DailyTimes(
        mode="at",
        at=tuple(
            TimeOfDay(hour=rng.randint(0, 23), minute=rng.choice([0, 15, 30, 45]))
            for _ in range(rng.randint(1, 3))
        ),
    )


def _spec(rng: random.Random) -> RecurrenceSpec | None:
    """A random recurrence, or None when the draw produced a refused shape."""
    freq = rng.choice(["once", "daily", "weekly", "monthly", "yearly"])
    anchor = date(2026, rng.randint(1, 12), rng.randint(1, 28))
    kwargs: dict[str, object] = {"freq": freq, "times": _times(rng), "anchor_date": anchor}
    if freq != "once":
        kwargs["interval"] = rng.choice([1, 1, 1, 2, 3])
        if rng.random() < 0.35:
            if rng.random() < 0.5:
                kwargs["end"] = SeriesEnd(
                    kind="on_date", on_date=anchor + timedelta(days=rng.randint(0, 800))
                )
            else:
                kwargs["end"] = SeriesEnd(kind="after_count", after_count=rng.randint(1, 30))
    if freq == "weekly":
        kwargs["byweekday"] = tuple(sorted(rng.sample(range(1, 8), rng.randint(1, 4))))
    elif freq == "monthly":
        if rng.random() < 0.4:
            kwargs["nth_weekday"] = (rng.choice([-1, 1, 2, 3, 4, 5]), rng.randint(1, 7))
        else:
            kwargs["bymonthday"] = tuple(
                sorted({rng.choice([-1, *range(1, 32)]) for _ in range(rng.randint(1, 3))})
            )
    elif freq == "yearly":
        kwargs["bymonth"] = tuple(sorted(rng.sample(range(1, 13), rng.randint(1, 3))))
        kwargs["bymonthday"] = tuple(
            sorted({rng.choice([-1, *range(1, 32)]) for _ in range(rng.randint(1, 2))})
        )
    try:
        return RecurrenceSpec(**kwargs)  # type: ignore[arg-type]
    except RecurrenceError, ValueError:
        # A refused shape is the spec doing its job, not a sample worth keeping.
        return None


def _walk() -> list[tuple[RecurrenceSpec, str, datetime]]:
    """The sample: (spec, zone, reference instant), deterministic under SEED."""
    rng = random.Random(SEED)
    drawn: list[tuple[RecurrenceSpec, str, datetime]] = []
    while len(drawn) < SAMPLE:
        spec = _spec(rng)
        if spec is None:
            continue
        drawn.append(
            (
                spec,
                rng.choice(ZONES),
                datetime(
                    2026,
                    rng.randint(1, 12),
                    rng.randint(1, 28),
                    rng.randint(0, 23),
                    rng.choice([0, 30]),
                    tzinfo=UTC,
                ),
            )
        )
    return drawn


#: Days a zone's clock actually moves, and the direction it moves in. A random
#: walk lands on one about once in a thousand draws, so they are named.
_TRANSITIONS: tuple[tuple[str, date], ...] = (
    ("Europe/Paris", date(2026, 3, 29)),  # spring: 02:00 → 03:00
    ("Europe/Paris", date(2026, 10, 25)),  # autumn: the 02:00 hour runs twice
    ("America/New_York", date(2026, 3, 8)),
    ("America/New_York", date(2026, 11, 1)),
    ("Australia/Lord_Howe", date(2026, 4, 5)),  # thirty minutes, not sixty
    ("Pacific/Chatham", date(2026, 9, 27)),  # forty-five
)


def _clock_change_cases() -> list[tuple[RecurrenceSpec, str, datetime]]:
    """A served day on each transition, stepping THROUGH the moving hour.

    This is what makes the strictly-increasing property able to fail: at a
    spring transition 02:00 and 03:00 resolve to the SAME instant, so a walk
    that never crosses one would pass with the de-duplication removed —
    measured 2026-09-10, and a property its own falsification cannot break is
    decoration.
    """
    cases: list[tuple[RecurrenceSpec, str, datetime]] = []
    for zone, day in _TRANSITIONS:
        for step in (30, 60):
            spec = RecurrenceSpec(
                freq="daily",
                times=DailyTimes(
                    mode="every",
                    step_minutes=step,
                    start=TimeOfDay(hour=0, minute=0),
                    end=TimeOfDay(hour=23, minute=30),
                ),
                anchor_date=day,
            )
            midnight = datetime.combine(day, datetime.min.time(), tzinfo=ZoneInfo(zone))
            cases.append((spec, zone, midnight.astimezone(UTC) - timedelta(seconds=1)))
    return cases


CLOCK_CHANGES = _clock_change_cases()
SAMPLES = _walk() + CLOCK_CHANGES


def _label(spec: RecurrenceSpec, zone: str, after: datetime) -> str:
    """What a failure must print to be reproducible without the seed."""
    return f"{spec.model_dump(mode='json')} | {zone} | after={after.isoformat()}"


class TestEveryRecurrenceHoldsTheseInvariants:
    """One walk, eight properties — each a promise the docstrings make."""

    def test_the_sample_is_not_degenerate(self) -> None:
        """A property suite over an empty walk is a green that means nothing."""
        assert len(SAMPLES) == SAMPLE + len(CLOCK_CHANGES)
        assert len({spec.freq for spec, _, _ in SAMPLES}) == 5
        assert CLOCK_CHANGES, "without a clock change, the de-duplication is never exercised"

    def test_every_instant_is_strictly_after_the_reference(self) -> None:
        for spec, zone, after in SAMPLES:
            for instant in occurrences(spec, zone, after=after, count=8):
                assert instant > after, _label(spec, zone, after)

    def test_the_series_is_strictly_increasing(self) -> None:
        """Two wall clocks collapse onto one instant at a spring transition."""
        for spec, zone, after in SAMPLES:
            got = occurrences(spec, zone, after=after, count=60)
            assert all(a < b for a, b in itertools.pairwise(got)), _label(spec, zone, after)

    def test_a_moving_clock_really_does_collapse_two_moments(self) -> None:
        """The premise of the test above — asserted, never assumed.

        If no named transition actually produced a collision, the property
        would be green for the wrong reason and the de-duplication could be
        deleted unnoticed.
        """
        collapsed = 0
        for spec, zone, after in CLOCK_CHANGES:
            moments = spec.times.materialise()
            served = occurrences(spec, zone, after=after, count=len(moments) + 5)
            same_day = [
                instant
                for instant in served
                if instant.astimezone(ZoneInfo(zone)).date() == spec.anchor_date
            ]
            if len(same_day) < len(moments):
                collapsed += 1
        assert collapsed, "no named transition collapsed a moment — the sample is inert"

    def test_no_instant_falls_past_the_last_local_day(self) -> None:
        for spec, zone, after in SAMPLES:
            last_day = spec.end.on_date
            if spec.end.kind != "on_date" or last_day is None:
                continue
            zone_info = ZoneInfo(zone)
            for instant in occurrences(spec, zone, after=after, count=8):
                assert instant.astimezone(zone_info).date() <= last_day, _label(spec, zone, after)

    def test_next_occurrence_is_the_first_of_the_listing(self) -> None:
        """Two readers of one rule: they answer the same instant or neither does."""
        for spec, zone, after in SAMPLES:
            got = occurrences(spec, zone, after=after, count=1)
            expected = got[0] if got else None
            assert next_occurrence(spec, zone, after=after) == expected, _label(spec, zone, after)

    def test_the_weekly_grid_reads_the_same_instants_as_the_listing(self) -> None:
        """The grid colours a cell by EQUALITY with these instants (ADR-265)."""
        for spec, zone, after in SAMPLES:
            got = occurrences(spec, zone, after=after, count=8)
            if not got:
                continue
            window = slots_between(
                spec, zone, start=got[0], end=got[-1] + timedelta(microseconds=1)
            )
            assert window == got, _label(spec, zone, after)

    def test_a_counted_series_yields_exactly_its_count(self) -> None:
        """``after_count`` counts INSTANTS from the anchor, never days."""
        for spec, zone, after in SAMPLES:
            wanted = spec.end.after_count
            if spec.end.kind != "after_count" or wanted is None:
                continue
            assert sum(1 for _ in series(spec, ZoneInfo(zone))) == wanted, _label(spec, zone, after)

    def test_a_counted_series_offers_nothing_past_its_own_last_instant(self) -> None:
        """The boundary is the series' OWN end, never a date we guessed at.

        Written first as « nothing after 2032 », which failed on a yearly rule
        naming two months: sixteen occurrences at two a year reach 2033. The
        engine was right and the property was naive — a property is read off
        the contract, never off an intuition about how far a series goes.
        """
        for spec, zone, after in SAMPLES:
            if spec.end.kind != "after_count":
                continue
            emitted = list(series(spec, ZoneInfo(zone)))
            assert emitted, _label(spec, zone, after)
            assert occurrences(spec, zone, after=emitted[-1], count=3) == [], _label(
                spec, zone, emitted[-1]
            )
