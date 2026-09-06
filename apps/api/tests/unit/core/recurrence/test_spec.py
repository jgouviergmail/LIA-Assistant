"""The recurrence vocabulary: what it accepts, and what it refuses."""

from datetime import date

import pytest

from src.core.recurrence import (
    DailyTimes,
    RecurrenceError,
    RecurrenceLimits,
    RecurrenceSpec,
    SeriesEnd,
    TimeOfDay,
)
from src.core.recurrence.spec import _HARD_TIMES_CEILING

LIMITS = RecurrenceLimits(max_times_per_day=48, min_step_minutes=5, max_series_count=1000)


def at(*pairs: tuple[int, int]) -> DailyTimes:
    """A `DailyTimes` from (hour, minute) pairs."""
    return DailyTimes(mode="at", at=tuple(TimeOfDay(hour=h, minute=m) for h, m in pairs))


def test_explicit_times_are_sorted_and_deduplicated() -> None:
    times = DailyTimes(
        mode="at",
        at=(
            TimeOfDay(hour=19, minute=0),
            TimeOfDay(hour=8, minute=0),
            TimeOfDay(hour=8, minute=0),
        ),
    )
    assert times.materialise() == (TimeOfDay(hour=8, minute=0), TimeOfDay(hour=19, minute=0))


def test_step_times_are_materialised_between_the_bounds() -> None:
    times = DailyTimes(
        mode="every",
        step_minutes=120,
        start=TimeOfDay(hour=8, minute=0),
        end=TimeOfDay(hour=14, minute=0),
    )
    assert [(t.hour, t.minute) for t in times.materialise()] == [
        (8, 0),
        (10, 0),
        (12, 0),
        (14, 0),
    ]


def test_per_day_counts_the_materialised_times() -> None:
    spec = RecurrenceSpec(
        freq="daily", times=at((8, 0), (12, 30), (19, 0)), anchor_date=date(2026, 9, 6)
    )
    assert spec.per_day() == 3


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("interval below one", {"freq": "daily", "interval": 0}),
        ("weekly without a weekday", {"freq": "weekly"}),
        ("monthly without a selector", {"freq": "monthly"}),
        (
            "monthly with both selectors",
            {"freq": "monthly", "bymonthday": (1,), "nth_weekday": (2, 2)},
        ),
        ("yearly without a month", {"freq": "yearly", "bymonthday": (24,)}),
        ("once with an interval", {"freq": "once", "interval": 2}),
        (
            "once with an end rule",
            {"freq": "once", "end": SeriesEnd(kind="after_count", after_count=3)},
        ),
        ("weekday out of range", {"freq": "weekly", "byweekday": (8,)}),
        ("day of month out of range", {"freq": "monthly", "bymonthday": (32,)}),
        ("nth out of range", {"freq": "monthly", "nth_weekday": (6, 1)}),
        ("month out of range", {"freq": "yearly", "bymonth": (13,), "bymonthday": (1,)}),
    ],
)
def test_structural_refusals(label: str, kwargs: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "times": at((8, 0)),
        "anchor_date": date(2026, 9, 6),
        **kwargs,
    }
    with pytest.raises((RecurrenceError, ValueError)):
        RecurrenceSpec(**payload)  # type: ignore[arg-type]


def test_an_impossible_calendar_date_is_refused() -> None:
    """30 February would validate, cost 166 ms and produce nothing (spec 4.8)."""
    with pytest.raises((RecurrenceError, ValueError)):
        RecurrenceSpec(
            freq="yearly",
            times=at((9, 0)),
            anchor_date=date(2026, 1, 1),
            bymonth=(2,),
            bymonthday=(30,),
        )


def test_a_possible_pair_among_impossible_ones_is_accepted() -> None:
    """31 exists in March even though February has no 31st."""
    spec = RecurrenceSpec(
        freq="yearly",
        times=at((9, 0)),
        anchor_date=date(2026, 1, 1),
        bymonth=(2, 3),
        bymonthday=(31,),
    )
    assert spec.bymonth == (2, 3)


def test_injected_limits_refuse_beyond_the_cap() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=30,
            start=TimeOfDay(hour=0, minute=0),
            end=TimeOfDay(hour=23, minute=30),
        ),
        anchor_date=date(2026, 9, 6),
    )
    tight = RecurrenceLimits(max_times_per_day=12, min_step_minutes=5, max_series_count=1000)
    with pytest.raises(RecurrenceError):
        spec.validate_against(tight)
    spec.validate_against(LIMITS)  # the same spec, a wider consumer


def test_injected_step_floor_is_enforced() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=5,
            start=TimeOfDay(hour=8, minute=0),
            end=TimeOfDay(hour=8, minute=30),
        ),
        anchor_date=date(2026, 9, 6),
    )
    strict = RecurrenceLimits(max_times_per_day=48, min_step_minutes=15, max_series_count=1000)
    with pytest.raises(RecurrenceError):
        spec.validate_against(strict)


def test_the_two_default_limit_sets_differ_and_are_coherent() -> None:
    """A routine runs a pipeline, a reminder sends a notification: the caps
    are not the same, and both are readable from one place."""
    from src.core.constants import RECURRENCE_REMINDER_LIMITS, RECURRENCE_ROUTINE_LIMITS

    assert RECURRENCE_ROUTINE_LIMITS.max_times_per_day < (
        RECURRENCE_REMINDER_LIMITS.max_times_per_day
    )
    assert RECURRENCE_ROUTINE_LIMITS.min_step_minutes >= (
        RECURRENCE_REMINDER_LIMITS.min_step_minutes
    )
    for limits in (RECURRENCE_ROUTINE_LIMITS, RECURRENCE_REMINDER_LIMITS):
        assert limits.max_times_per_day >= 1
        assert limits.min_step_minutes >= 1
        assert limits.max_series_count >= 1


def test_a_routine_shaped_spec_passes_the_routine_limits() -> None:
    from src.core.constants import RECURRENCE_ROUTINE_LIMITS

    spec = RecurrenceSpec(
        freq="weekly",
        times=at((8, 0)),
        anchor_date=date(2026, 9, 7),
        byweekday=(1, 2, 3, 4, 5),
    )
    spec.validate_against(RECURRENCE_ROUTINE_LIMITS)


class TestASelectorIsStoredCanonical:
    """A day selector is a SET, so two spellings of it are one recurrence.

    Nothing downstream re-sorts or de-duplicates these tuples: `describe`
    renders `byweekday` in order and produced "le lundi, lundi et mercredi"
    for `(1, 1, 3)`. The engine is immune (dateutil folds duplicates), which
    is exactly why the defect was invisible until someone read the sentence.

    Repairing here rather than refusing follows the doctrine ADR-184 states:
    what is mechanically repairable is repaired before validation, never
    reported as a defect — `[1, 1, 3]` carries no ambiguity about intent.
    """

    def test_duplicate_weekdays_collapse(self) -> None:
        spec = _weekly(byweekday=[1, 1, 3])
        assert spec.byweekday == (1, 3)

    def test_weekdays_are_sorted(self) -> None:
        assert _weekly(byweekday=[5, 1, 3]).byweekday == (1, 3, 5)

    def test_days_of_month_collapse_and_sort(self) -> None:
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "monthly",
                "interval": 1,
                "anchor_date": "2026-03-09",
                "bymonthday": [15, 1, 15],
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
            }
        )
        assert spec.bymonthday == (1, 15)

    def test_months_collapse_and_sort(self) -> None:
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "yearly",
                "interval": 1,
                "anchor_date": "2026-03-09",
                "bymonth": [12, 3, 3],
                "bymonthday": [1],
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
            }
        )
        assert spec.bymonth == (3, 12)

    def test_the_last_day_marker_survives_sorting(self) -> None:
        """-1 means "the last day", not "before the first" — it must remain."""
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "monthly",
                "interval": 1,
                "anchor_date": "2026-03-09",
                "bymonthday": [-1, 1, -1],
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
            }
        )
        assert spec.bymonthday == (1, -1)

    def test_moments_of_a_day_collapse_too(self) -> None:
        """Harmless downstream — `materialise` folds them — but the STORED
        value must still be canonical, or two equal recurrences compare
        unequal and a round-trip is not idempotent."""
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "daily",
                "interval": 1,
                "anchor_date": "2026-03-09",
                "times": {
                    "mode": "at",
                    "at": [
                        {"hour": 9, "minute": 0},
                        {"hour": 8, "minute": 0},
                        {"hour": 9, "minute": 0},
                    ],
                },
            }
        )
        assert spec.times.at == (TimeOfDay(hour=8, minute=0), TimeOfDay(hour=9, minute=0))

    def test_normalisation_is_idempotent(self) -> None:
        once = _weekly(byweekday=[3, 1, 1])
        twice = RecurrenceSpec.model_validate(once.model_dump(mode="json"))
        assert twice == once


def _weekly(*, byweekday: list[int]) -> RecurrenceSpec:
    return RecurrenceSpec.model_validate(
        {
            "freq": "weekly",
            "interval": 1,
            "anchor_date": "2026-03-09",
            "byweekday": byweekday,
            "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
        }
    )


class TestAStoredSelectorIsAReadSelector:
    """A selector the engine ignores must not be storable.

    Measured 2026-09-06, before this rule existed: a `daily` spec carrying
    `byweekday=(1, 2)` validated, `describe` said "every day", and the engine
    fired every day — the two weekdays were accepted, stored, and silently
    thrown away. A `monthly` spec carrying `bymonth=(1, 7)` fired twelve times
    a year instead of two.

    This is the trap ADR-184 names, pointing the other way: there, a bound was
    enforced without being published; here, a value is published without being
    enforced. Both let a producer believe it was obeyed.
    """

    @pytest.mark.parametrize(
        ("label", "kwargs"),
        [
            ("daily with weekdays", {"freq": "daily", "byweekday": [1, 2]}),
            ("daily with a day of month", {"freq": "daily", "bymonthday": [15]}),
            ("daily with months", {"freq": "daily", "bymonth": [1]}),
            ("daily with an nth weekday", {"freq": "daily", "nth_weekday": (2, 2)}),
            ("once with weekdays", {"freq": "once", "byweekday": [1]}),
            (
                "weekly with a day of month",
                {"freq": "weekly", "byweekday": [1], "bymonthday": [15]},
            ),
            ("weekly with months", {"freq": "weekly", "byweekday": [1], "bymonth": [3]}),
            ("monthly with weekdays", {"freq": "monthly", "bymonthday": [1], "byweekday": [2]}),
            ("monthly with months", {"freq": "monthly", "bymonthday": [15], "bymonth": [1, 7]}),
            (
                "yearly with weekdays",
                {"freq": "yearly", "bymonth": [1], "bymonthday": [1], "byweekday": [3]},
            ),
            (
                "yearly with an nth weekday",
                {"freq": "yearly", "bymonth": [1], "bymonthday": [1], "nth_weekday": (1, 1)},
            ),
        ],
    )
    def test_a_selector_the_frequency_never_reads_is_refused(
        self, label: str, kwargs: dict[str, object]
    ) -> None:
        with pytest.raises(ValueError):
            RecurrenceSpec.model_validate(
                {
                    "anchor_date": "2026-09-07",
                    "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                    **kwargs,
                }
            )

    @pytest.mark.parametrize(
        ("label", "kwargs"),
        [
            ("daily", {"freq": "daily"}),
            ("once", {"freq": "once"}),
            ("weekly", {"freq": "weekly", "byweekday": [1, 3]}),
            ("monthly by day", {"freq": "monthly", "bymonthday": [15]}),
            ("monthly by nth", {"freq": "monthly", "nth_weekday": (2, 2)}),
            ("yearly", {"freq": "yearly", "bymonth": [1, 7], "bymonthday": [15]}),
        ],
    )
    def test_every_frequency_still_accepts_its_own_selector(
        self, label: str, kwargs: dict[str, object]
    ) -> None:
        spec = RecurrenceSpec.model_validate(
            {
                "anchor_date": "2026-09-07",
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                **kwargs,
            }
        )
        assert spec.freq == kwargs["freq"]

    def test_an_empty_foreign_selector_is_not_a_foreign_selector(self) -> None:
        """The migrations write every field, empty where it does not apply."""
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "once",
                "anchor_date": "2026-09-07",
                "byweekday": [],
                "bymonthday": [],
                "bymonth": [],
                "nth_weekday": None,
                "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                "end": {"kind": "never", "on_date": None, "after_count": None},
            }
        )
        assert spec.freq == "once"


def test_the_hard_ceiling_produces_the_number_it_declares() -> None:
    """A ceiling of 288 that yields 289 is a ceiling nobody can reason about.

    It only bites below a five-minute step — 288 is a full day at that pace —
    and every consumer's own cap refuses far earlier, so this is exactness
    rather than a behaviour change.
    """
    every_minute = DailyTimes(
        mode="every",
        step_minutes=1,
        start=TimeOfDay(hour=0, minute=0),
        end=TimeOfDay(hour=23, minute=59),
    )
    assert len(every_minute.materialise()) == _HARD_TIMES_CEILING
