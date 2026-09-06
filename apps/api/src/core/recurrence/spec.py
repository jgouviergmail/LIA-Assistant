"""The recurrence vocabulary: one stored shape for every consumer.

Domain-free by construction: nothing here imports ``src.domains``. What a
consumer is allowed to ask for is INJECTED (:class:`RecurrenceLimits`), which
is what lets a routine cap a day at 12 runs and a reminder at 48 with one
engine and no branch.

Two levels of validation, deliberately separated:

- **Structural**, at construction: a shape that could never fire is refused
  here — a weekly rule with no weekday, a monthly rule with two selectors, the
  30th of February. Measured 2026-09-06: that last one validated, cost 166 ms
  and produced nothing, which would have stored a null trigger — a dead
  routine that does not say it is dead.
- **Against the consumer's limits**, explicitly: :meth:`RecurrenceSpec.validate_against`.
  A cap cannot live in the model, or the model would belong to its first
  consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: The most days a month can ever have, by month number. A (month, day) pair
#: absent from every month of a yearly rule can never fire.
MAX_DAY_IN_MONTH: dict[int, int] = {
    1: 31,
    2: 29,
    3: 31,
    4: 30,
    5: 31,
    6: 30,
    7: 31,
    8: 31,
    9: 30,
    10: 31,
    11: 30,
    12: 31,
}

#: The day selectors each frequency actually READS, by field name.
#:
#: The engine builds one `rrule` per frequency and hands it only these; a
#: selector absent from a frequency's set is not "unused", it is DROPPED.
#: Measured 2026-09-06: a `daily` spec carrying `byweekday=(1, 2)` fired every
#: day of the week, and a `monthly` one carrying `bymonth=(1, 7)` fired twelve
#: times a year instead of two — both stored, both displayed as what they
#: really did, neither doing what the value said.
SELECTORS_READ_BY: dict[str, frozenset[str]] = {
    "once": frozenset(),
    "daily": frozenset(),
    "weekly": frozenset({"byweekday"}),
    "monthly": frozenset({"bymonthday", "nth_weekday"}),
    "yearly": frozenset({"bymonth", "bymonthday"}),
}

#: How a recurrence walks the calendar. ``once`` is a recurrence of one.
RecurrenceFreq = Literal["once", "daily", "weekly", "monthly", "yearly"]


class RecurrenceError(ValueError):
    """A recurrence that could never fire, or that exceeds a consumer's limits.

    **What actually reaches a caller differs by validation level**, and the
    difference is Pydantic's, not ours (verified 2026-09-06):

    - raised inside a ``model_validator``, it is WRAPPED into a
      ``pydantic.ValidationError``. That class subclasses ``ValueError``, so
      ``except ValueError`` catches both and FastAPI answers 422 — the same
      contract every other schema in this codebase relies on;
    - raised by :meth:`RecurrenceSpec.validate_against`, which is an ordinary
      method, it reaches the caller as itself.

    A caller that must treat the two alike catches ``ValueError``. The engine
    never raises either: everything refusable was refused at construction.
    """


class TimeOfDay(BaseModel):
    """A wall-clock moment inside a day, in the consumer's timezone."""

    model_config = ConfigDict(frozen=True)

    hour: int = Field(..., ge=0, le=23, description="Hour of day (0-23), wall clock.")
    minute: int = Field(..., ge=0, le=59, description="Minute of hour (0-59).")

    @property
    def minutes_from_midnight(self) -> int:
        """Minutes since local midnight — the total order over a day.

        Returns:
            The moment as a single integer, for sorting and de-duplication.
        """
        return self.hour * 60 + self.minute


def _canonical(values: object) -> object:
    """Fold a day selector to its canonical spelling: sorted, each once.

    A selector is a SET — `[1, 1, 3]` and `[3, 1]` name the same recurrence —
    but a tuple keeps whatever order and repetitions it was given, and every
    reader downstream trusts it. `describe` rendered `(1, 1, 3)` as "le lundi,
    lundi et mercredi"; the engine folded the duplicate silently, which is
    what kept the defect out of sight.

    Negative markers sort LAST: -1 means "the last day of the month", not a
    day before the first, so `[-1, 1]` reads `(1, -1)`.

    Args:
        values: The raw field value, whatever Pydantic was handed.

    Returns:
        The canonical tuple, or the input untouched when it is not a sequence
        of integers — validation, not this repair, owns the refusal.
    """
    if not isinstance(values, (list, tuple)):
        return values
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return values
    return tuple(sorted(set(values), key=lambda v: (v < 0, v)))


class DailyTimes(BaseModel):
    """The moments a SERVED day fires at: explicit, or a step between bounds.

    ``every`` is stored as declared and materialised on every computation.
    Storing the derived list beside the parameters that produced it would be a
    second authority on the same fact.
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["at", "every"] = Field(
        default="at", description="at = explicit moments; every = a step between two bounds."
    )
    at: tuple[TimeOfDay, ...] = Field(default=(), description="mode=at: the moments, in any order.")
    step_minutes: int | None = Field(
        default=None, ge=1, description="mode=every: minutes between two moments."
    )
    start: TimeOfDay | None = Field(default=None, description="mode=every: first moment.")
    end: TimeOfDay | None = Field(default=None, description="mode=every: last moment, included.")

    @model_validator(mode="before")
    @classmethod
    def canonical_moments(cls, data: object) -> object:
        """Fold `at` to sorted, distinct moments.

        `materialise` already folds them for every READER, so this changes no
        behaviour — it makes the STORED value canonical, so two equal
        recurrences compare equal and a round-trip is idempotent.

        Args:
            data: The raw payload.

        Returns:
            The payload, with `at` canonicalised when it carries moments.
        """
        if not isinstance(data, dict) or not isinstance(data.get("at"), (list, tuple)):
            return data
        seen: dict[int, object] = {}
        for raw in data["at"]:
            moment = raw if isinstance(raw, TimeOfDay) else TimeOfDay.model_validate(raw)
            seen.setdefault(moment.minutes_from_midnight, raw)
        return {**data, "at": [seen[key] for key in sorted(seen)]}

    @model_validator(mode="after")
    def validate_mode(self) -> DailyTimes:
        """Each mode needs its own fields, and refuses the other's.

        Returns:
            The validated instance.

        Raises:
            ValidationError: Pydantic wraps the ``RecurrenceError`` raised here
                for a mode whose fields are missing or reversed.
        """
        if self.mode == "at":
            if not self.at:
                raise RecurrenceError("mode=at needs at least one moment")
        else:
            if self.step_minutes is None or self.start is None or self.end is None:
                raise RecurrenceError("mode=every needs step_minutes, start and end")
            if self.end.minutes_from_midnight < self.start.minutes_from_midnight:
                raise RecurrenceError("mode=every needs start <= end")
        return self

    def materialise(self) -> tuple[TimeOfDay, ...]:
        """The moments of one served day: sorted, de-duplicated, bounded.

        The bound is structural rather than a policy: a step of one minute over
        a full day would otherwise build 1 440 moments before any consumer's
        cap could refuse them.

        Returns:
            The moments, ascending, each appearing once.
        """
        if self.mode == "at":
            moments = self.at
        else:
            # Narrowed by `validate_mode`; re-read locally for MyPy.
            step = self.step_minutes
            start = self.start
            end = self.end
            assert step is not None and start is not None and end is not None
            collected: list[TimeOfDay] = []
            cursor = start.minutes_from_midnight
            last = end.minutes_from_midnight
            while cursor <= last and len(collected) < _HARD_TIMES_CEILING:
                collected.append(TimeOfDay(hour=cursor // 60, minute=cursor % 60))
                cursor += step
            moments = tuple(collected)
        unique = sorted({m.minutes_from_midnight for m in moments})
        return tuple(TimeOfDay(hour=k // 60, minute=k % 60) for k in unique)


#: Structural ceiling on the moments of a day, above every consumer's cap.
#: It exists so materialisation cannot build an unbounded list before a
#: consumer's own limit is consulted.
_HARD_TIMES_CEILING = 288


class SeriesEnd(BaseModel):
    """When a series stops: never, on a local date, or after N occurrences."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["never", "on_date", "after_count"] = Field(
        default="never", description="How the series ends."
    )
    on_date: date | None = Field(
        default=None, description="kind=on_date: the LAST local day, included."
    )
    after_count: int | None = Field(
        default=None, ge=1, description="kind=after_count: how many INSTANTS, not days."
    )

    @model_validator(mode="after")
    def validate_kind(self) -> SeriesEnd:
        """Each kind carries its own value and no other.

        Returns:
            The validated instance.

        Raises:
            ValidationError: Pydantic wraps the ``RecurrenceError`` raised here
                for a missing or foreign value.
        """
        if self.kind == "on_date" and self.on_date is None:
            raise RecurrenceError("end kind=on_date needs a date")
        if self.kind == "after_count" and self.after_count is None:
            raise RecurrenceError("end kind=after_count needs a count")
        if self.kind == "never" and (self.on_date is not None or self.after_count is not None):
            raise RecurrenceError("end kind=never carries no value")
        return self


@dataclass(frozen=True, slots=True)
class RecurrenceLimits:
    """What ONE consumer allows. Injected, never hard-coded in the model.

    A routine runs an agent pipeline and a reminder sends a notification: the
    same engine serves both because the ceiling travels with the caller.

    Attributes:
        max_times_per_day: Most moments a served day may carry.
        min_step_minutes: Smallest step ``mode=every`` may declare.
        max_series_count: Largest ``after_count`` a series may declare.
    """

    max_times_per_day: int
    min_step_minutes: int
    max_series_count: int


class RecurrenceSpec(BaseModel):
    """A recurrence: which calendar days, and which moments inside them.

    ``anchor_date`` is BOTH the day the series starts and the phase of an
    interval. Measured 2026-09-06: without it, "every 3 days" resolved to "in 3
    days" from every reference instant, and "every other Tuesday" answered a
    different Tuesday depending on the day it was read — the series was not a
    series at all.
    """

    model_config = ConfigDict(frozen=True)

    freq: RecurrenceFreq = Field(..., description="How the recurrence walks the calendar.")
    times: DailyTimes = Field(..., description="The moments a served day fires at.")
    anchor_date: date = Field(
        ...,
        description="The day the series starts; also the phase when interval > 1.",
    )
    interval: int = Field(default=1, ge=1, description="Every N periods of `freq`.")
    byweekday: tuple[int, ...] = Field(
        default=(), description="freq=weekly: ISO weekdays, 1=Monday..7=Sunday."
    )
    bymonthday: tuple[int, ...] = Field(
        default=(), description="freq=monthly/yearly: 1..31, or -1 for the last day."
    )
    nth_weekday: tuple[int, int] | None = Field(
        default=None,
        description="freq=monthly: (nth, ISO weekday); nth in -1 or 1..5.",
    )
    bymonth: tuple[int, ...] = Field(default=(), description="freq=yearly: months, 1..12.")
    end: SeriesEnd = Field(default_factory=SeriesEnd, description="When the series stops.")

    @model_validator(mode="before")
    @classmethod
    def canonical_selectors(cls, data: object) -> object:
        """Fold every day selector to its canonical spelling before validation.

        Args:
            data: The raw payload.

        Returns:
            The payload, with the three selectors canonicalised.
        """
        if not isinstance(data, dict):
            return data
        present = [name for name in ("byweekday", "bymonthday", "bymonth") if name in data]
        if not present:
            return data
        return {**data, **{name: _canonical(data[name]) for name in present}}

    @model_validator(mode="after")
    def validate_shape(self) -> RecurrenceSpec:
        """Refuse every shape that could never fire.

        Returns:
            The validated instance.

        Raises:
            ValidationError: Pydantic wraps the ``RecurrenceError`` raised by
                the checks below for an incoherent or impossible shape.
        """
        self._validate_selectors()
        self._validate_no_unread_selector()
        self._validate_ranges()
        self._validate_once()
        self._validate_reachable_dates()
        return self

    def _validate_selectors(self) -> None:
        """Each frequency needs its own selector, and refuses the others."""
        if self.freq == "weekly" and not self.byweekday:
            raise RecurrenceError("freq=weekly needs at least one weekday")
        if self.freq == "monthly" and not (self.bymonthday or self.nth_weekday):
            raise RecurrenceError("freq=monthly needs a day of month or an nth weekday")
        if self.freq == "monthly" and self.bymonthday and self.nth_weekday is not None:
            raise RecurrenceError("freq=monthly takes a day of month OR an nth weekday")
        if self.freq == "yearly" and not (self.bymonth and self.bymonthday):
            raise RecurrenceError("freq=yearly needs a month and a day of month")

    def _validate_no_unread_selector(self) -> None:
        """Refuse a selector this frequency would never read.

        Accepting one is worse than useless: it is stored, it is returned by
        the API, an editor renders it — and the engine drops it. The value
        says one schedule while the series runs another, with nothing
        anywhere to reveal the gap.

        Empty is not "given": every migration writes all four fields, empty
        where they do not apply, and a spec must survive its own round-trip.

        Raises:
            RecurrenceError: When a selector foreign to this frequency carries
                a value.
        """
        read = SELECTORS_READ_BY[self.freq]
        given = {
            name
            for name, value in (
                ("byweekday", self.byweekday),
                ("bymonthday", self.bymonthday),
                ("bymonth", self.bymonth),
                ("nth_weekday", self.nth_weekday),
            )
            if value
        }
        unread = sorted(given - read)
        if unread:
            raise RecurrenceError(
                f"freq={self.freq} never reads {', '.join(unread)}; "
                f"it reads {', '.join(sorted(read)) or 'no day selector'}"
            )

    def _validate_ranges(self) -> None:
        """Every selector value inside its own range."""
        if any(not 1 <= day <= 7 for day in self.byweekday):
            raise RecurrenceError("weekday must be 1 (Monday) to 7 (Sunday)")
        if any(day == 0 or day < -1 or day > 31 for day in self.bymonthday):
            raise RecurrenceError("day of month must be 1..31 or -1")
        if any(not 1 <= month <= 12 for month in self.bymonth):
            raise RecurrenceError("month must be 1..12")
        if self.nth_weekday is not None:
            nth, weekday = self.nth_weekday
            if nth == 0 or nth < -1 or nth > 5:
                raise RecurrenceError("nth must be -1 or 1..5")
            if not 1 <= weekday <= 7:
                raise RecurrenceError("weekday must be 1 (Monday) to 7 (Sunday)")

    def _validate_once(self) -> None:
        """A single occurrence has neither an interval nor an end rule."""
        if self.freq != "once":
            return
        if self.interval != 1:
            raise RecurrenceError("freq=once has no interval")
        if self.end.kind != "never":
            raise RecurrenceError("freq=once has no end rule")

    def _validate_reachable_dates(self) -> None:
        """Refuse a (month, day) set no calendar can ever satisfy.

        The rule is existential, not universal: ``bymonth=(2, 3)`` with
        ``bymonthday=(31,)`` is legitimate — the 31st of March exists — while
        ``bymonth=(2,)`` with the same day can never fire.

        Raises:
            RecurrenceError: When no pair is reachable.
        """
        if self.freq != "yearly":
            return
        reachable = any(
            day == -1 or day <= MAX_DAY_IN_MONTH[month]
            for month in self.bymonth
            for day in self.bymonthday
        )
        if not reachable:
            raise RecurrenceError("no calendar date matches these months and days of month")

    def per_day(self) -> int:
        """How many moments a SERVED day carries.

        A clock change makes the REAL count differ on one day a year (24
        declared, 23 served at the spring transition), so a consumer showing
        this must word it as an upper bound.

        Returns:
            The number of moments a served day fires at.
        """
        return len(self.times.materialise())

    def validate_against(self, limits: RecurrenceLimits) -> None:
        """Refuse a spec that exceeds ONE consumer's limits.

        Args:
            limits: What this consumer allows.

        Raises:
            RecurrenceError: When the spec exceeds any of them.
        """
        moments = self.per_day()
        if moments > limits.max_times_per_day:
            raise RecurrenceError(
                f"{moments} times a day exceeds the limit of {limits.max_times_per_day}"
            )
        if (
            self.times.mode == "every"
            and self.times.step_minutes is not None
            and self.times.step_minutes < limits.min_step_minutes
        ):
            raise RecurrenceError(
                f"a step of {self.times.step_minutes} min is below the "
                f"minimum of {limits.min_step_minutes} min"
            )
        if (
            self.end.kind == "after_count"
            and self.end.after_count is not None
            and self.end.after_count > limits.max_series_count
        ):
            raise RecurrenceError(
                f"a series of {self.end.after_count} exceeds the limit "
                f"of {limits.max_series_count}"
            )
