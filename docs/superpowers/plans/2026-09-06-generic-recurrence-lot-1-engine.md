# Generic Recurrence — Lot 1: the engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, **inline** (owner directive: no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A domain-free recurrence component — `src/core/recurrence/` — that
turns a stored specification into the instants it fires at, in a timezone,
with every invariant of the design proven by a test.

**Architecture:** A recurrence is `[calendar days] × [times of day]`. The day
axis is computed by `dateutil.rrule` (already a dependency) over **naive local
wall clock**; each day's times are a bounded list; every wall clock is
localised with `fold=0` and the result is sorted and de-duplicated **by
instant**. Nothing here imports a domain: the caps a consumer enforces are
**injected** (`RecurrenceLimits`), which is what lets a routine allow 12 runs a
day and a reminder 48 with one engine.

**Tech Stack:** Python 3.14, Pydantic v2, `dateutil.rrule` 2.9.0.post0,
`zoneinfo`, pytest (`asyncio_mode = "auto"`), MyPy strict, Black (line-length
100), Ruff.

**Spec:** `docs/superpowers/specs/2026-09-06-generic-recurrence-design.md`

## Global Constraints

- **Never `git commit` / `git push`** (owner rule). Every "Commit" step below is replaced by **"Run the gate"**.
- **No subagents** (owner rule): execute inline.
- `src/core/recurrence/` imports **nothing** from `src/domains/` — asserted by a test in this lot.
- File-size ratchet: no file above **600 logical SLOC** (`scripts/audit/measure_sloc.py` semantics). `core/i18n_*` is a data module and is exempt.
- MyPy strict: full type hints on every function (args + return), PEP 604 `X | None`, no `Any`, no bare `cast`.
- Google-style docstrings with Args/Returns/Raises; module docstring on every file. **English only.**
- All datetimes timezone-aware UTC. `datetime.utcnow()`, naive `now()` and `date.today()` are forbidden (AST guard `test_no_hardcoded_timezone_guard.py`).
- No user-visible string inline in Python: wording lives in `src/core/i18n_recurrence.py`, keyed on the **backend-canonical** language (`zh-CN`, never `zh`), reached through `normalize_language`.
- `structlog.get_logger(__name__)` only; never `print()`.
- No empty `except: pass` (AST guard `test_no_empty_except_guard.py`).
- Tests mirror the source tree: `apps/api/tests/unit/core/recurrence/`.
- Run everything from `apps/api` with `.venv/Scripts/pytest`.

## File Structure

| File | Responsibility |
|---|---|
| `src/core/recurrence/__init__.py` | The public API, and the only import surface consumers use |
| `src/core/recurrence/spec.py` | The vocabulary: `TimeOfDay`, `DailyTimes`, `SeriesEnd`, `RecurrenceSpec`, `RecurrenceLimits`, `RecurrenceError`. Structural validation. |
| `src/core/recurrence/engine.py` | `series`, `occurrences`, `next_occurrence`, `slots_between`. No wording, no I/O. |
| `src/core/recurrence/display.py` | `describe(spec, language)` — the sentence, composed from parts |
| `src/core/i18n_recurrence.py` | The 6-language tables (data module, ratchet-exempt) |
| `src/core/constants.py` | Default caps (modified) |
| `tests/unit/core/recurrence/test_spec.py` | Vocabulary and structural refusals |
| `tests/unit/core/recurrence/test_engine.py` | Coverage, DST, order, end of series, cost |
| `tests/unit/core/recurrence/test_display.py` | The composed sentence in 6 languages |
| `tests/unit/core/recurrence/test_no_domain_import.py` | The genericity boundary |
| `tests/unit/core/recurrence/test_legacy_equivalence.py` | Differential vs the current engine |

Three source files rather than one: the spec estimates ~250 + ~200 + ~150
logical SLOC, and one file would sit at the ratchet's edge on the first
extension.

---

### Task 1: The vocabulary and its structural refusals

**Files:**
- Create: `apps/api/src/core/recurrence/__init__.py`
- Create: `apps/api/src/core/recurrence/spec.py`
- Test: `apps/api/tests/unit/core/recurrence/__init__.py` (empty)
- Test: `apps/api/tests/unit/core/recurrence/test_spec.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `RecurrenceError(ValueError)`
  - `TimeOfDay(hour: int, minute: int)` with `minutes_from_midnight: int`
  - `DailyTimes(mode: Literal["at", "every"], at: tuple[TimeOfDay, ...], step_minutes: int | None, start: TimeOfDay | None, end: TimeOfDay | None)` with `materialise() -> tuple[TimeOfDay, ...]`
  - `SeriesEnd(kind: Literal["never", "on_date", "after_count"], on_date: date | None, after_count: int | None)`
  - `RecurrenceFreq = Literal["once", "daily", "weekly", "monthly", "yearly"]`
  - `RecurrenceSpec(freq, times, anchor_date, interval, byweekday, bymonthday, nth_weekday, bymonth, end)` with `per_day() -> int`
  - `RecurrenceLimits(max_times_per_day: int, min_step_minutes: int, max_series_count: int)`
  - `RecurrenceSpec.validate_against(limits: RecurrenceLimits) -> None`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/core/recurrence/__init__.py` (empty file), then
`apps/api/tests/unit/core/recurrence/test_spec.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/test_spec.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'src.core.recurrence'`.

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/core/recurrence/spec.py`:

```python
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
            while cursor <= last and len(collected) <= _HARD_TIMES_CEILING:
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
```

Create `apps/api/src/core/recurrence/__init__.py`:

```python
"""Generic recurrence: a stored specification, and the instants it fires at.

The single import surface for every consumer. Nothing in this package imports
``src.domains`` — the caps a consumer enforces are injected
(:class:`RecurrenceLimits`), so one engine serves a routine capped at 12 runs a
day and a reminder capped at 48.
"""

from src.core.recurrence.spec import (
    MAX_DAY_IN_MONTH,
    DailyTimes,
    RecurrenceError,
    RecurrenceFreq,
    RecurrenceLimits,
    RecurrenceSpec,
    SeriesEnd,
    TimeOfDay,
)

__all__ = [
    "MAX_DAY_IN_MONTH",
    "DailyTimes",
    "RecurrenceError",
    "RecurrenceFreq",
    "RecurrenceLimits",
    "RecurrenceSpec",
    "SeriesEnd",
    "TimeOfDay",
]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/test_spec.py -v
```

Expected: PASS, 8 tests + 11 parametrized refusals.

- [ ] **Step 5: Run the gate** (replaces "Commit" — owner rule: never `git commit`)

```bash
cd apps/api && .venv/Scripts/black --check src/core/recurrence tests/unit/core/recurrence \
  && .venv/Scripts/ruff check src/core/recurrence tests/unit/core/recurrence \
  && .venv/Scripts/mypy src/core/recurrence
```

Expected: all three clean. Report the exact output; do not proceed on a warning.

---

### Task 2: The engine — days × moments, localised and ordered by instant

**Files:**
- Create: `apps/api/src/core/recurrence/engine.py`
- Modify: `apps/api/src/core/recurrence/__init__.py`
- Test: `apps/api/tests/unit/core/recurrence/test_engine.py`

**Interfaces:**
- Consumes: everything Task 1 produced.
- Produces:
  - `series(spec: RecurrenceSpec, tz: ZoneInfo, *, from_day: date | None = None) -> Iterator[datetime]`
  - `occurrences(spec: RecurrenceSpec, timezone: str, *, after: datetime, count: int) -> list[datetime]`
  - `next_occurrence(spec: RecurrenceSpec, timezone: str, *, after: datetime) -> datetime | None`
  - `slots_between(spec: RecurrenceSpec, timezone: str, *, start: datetime, end: datetime, cap: int = 1000) -> list[datetime]`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/core/recurrence/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/test_engine.py -v
```

Expected: collection error — `ImportError: cannot import name 'occurrences' from 'src.core.recurrence'`.

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/core/recurrence/engine.py`:

```python
"""Turning a recurrence into the instants it fires at.

The engine never raises: every refusable shape was refused by
:mod:`src.core.recurrence.spec` at construction.

Three invariants, each paid for by a measurement (2026-09-06):

- **The days are enumerated, never delegated to a cron.** APScheduler skips the
  day after a transition whose offset changes at local midnight — 142 runs a
  year across 73 zones, `Europe/Paris` included, silently.
- **A wall clock becomes an instant with ``fold=0``.** A time that does not
  exist lands on the first instant that does, which is the shift the previous
  engine already performed.
- **The result is ordered and de-duplicated by INSTANT.** At the spring
  transition two wall-clock times collapse onto one instant, and a later one
  can precede an earlier one (02:30 to 01:30Z, then 03:00 to 01:00Z).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import DAILY, MONTHLY, WEEKLY, YEARLY, rrule
from dateutil.rrule import weekday as rrule_weekday

from src.core.recurrence.spec import RecurrenceSpec, TimeOfDay

#: Most day-rule steps walked before giving up. A legal rule reaches its next
#: occurrence in a handful of steps (the rarest measured, a leap day every four
#: years, takes one); this only stops a pathological one from spinning.
_SCAN_DAY_BUDGET = 4000

#: Days of margin when fast-forwarding. A clock change can move an instant
#: across local midnight; the caller filters on the instant anyway.
_FAST_FORWARD_MARGIN_DAYS = 1


def _day_rule(spec: RecurrenceSpec) -> rrule:
    """The DAY axis of a recurrence, in naive local wall clock.

    Args:
        spec: The recurrence.

    Returns:
        A rule yielding one naive datetime per served day.
    """
    start = datetime.combine(spec.anchor_date, time(0, 0))
    if spec.freq == "once":
        return rrule(DAILY, dtstart=start, count=1)
    if spec.freq == "daily":
        return rrule(DAILY, interval=spec.interval, dtstart=start)
    if spec.freq == "weekly":
        return rrule(
            WEEKLY,
            interval=spec.interval,
            dtstart=start,
            byweekday=[day - 1 for day in sorted(spec.byweekday)],
            wkst=0,
        )
    if spec.freq == "monthly":
        if spec.nth_weekday is not None:
            nth, weekday = spec.nth_weekday
            return rrule(
                MONTHLY,
                interval=spec.interval,
                dtstart=start,
                byweekday=rrule_weekday(weekday - 1, nth),
            )
        return rrule(
            MONTHLY,
            interval=spec.interval,
            dtstart=start,
            bymonthday=sorted(spec.bymonthday),
        )
    return rrule(
        YEARLY,
        interval=spec.interval,
        dtstart=start,
        bymonth=sorted(spec.bymonth),
        bymonthday=sorted(spec.bymonthday),
    )


def _instant(day: date, moment: TimeOfDay, tz: ZoneInfo) -> datetime:
    """The UTC instant of a wall-clock moment on a local day.

    ``fold=0`` resolves a non-existent wall clock to the first instant that
    exists, and an ambiguous one to its FIRST occurrence — so the repeated hour
    of an autumn transition fires once, not twice.

    Args:
        day: The local calendar day.
        moment: The wall-clock moment.
        tz: The zone the wall clock is read in.

    Returns:
        The instant, in UTC.
    """
    wall = datetime.combine(day, time(moment.hour, moment.minute), tzinfo=tz).replace(fold=0)
    return wall.astimezone(UTC)


def series(
    spec: RecurrenceSpec, tz: ZoneInfo, *, from_day: date | None = None
) -> Iterator[datetime]:
    """The series, ascending and de-duplicated by instant. Lazy.

    Args:
        spec: The recurrence.
        tz: The zone its wall clocks are read in.
        from_day: Skip the day rule ahead to this local day instead of walking
            it from the anchor. Ignored for an ``after_count`` series, whose
            count is defined from the beginning — and which is bounded by that
            very count, so walking it is cheap.

    Yields:
        Every instant of the series, in order.
    """
    moments = spec.times.materialise()
    limit = spec.end.after_count if spec.end.kind == "after_count" else None
    last_day = spec.end.on_date if spec.end.kind == "on_date" else None

    if limit is not None or from_day is None:
        walker: Iterator[datetime] = iter(_day_rule(spec))
    else:
        floor = datetime.combine(from_day, time(0, 0))
        walker = _day_rule(spec).xafter(floor, inc=True)

    emitted = 0
    scanned = 0
    seen: set[datetime] = set()
    for naive_day in walker:
        scanned += 1
        if scanned > _SCAN_DAY_BUDGET:
            return
        day = naive_day.date()
        if last_day is not None and day > last_day:
            return
        for instant in sorted(_instant(day, moment, tz) for moment in moments):
            if instant in seen:
                continue
            seen.add(instant)
            yield instant
            emitted += 1
            if limit is not None and emitted >= limit:
                return


def occurrences(
    spec: RecurrenceSpec, timezone: str, *, after: datetime, count: int
) -> list[datetime]:
    """The next ``count`` instants STRICTLY after ``after``.

    Strict is the single convention of this package. The engine it replaces
    mixed both: its listing included its own reference while its re-arm forced
    strictness with a microsecond.

    Args:
        spec: The recurrence.
        timezone: IANA zone its wall clocks are read in.
        after: Reference instant (UTC); the result is strictly later.
        count: How many instants to return.

    Returns:
        Up to ``count`` instants, ascending. Empty when the series is over.

    Raises:
        ValueError: If ``count`` is not positive.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    tz = ZoneInfo(timezone)
    from_day = (after.astimezone(tz) - timedelta(days=_FAST_FORWARD_MARGIN_DAYS)).date()
    found: list[datetime] = []
    for instant in series(spec, tz, from_day=from_day):
        if instant > after:
            found.append(instant)
            if len(found) >= count:
                break
    return found


def next_occurrence(spec: RecurrenceSpec, timezone: str, *, after: datetime) -> datetime | None:
    """The next instant strictly after ``after``, or ``None`` when none remains.

    Args:
        spec: The recurrence.
        timezone: IANA zone.
        after: Reference instant (UTC).

    Returns:
        The instant, or ``None`` for an exhausted or past series — which a
        consumer stores as a null trigger.
    """
    found = occurrences(spec, timezone, after=after, count=1)
    return found[0] if found else None


def slots_between(
    spec: RecurrenceSpec, timezone: str, *, start: datetime, end: datetime, cap: int = 1000
) -> list[datetime]:
    """Every instant in ``[start, end)``.

    The same series :func:`occurrences` walks, by construction — a second
    implementation would be a second authority, and the weekly grid colours its
    cells by EQUALITY with these instants.

    Args:
        spec: The recurrence.
        timezone: IANA zone.
        start: Window start (UTC), included.
        end: Window end (UTC), excluded.
        cap: Most instants to return; a window larger than the caller expects
            is truncated rather than unbounded.

    Returns:
        The instants, ascending.
    """
    tz = ZoneInfo(timezone)
    from_day = (start.astimezone(tz) - timedelta(days=_FAST_FORWARD_MARGIN_DAYS)).date()
    found: list[datetime] = []
    for instant in series(spec, tz, from_day=from_day):
        if instant >= end:
            break
        if instant >= start:
            found.append(instant)
            if len(found) >= cap:
                break
    return found
```

Do **not** edit `__init__.py` yet. It imports `display`, which Task 4 creates;
adding the engine imports now would leave the package unimportable between the
two tasks. Task 4 writes the file whole. Until then, `test_engine.py` imports
work because Python resolves `src.core.recurrence.engine` directly.

If you prefer a green `__init__.py` at every step, run Task 4 before Task 3 —
the two are independent.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/ -v
```

Expected: PASS. If `test_a_sub_daily_rule_never_goes_backwards_or_repeats`
fails on the count, print the instants and check them against the measurement
in the design document (§4.4) before changing the assertion — the number is a
measurement, not a preference.

- [ ] **Step 5: Run the gate**

```bash
cd apps/api && .venv/Scripts/black --check src/core/recurrence tests/unit/core/recurrence \
  && .venv/Scripts/ruff check src/core/recurrence tests/unit/core/recurrence \
  && .venv/Scripts/mypy src/core/recurrence
cd ../.. && apps/api/.venv/Scripts/python scripts/audit/measure_sloc.py apps/api/src/core/recurrence
```

Expected: clean, and every file under 600 logical SLOC. `measure_sloc.py` takes
ONE path argument (verified: `sys.argv[1]`, defaulting to the whole source
tree), so it runs from the repo root with an explicit path.

---

### Task 3: The genericity boundary, asserted

**Files:**
- Test: `apps/api/tests/unit/core/recurrence/test_no_domain_import.py`

**Interfaces:**
- Consumes: the package from Tasks 1-2.
- Produces: nothing (a guard).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/core/recurrence/test_no_domain_import.py`:

```python
"""The genericity boundary — asserted, not promised.

`core/recurrence` must serve consumers that do not exist yet. A single import
of `src.domains` would make it the property of its first consumer, and the
second one would inherit a dependency it has no use for.

An AST check rather than a runtime one: an import inside a function body would
survive `import src.core.recurrence` and still tie the package to a domain.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[4] / "src" / "core" / "recurrence"

#: Import roots the package may never reach for, at any depth.
FORBIDDEN_ROOTS = ("src.domains", "src.infrastructure", "src.api")


def _imported_modules(source: str) -> list[str]:
    """Every module name a file imports, `from` and plain, at any depth."""
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.append(node.module)
    return found


def test_the_package_exists() -> None:
    assert PACKAGE.is_dir(), f"{PACKAGE} not found"
    assert sorted(p.name for p in PACKAGE.glob("*.py")) == [
        "__init__.py",
        "display.py",
        "engine.py",
        "spec.py",
    ]


def test_no_module_imports_a_domain() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        for module in _imported_modules(path.read_text(encoding="utf-8")):
            if module.startswith(FORBIDDEN_ROOTS):
                offenders.append(f"{path.name}: {module}")
    assert offenders == [], (
        "core/recurrence must stay domain-free so a future consumer inherits "
        f"no dependency: {offenders}"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/test_no_domain_import.py -v
```

Expected: `test_the_package_exists` FAILS — `display.py` does not exist yet.
`test_no_module_imports_a_domain` passes already, which is the point: it must
keep passing for the life of the package.

- [ ] **Step 3: No implementation yet**

The failure is the specification for Task 4. Leave it red and move on — Task 4
Step 4 is where both turn green.

- [ ] **Step 4: Run the gate**

```bash
cd apps/api && .venv/Scripts/black --check tests/unit/core/recurrence \
  && .venv/Scripts/ruff check tests/unit/core/recurrence
```

Expected: clean (the test file itself, not the missing module).

---

### Task 4: The sentence, composed and localised

**Files:**
- Create: `apps/api/src/core/i18n_recurrence.py`
- Create: `apps/api/src/core/recurrence/display.py`
- Modify: `apps/api/src/core/recurrence/__init__.py`
- Test: `apps/api/tests/unit/core/recurrence/test_display.py`

**Interfaces:**
- Consumes: `RecurrenceSpec` (Task 1).
- Produces:
  - `describe(spec: RecurrenceSpec, language: str) -> str`
  - `src.core.i18n_recurrence.RECURRENCE_PARTS: dict[str, dict[str, str]]`
  - `src.core.i18n_recurrence.get_recurrence_part(key: str, language: str | None) -> str`

**Why composed and not enumerated:** the space is
freq × interval × selector × times × end. One key per shape would be hundreds
of keys in six languages. The sentence is assembled from four clauses, each a
key.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/core/recurrence/test_display.py`:

```python
"""The recurrence sentence: composed from parts, in the six languages."""

from datetime import date

import pytest

from src.core.i18n_recurrence import RECURRENCE_PARTS
from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay, describe

LANGUAGES = ("fr", "en", "es", "de", "it", "zh-CN")


def at(*pairs: tuple[int, int]) -> DailyTimes:
    return DailyTimes(mode="at", at=tuple(TimeOfDay(hour=h, minute=m) for h, m in pairs))


def test_every_language_declares_every_part() -> None:
    """Strict key parity across the six languages — the repo's i18n rule."""
    reference = set(RECURRENCE_PARTS["en"])
    for language in LANGUAGES:
        assert set(RECURRENCE_PARTS[language]) == reference, f"{language} drifted"


def test_daily_single_time_french() -> None:
    spec = RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 9, 6))
    assert describe(spec, "fr") == "Tous les jours à 08:00"


def test_daily_several_times_french() -> None:
    spec = RecurrenceSpec(
        freq="daily", times=at((8, 0), (12, 30), (19, 0)), anchor_date=date(2026, 9, 6)
    )
    assert describe(spec, "fr") == "Tous les jours à 08:00, 12:30 et 19:00"


def test_interval_is_stated_french() -> None:
    spec = RecurrenceSpec(
        freq="weekly",
        times=at((9, 0)),
        anchor_date=date(2026, 9, 8),
        interval=2,
        byweekday=(2,),
    )
    assert describe(spec, "fr") == "Toutes les 2 semaines, le mardi, à 09:00"


def test_a_step_is_stated_french() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=120,
            start=TimeOfDay(hour=8, minute=0),
            end=TimeOfDay(hour=20, minute=0),
        ),
        anchor_date=date(2026, 9, 6),
    )
    assert describe(spec, "fr") == "Tous les jours, toutes les 2 h, de 08:00 à 20:00"


def test_day_of_month_french() -> None:
    spec = RecurrenceSpec(
        freq="monthly", times=at((10, 0)), anchor_date=date(2026, 9, 1), bymonthday=(15,)
    )
    assert describe(spec, "fr") == "Le 15 de chaque mois, à 10:00"


def test_last_day_of_month_french() -> None:
    spec = RecurrenceSpec(
        freq="monthly", times=at((23, 30)), anchor_date=date(2026, 9, 1), bymonthday=(-1,)
    )
    assert describe(spec, "fr") == "Le dernier jour du mois, à 23:30"


def test_single_occurrence_french() -> None:
    spec = RecurrenceSpec(freq="once", times=at((9, 0)), anchor_date=date(2026, 9, 12))
    assert describe(spec, "fr") == "Une seule fois, le 12/09/2026, à 09:00"


def test_end_on_date_is_appended_french() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=at((8, 0)),
        anchor_date=date(2026, 9, 6),
        end=SeriesEnd(kind="on_date", on_date=date(2026, 12, 31)),
    )
    assert describe(spec, "fr") == "Tous les jours à 08:00, jusqu'au 31/12/2026"


def test_end_after_count_is_appended_french() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=at((8, 0)),
        anchor_date=date(2026, 9, 6),
        end=SeriesEnd(kind="after_count", after_count=10),
    )
    assert describe(spec, "fr") == "Tous les jours à 08:00, 10 fois"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_shape_renders_in_every_language(language: str) -> None:
    """No shape may fall back to a key, an empty string, or a brace."""
    shapes = [
        RecurrenceSpec(freq="once", times=at((9, 0)), anchor_date=date(2026, 9, 12)),
        RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 9, 6)),
        RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 9, 6), interval=3),
        RecurrenceSpec(
            freq="weekly",
            times=at((9, 0)),
            anchor_date=date(2026, 9, 8),
            interval=2,
            byweekday=(1, 4),
        ),
        RecurrenceSpec(
            freq="monthly",
            times=at((10, 0)),
            anchor_date=date(2026, 9, 1),
            bymonthday=(15,),
        ),
        RecurrenceSpec(
            freq="monthly",
            times=at((10, 0)),
            anchor_date=date(2026, 9, 1),
            nth_weekday=(2, 2),
        ),
        RecurrenceSpec(
            freq="yearly",
            times=at((18, 0)),
            anchor_date=date(2026, 12, 24),
            bymonth=(12,),
            bymonthday=(24,),
        ),
        RecurrenceSpec(
            freq="daily",
            times=DailyTimes(
                mode="every",
                step_minutes=30,
                start=TimeOfDay(hour=9, minute=0),
                end=TimeOfDay(hour=11, minute=0),
            ),
            anchor_date=date(2026, 9, 6),
            end=SeriesEnd(kind="after_count", after_count=5),
        ),
    ]
    for spec in shapes:
        sentence = describe(spec, language)
        assert sentence, f"{language}: empty sentence for {spec.freq}"
        assert "{" not in sentence and "}" not in sentence, f"{language}: unfilled placeholder"
        assert "recurrence." not in sentence, f"{language}: raw key leaked"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/test_display.py -v
```

Expected: collection error — `No module named 'src.core.i18n_recurrence'`.

- [ ] **Step 3: Write the implementation**

Create `apps/api/src/core/i18n_recurrence.py`:

```python
"""Central i18n for the generic recurrence component.

Data module (like the sibling ``core/i18n_*``): no domain imports, exempt from
the size ratchet.

The sentence is COMPOSED, never enumerated. The shape space is
freq × interval × selector × times × end; one key per shape would be hundreds
of entries in six languages, and the seventh consumer would add hundreds more.
Four clauses, each a key, assembled by :mod:`src.core.recurrence.display`.

Keyed on the backend-canonical language (``zh-CN``, never ``zh``), reached
through ``normalize_language`` — the single chokepoint.
"""

from __future__ import annotations

#: Every clause of a recurrence sentence, by canonical language.
#:
#: Placeholders: ``{n}`` a count, ``{days}`` a day list, ``{times}`` a moment
#: list, ``{from}``/``{to}`` step bounds, ``{step}`` a step, ``{date}`` a date,
#: ``{day}`` a day of month, ``{month}`` a month name, ``{weekday}`` a weekday.
RECURRENCE_PARTS: dict[str, dict[str, str]] = {
    "fr": {
        "once": "Une seule fois, le {date}",
        "daily": "Tous les jours",
        "daily_n": "Tous les {n} jours",
        "weekly": "Toutes les semaines, le {days}",
        "weekly_n": "Toutes les {n} semaines, le {days}",
        "monthly_day": "Le {day} de chaque mois",
        "monthly_day_n": "Le {day} tous les {n} mois",
        "monthly_last": "Le dernier jour du mois",
        "monthly_last_n": "Le dernier jour, tous les {n} mois",
        "monthly_nth": "Le {nth} {weekday} de chaque mois",
        "monthly_nth_n": "Le {nth} {weekday}, tous les {n} mois",
        "yearly": "Tous les ans, le {day} {month}",
        "yearly_n": "Tous les {n} ans, le {day} {month}",
        "at_times": "à {times}",
        "every_step": "toutes les {step}, de {from} à {to}",
        "end_on_date": "jusqu'au {date}",
        "end_after_count": "{n} fois",
        "nth_1": "1er",
        "nth_2": "2e",
        "nth_3": "3e",
        "nth_4": "4e",
        "nth_5": "5e",
        "nth_last": "dernier",
        "step_hours": "{n} h",
        "step_minutes": "{n} min",
        "list_separator": ", ",
        "list_last": " et ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "en": {
        "once": "Once, on {date}",
        "daily": "Every day",
        "daily_n": "Every {n} days",
        "weekly": "Every week, on {days}",
        "weekly_n": "Every {n} weeks, on {days}",
        "monthly_day": "On the {day} of every month",
        "monthly_day_n": "On the {day}, every {n} months",
        "monthly_last": "On the last day of the month",
        "monthly_last_n": "On the last day, every {n} months",
        "monthly_nth": "On the {nth} {weekday} of every month",
        "monthly_nth_n": "On the {nth} {weekday}, every {n} months",
        "yearly": "Every year, on {month} {day}",
        "yearly_n": "Every {n} years, on {month} {day}",
        "at_times": "at {times}",
        "every_step": "every {step}, from {from} to {to}",
        "end_on_date": "until {date}",
        "end_after_count": "{n} times",
        "nth_1": "1st",
        "nth_2": "2nd",
        "nth_3": "3rd",
        "nth_4": "4th",
        "nth_5": "5th",
        "nth_last": "last",
        "step_hours": "{n} h",
        "step_minutes": "{n} min",
        "list_separator": ", ",
        "list_last": " and ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "es": {
        "once": "Una sola vez, el {date}",
        "daily": "Todos los días",
        "daily_n": "Cada {n} días",
        "weekly": "Cada semana, el {days}",
        "weekly_n": "Cada {n} semanas, el {days}",
        "monthly_day": "El {day} de cada mes",
        "monthly_day_n": "El {day}, cada {n} meses",
        "monthly_last": "El último día del mes",
        "monthly_last_n": "El último día, cada {n} meses",
        "monthly_nth": "El {nth} {weekday} de cada mes",
        "monthly_nth_n": "El {nth} {weekday}, cada {n} meses",
        "yearly": "Cada año, el {day} de {month}",
        "yearly_n": "Cada {n} años, el {day} de {month}",
        "at_times": "a las {times}",
        "every_step": "cada {step}, de {from} a {to}",
        "end_on_date": "hasta el {date}",
        "end_after_count": "{n} veces",
        "nth_1": "1.º",
        "nth_2": "2.º",
        "nth_3": "3.º",
        "nth_4": "4.º",
        "nth_5": "5.º",
        "nth_last": "último",
        "step_hours": "{n} h",
        "step_minutes": "{n} min",
        "list_separator": ", ",
        "list_last": " y ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "de": {
        "once": "Einmalig, am {date}",
        "daily": "Täglich",
        "daily_n": "Alle {n} Tage",
        "weekly": "Wöchentlich, am {days}",
        "weekly_n": "Alle {n} Wochen, am {days}",
        "monthly_day": "Am {day}. jedes Monats",
        "monthly_day_n": "Am {day}., alle {n} Monate",
        "monthly_last": "Am letzten Tag des Monats",
        "monthly_last_n": "Am letzten Tag, alle {n} Monate",
        "monthly_nth": "Am {nth} {weekday} jedes Monats",
        "monthly_nth_n": "Am {nth} {weekday}, alle {n} Monate",
        "yearly": "Jährlich, am {day}. {month}",
        "yearly_n": "Alle {n} Jahre, am {day}. {month}",
        "at_times": "um {times}",
        "every_step": "alle {step}, von {from} bis {to}",
        "end_on_date": "bis zum {date}",
        "end_after_count": "{n}-mal",
        "nth_1": "1.",
        "nth_2": "2.",
        "nth_3": "3.",
        "nth_4": "4.",
        "nth_5": "5.",
        "nth_last": "letzten",
        "step_hours": "{n} Std.",
        "step_minutes": "{n} Min.",
        "list_separator": ", ",
        "list_last": " und ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "it": {
        "once": "Una sola volta, il {date}",
        "daily": "Tutti i giorni",
        "daily_n": "Ogni {n} giorni",
        "weekly": "Ogni settimana, il {days}",
        "weekly_n": "Ogni {n} settimane, il {days}",
        "monthly_day": "Il {day} di ogni mese",
        "monthly_day_n": "Il {day}, ogni {n} mesi",
        "monthly_last": "L'ultimo giorno del mese",
        "monthly_last_n": "L'ultimo giorno, ogni {n} mesi",
        "monthly_nth": "Il {nth} {weekday} di ogni mese",
        "monthly_nth_n": "Il {nth} {weekday}, ogni {n} mesi",
        "yearly": "Ogni anno, il {day} {month}",
        "yearly_n": "Ogni {n} anni, il {day} {month}",
        "at_times": "alle {times}",
        "every_step": "ogni {step}, dalle {from} alle {to}",
        "end_on_date": "fino al {date}",
        "end_after_count": "{n} volte",
        "nth_1": "1º",
        "nth_2": "2º",
        "nth_3": "3º",
        "nth_4": "4º",
        "nth_5": "5º",
        "nth_last": "ultimo",
        "step_hours": "{n} h",
        "step_minutes": "{n} min",
        "list_separator": ", ",
        "list_last": " e ",
        "clause_join": ", ",
        "clause_join_tight": " ",
    },
    "zh-CN": {
        "once": "仅一次，{date}",
        "daily": "每天",
        "daily_n": "每 {n} 天",
        "weekly": "每周 {days}",
        "weekly_n": "每 {n} 周的 {days}",
        "monthly_day": "每月 {day} 日",
        "monthly_day_n": "每 {n} 个月的 {day} 日",
        "monthly_last": "每月最后一天",
        "monthly_last_n": "每 {n} 个月的最后一天",
        "monthly_nth": "每月第 {nth} 个{weekday}",
        "monthly_nth_n": "每 {n} 个月的第 {nth} 个{weekday}",
        "yearly": "每年 {month}{day} 日",
        "yearly_n": "每 {n} 年的 {month}{day} 日",
        "at_times": "{times}",
        "every_step": "每 {step}，从 {from} 到 {to}",
        "end_on_date": "直到 {date}",
        "end_after_count": "共 {n} 次",
        "nth_1": "1",
        "nth_2": "2",
        "nth_3": "3",
        "nth_4": "4",
        "nth_5": "5",
        "nth_last": "最后一",
        "step_hours": "{n} 小时",
        "step_minutes": "{n} 分钟",
        "list_separator": "、",
        "list_last": "和",
        "clause_join": "，",
        "clause_join_tight": "",
    },
}


def get_recurrence_part(key: str, language: str | None) -> str:
    """One clause of a recurrence sentence, in the reader's language.

    Args:
        key: A key of :data:`RECURRENCE_PARTS`.
        language: Any raw locale — normalized through the single chokepoint.

    Returns:
        The clause, English as the last resort.
    """
    from src.core.i18n import DEFAULT_LANGUAGE, normalize_language

    canonical = normalize_language(language or DEFAULT_LANGUAGE)
    table = RECURRENCE_PARTS.get(canonical, RECURRENCE_PARTS["en"])
    return table.get(key, RECURRENCE_PARTS["en"][key])
```

Create `apps/api/src/core/recurrence/display.py`:

```python
"""The recurrence sentence, composed from localized clauses.

Four clauses in order — the calendar clause, the time clause, and the end
clause — assembled here and worded in :mod:`src.core.i18n_recurrence`. No
wording is ever written in this file: it is the assembly, not the vocabulary.

Day and month names come from ``core.i18n_dates``, so no day name is declared
twice in the codebase.
"""

from __future__ import annotations

from datetime import date

from src.core.i18n_recurrence import get_recurrence_part
from src.core.recurrence.spec import RecurrenceSpec, TimeOfDay


def _join(parts: list[str], language: str) -> str:
    """Join a list the way the reader's language does ("a, b et c").

    Args:
        parts: Already-worded items, in order.
        language: The reader's language.

    Returns:
        The joined list; the last separator differs from the others.
    """
    if len(parts) <= 1:
        return parts[0] if parts else ""
    separator = get_recurrence_part("list_separator", language)
    last = get_recurrence_part("list_last", language)
    return separator.join(parts[:-1]) + last + parts[-1]


def _clock(moment: TimeOfDay) -> str:
    """A moment as `HH:MM` — digits, identical in every language."""
    return f"{moment.hour:02d}:{moment.minute:02d}"


def _format_date(day: date) -> str:
    """A calendar date as `DD/MM/YYYY`."""
    return day.strftime("%d/%m/%Y")


def _weekday_name(iso_weekday: int, language: str) -> str:
    """A weekday name, from the central table (never declared twice)."""
    from src.core.i18n_dates import get_day_name

    return get_day_name(iso_weekday - 1, language)


def _month_name(month: int, language: str) -> str:
    """A month name, from the central table."""
    from src.core.i18n_dates import get_month_name

    return get_month_name(month, language)


def _calendar_clause(spec: RecurrenceSpec, language: str) -> str:
    """Which days the recurrence serves, worded.

    Args:
        spec: The recurrence.
        language: The reader's language.

    Returns:
        The clause, without the time part.
    """
    repeated = spec.interval > 1
    if spec.freq == "once":
        return get_recurrence_part("once", language).format(date=_format_date(spec.anchor_date))
    if spec.freq == "daily":
        key = "daily_n" if repeated else "daily"
        return get_recurrence_part(key, language).format(n=spec.interval)
    if spec.freq == "weekly":
        days = _join([_weekday_name(day, language) for day in sorted(spec.byweekday)], language)
        key = "weekly_n" if repeated else "weekly"
        return get_recurrence_part(key, language).format(n=spec.interval, days=days)
    if spec.freq == "monthly":
        return _monthly_clause(spec, language, repeated=repeated)
    month = _month_name(spec.bymonth[0], language)
    key = "yearly_n" if repeated else "yearly"
    return get_recurrence_part(key, language).format(
        n=spec.interval, day=spec.bymonthday[0], month=month
    )


def _monthly_clause(spec: RecurrenceSpec, language: str, *, repeated: bool) -> str:
    """The monthly clause: a day of month, the last day, or an nth weekday.

    Args:
        spec: The recurrence (``freq == "monthly"``).
        language: The reader's language.
        repeated: Whether the interval exceeds one.

    Returns:
        The clause.
    """
    if spec.nth_weekday is not None:
        nth, weekday = spec.nth_weekday
        nth_word = get_recurrence_part("nth_last" if nth == -1 else f"nth_{nth}", language)
        key = "monthly_nth_n" if repeated else "monthly_nth"
        return get_recurrence_part(key, language).format(
            n=spec.interval, nth=nth_word, weekday=_weekday_name(weekday, language)
        )
    if spec.bymonthday == (-1,):
        key = "monthly_last_n" if repeated else "monthly_last"
        return get_recurrence_part(key, language).format(n=spec.interval)
    days = _join([str(day) for day in sorted(spec.bymonthday)], language)
    key = "monthly_day_n" if repeated else "monthly_day"
    return get_recurrence_part(key, language).format(n=spec.interval, day=days)


def _time_clause(spec: RecurrenceSpec, language: str) -> str:
    """The moments of a served day, worded.

    Args:
        spec: The recurrence.
        language: The reader's language.

    Returns:
        The clause.
    """
    if spec.times.mode == "every":
        step = spec.times.step_minutes
        start = spec.times.start
        end = spec.times.end
        assert step is not None and start is not None and end is not None
        if step % 60 == 0:
            worded_step = get_recurrence_part("step_hours", language).format(n=step // 60)
        else:
            worded_step = get_recurrence_part("step_minutes", language).format(n=step)
        return get_recurrence_part("every_step", language).format(
            step=worded_step, **{"from": _clock(start), "to": _clock(end)}
        )
    moments = _join([_clock(m) for m in spec.times.materialise()], language)
    return get_recurrence_part("at_times", language).format(times=moments)


def _end_clause(spec: RecurrenceSpec, language: str) -> str:
    """When the series stops, worded; empty when it never does.

    Args:
        spec: The recurrence.
        language: The reader's language.

    Returns:
        The clause, or an empty string.
    """
    if spec.end.kind == "on_date" and spec.end.on_date is not None:
        return get_recurrence_part("end_on_date", language).format(
            date=_format_date(spec.end.on_date)
        )
    if spec.end.kind == "after_count" and spec.end.after_count is not None:
        return get_recurrence_part("end_after_count", language).format(n=spec.end.after_count)
    return ""


def describe(spec: RecurrenceSpec, language: str) -> str:
    """The recurrence as one sentence, in the reader's language.

    Args:
        spec: The recurrence.
        language: Any raw locale — normalized downstream.

    Returns:
        A sentence such as "Toutes les 2 semaines, le mardi, à 09:00".
    """
    calendar = _calendar_clause(spec, language)
    times = _time_clause(spec, language)
    ending = _end_clause(spec, language)
    join = get_recurrence_part("clause_join", language)
    tight = get_recurrence_part("clause_join_tight", language)

    # "Every day at 08:00" is ONE phrase; everything else is a sequence of
    # clauses and takes the separator. The test is the TIME clause, not the
    # calendar one: measured 2026-09-06, keying it on the calendar produced
    # "Tous les jours toutes les 2 h" with no comma. Both separators are
    # localized — Chinese joins with a full-width comma and no space.
    one_phrase = spec.freq == "daily" and spec.interval == 1 and spec.times.mode == "at"
    sentence = f"{calendar}{tight if one_phrase else join}{times}" if times else calendar
    if ending:
        sentence = f"{sentence}{join}{ending}"
    return sentence
```

Now write `apps/api/src/core/recurrence/__init__.py` **whole** — replacing the
stub from Task 1. Import order is `display`, `engine`, `spec` (alphabetical, as
Ruff's isort rule requires) and `__all__` is sorted with the dunder-free names
after the capitalised ones, which is the ordering Ruff accepts. Verified
2026-09-06: this exact file passes Black, Ruff (E,W,F,I,B,C4,UP) and MyPy under
the project's own configuration.

```python
"""Generic recurrence: a stored specification, and the instants it fires at.

The single import surface for every consumer. Nothing in this package imports
``src.domains`` — the caps a consumer enforces are injected
(:class:`RecurrenceLimits`), so one engine serves a routine capped at 12 runs a
day and a reminder capped at 48.
"""

from src.core.recurrence.display import describe
from src.core.recurrence.engine import (
    next_occurrence,
    occurrences,
    series,
    slots_between,
)
from src.core.recurrence.spec import (
    MAX_DAY_IN_MONTH,
    DailyTimes,
    RecurrenceError,
    RecurrenceFreq,
    RecurrenceLimits,
    RecurrenceSpec,
    SeriesEnd,
    TimeOfDay,
)

__all__ = [
    "MAX_DAY_IN_MONTH",
    "DailyTimes",
    "RecurrenceError",
    "RecurrenceFreq",
    "RecurrenceLimits",
    "RecurrenceSpec",
    "SeriesEnd",
    "TimeOfDay",
    "describe",
    "next_occurrence",
    "occurrences",
    "series",
    "slots_between",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/ -v
```

Expected: PASS, including `test_the_package_exists` from Task 3, now that
`display.py` exists.

The French wording assertions are exact strings. If one differs by a comma,
fix the **table or the joiner**, never the assertion — the assertion is the
contract the settings form and the HITL draft will render.

- [ ] **Step 5: Register the module with the central parity guard**

`tests/unit/core/test_i18n_parity.py` scans an **explicit list**, not the
filesystem: a new `i18n_*` module is invisible to it until it is declared.
Verified 2026-09-06 — `_I18N_MODULES` holds six names and would silently ignore
a seventh.

In `apps/api/tests/unit/core/test_i18n_parity.py`, add `"i18n_recurrence",` to
the `_I18N_MODULES` tuple, keeping the existing order and adding it last:

```python
_I18N_MODULES: tuple[str, ...] = (
    "i18n_hitl",
    "i18n_drafts",
    "i18n_api_messages",
    "i18n_v3",
    "i18n_dates",
    "i18n_patterns",
    "i18n_recurrence",
)
```

- [ ] **Step 6: Run the gate**

```bash
cd apps/api && .venv/Scripts/black --check src/core tests/unit/core \
  && .venv/Scripts/ruff check src/core tests/unit/core \
  && .venv/Scripts/mypy src/core/recurrence src/core/i18n_recurrence.py \
  && .venv/Scripts/pytest tests/unit/core/test_i18n_parity.py tests/unit/core/recurrence -v
```

Expected: clean, and the parity guard now covering the new module. If it
reports a missing key in one language, add the key to that language's table —
never remove it from the others.

---

### Task 5: Non-regression against the current engine

**Files:**
- Test: `apps/api/tests/unit/core/recurrence/test_legacy_equivalence.py`

**Interfaces:**
- Consumes: `occurrences` (Task 2), and the current
  `src.domains.scheduled_actions.schedule_helpers` (read-only — the test is
  the one place allowed to import a domain, because it compares against it).
- Produces: nothing (a guard).

**What it pins:** a legacy schedule (`days_of_week` + hour + minute) maps to
`{freq: weekly, interval: 1, byweekday, times: [{h, m}]}`. Measured
2026-09-06: 381/384 identical on next-occurrence lists, 76 492/76 518 identical
on weekly grids, and **every** difference is the current engine skipping a day
it should serve. No difference is a loss by the new engine — that is the
assertion.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/core/recurrence/test_legacy_equivalence.py`:

```python
"""The migration is an equivalence — proven, not asserted.

A legacy schedule becomes a weekly recurrence with one moment a day. If the new
engine moved a single instant, every past run row would stop matching its slot
and the ADR-265 weekly grid would go white.

The differences that remain are allowed in ONE direction only: the current
engine skipping a day the new one serves (measured: 142 runs a year across 73
zones, `Europe/Paris` included). A difference the other way is a regression and
fails this test.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay, occurrences
from src.domains.scheduled_actions.schedule_helpers import compute_next_triggers_utc

ZONES = [
    "Europe/Paris",
    "Europe/London",
    "America/New_York",
    "America/Santiago",
    "Asia/Tokyo",
    "Australia/Sydney",
    "Pacific/Auckland",
    "Asia/Kolkata",
]
DAY_SETS = [(1, 2, 3, 4, 5), (1, 2, 3, 4, 5, 6, 7), (6, 7), (3,)]
HOURS = [0, 8, 14, 23]
REFERENCES = [
    datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
    datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
    datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
]


def migrate(days: tuple[int, ...], hour: int, minute: int, anchor: date) -> RecurrenceSpec:
    """The migration, as the Alembic script will perform it."""
    return RecurrenceSpec(
        freq="weekly",
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=hour, minute=minute),)),
        anchor_date=anchor,
        interval=1,
        byweekday=tuple(sorted(days)),
    )


@pytest.mark.parametrize("zone", ZONES)
def test_the_new_engine_never_loses_an_occurrence(zone: str) -> None:
    losses: list[str] = []
    for days in DAY_SETS:
        for hour in HOURS:
            for reference in REFERENCES:
                legacy = compute_next_triggers_utc(
                    list(days), hour, 30, zone, count=12, after=reference
                )
                spec = migrate(days, hour, 30, reference.astimezone(ZoneInfo(zone)).date())
                fresh = occurrences(spec, zone, after=reference, count=12)
                # The lists have the same length, so a day the legacy engine
                # skips shifts one extra day in at the end. Compare only up to
                # the earlier of the two horizons.
                horizon = min(legacy[-1], fresh[-1])
                only_legacy = {i for i in legacy if i <= horizon} - set(fresh)
                if only_legacy:
                    stamps = sorted(
                        i.astimezone(ZoneInfo(zone)).isoformat() for i in only_legacy
                    )
                    losses.append(f"{zone} days={days} h={hour} ref={reference.date()}: {stamps}")
    assert losses == [], (
        "the new engine must never drop an occurrence the current one serves: "
        f"{losses}"
    )


def test_the_known_defect_is_the_only_difference_on_paris() -> None:
    """Europe/Paris, 00:30: the current engine loses 30/03 (measured)."""
    zone = "Europe/Paris"
    reference = datetime(2026, 3, 20, 12, 0, tzinfo=UTC)
    legacy = compute_next_triggers_utc(
        [1, 2, 3, 4, 5, 6, 7], 0, 30, zone, count=12, after=reference
    )
    spec = migrate((1, 2, 3, 4, 5, 6, 7), 0, 30, reference.astimezone(ZoneInfo(zone)).date())
    fresh = occurrences(spec, zone, after=reference, count=12)
    only_fresh = sorted(
        i.astimezone(ZoneInfo(zone)).strftime("%d/%m %H:%M") for i in set(fresh) - set(legacy)
    )
    assert only_fresh == ["30/03 00:30"]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/test_legacy_equivalence.py -v
```

Expected: FAIL only if the engine is wrong. If both tests pass immediately,
that is the intended result — this task's deliverable is the **guard**, and the
measurement it encodes was taken before the plan was written. Confirm by
temporarily changing `_instant` to use `fold=1` and checking the guard turns
red; then revert.

- [ ] **Step 3: No implementation**

Nothing to write: the engine already satisfies it. If a test fails, the defect
is in Task 2's engine, not in this test — the numbers come from a measurement
recorded in the design document.

- [ ] **Step 4: Run the full suite**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/ -v
```

Expected: PASS, every file.

- [ ] **Step 5: Run the gate**

```bash
cd apps/api && .venv/Scripts/black --check src/core tests/unit/core/recurrence \
  && .venv/Scripts/ruff check src/core tests/unit/core/recurrence \
  && .venv/Scripts/mypy src/core/recurrence
cd ../.. && task test:markers
```

Expected: clean, and `test:markers` green — a test that runs in zero CI jobs is
a test that silently leaves CI (ADR-155).

---

### Task 6: Default caps, and the lot's exit gate

**Files:**
- Modify: `apps/api/src/core/constants.py`
- Test: `apps/api/tests/unit/core/recurrence/test_spec.py` (extend)

**Interfaces:**
- Consumes: `RecurrenceLimits` (Task 1).
- Produces:
  - `RECURRENCE_ROUTINE_LIMITS: RecurrenceLimits` — the routine consumer's caps
  - `RECURRENCE_REMINDER_LIMITS: RecurrenceLimits` — the reminder consumer's caps

These live in `constants.py` because they are defaults a consumer picks up, not
values the component owns. Lot 4 makes them settings-overridable; a test must
then read them from `settings`, never hard-code the number.

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/unit/core/recurrence/test_spec.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/test_spec.py -k limit -v
```

Expected: FAIL — `ImportError: cannot import name 'RECURRENCE_ROUTINE_LIMITS'`.

- [ ] **Step 3: Write the implementation**

In `apps/api/src/core/constants.py`, next to the existing
`SCHEDULED_ACTIONS_*` block (around line 687), add:

```python
# =============================================================================
# Recurrence caps, per consumer (generic recurrence component)
# =============================================================================
# The component itself owns no ceiling: a cap travels with the caller, which is
# what lets one engine serve a routine that runs an agent pipeline and a
# reminder that sends a notification. Lot 4 makes these settings-overridable;
# a test must then read them from `settings`, never hard-code the number.

#: A routine runs the full agent pipeline on every occurrence: 12 a day is
#: already 12 LLM runs, and the form states the cost before saving.
RECURRENCE_ROUTINE_MAX_TIMES_PER_DAY = 12
RECURRENCE_ROUTINE_MIN_STEP_MINUTES = 15
RECURRENCE_ROUTINE_MAX_SERIES_COUNT = 500

#: A reminder sends a notification: the ceiling is about noise, not cost.
RECURRENCE_REMINDER_MAX_TIMES_PER_DAY = 48
RECURRENCE_REMINDER_MIN_STEP_MINUTES = 5
RECURRENCE_REMINDER_MAX_SERIES_COUNT = 1000
```

Then, at the end of `constants.py`, add the two assembled values (they are
placed at the end because they import from `core.recurrence`, and an import at
the top of a constants module would create a cycle):

```python
def _recurrence_limits() -> tuple[object, object]:
    """Assemble the two default limit sets.

    Imported lazily inside a function: ``core.recurrence`` imports nothing from
    here, but a module-level import would still make the two modules load in a
    fixed order for no benefit.

    Returns:
        The routine limits and the reminder limits.
    """
    from src.core.recurrence.spec import RecurrenceLimits

    return (
        RecurrenceLimits(
            max_times_per_day=RECURRENCE_ROUTINE_MAX_TIMES_PER_DAY,
            min_step_minutes=RECURRENCE_ROUTINE_MIN_STEP_MINUTES,
            max_series_count=RECURRENCE_ROUTINE_MAX_SERIES_COUNT,
        ),
        RecurrenceLimits(
            max_times_per_day=RECURRENCE_REMINDER_MAX_TIMES_PER_DAY,
            min_step_minutes=RECURRENCE_REMINDER_MIN_STEP_MINUTES,
            max_series_count=RECURRENCE_REMINDER_MAX_SERIES_COUNT,
        ),
    )


RECURRENCE_ROUTINE_LIMITS, RECURRENCE_REMINDER_LIMITS = _recurrence_limits()
```

If MyPy objects to the `tuple[object, object]` return annotation at the
assignment, type the helper precisely instead:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.recurrence.spec import RecurrenceLimits


def _recurrence_limits() -> tuple[RecurrenceLimits, RecurrenceLimits]:
    ...
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/ -v
```

Expected: PASS, every test of the lot.

- [ ] **Step 5: Run the lot's exit gate**

```bash
cd apps/api && .venv/Scripts/pytest tests/unit/core/recurrence/ -v
cd ../.. && task lint:backend && task test:backend:unit:fast && task test:markers
```

Expected: all green. Record the exact counts and report them. The lot is done
when:

1. `tests/unit/core/recurrence/` is fully green;
2. `task lint:backend` is clean (Black, Ruff, MyPy strict);
3. `test_no_domain_import.py` passes — the boundary holds;
4. `test_legacy_equivalence.py` passes — no occurrence is lost;
5. no file in `src/core/recurrence/` exceeds 600 logical SLOC;
6. **nothing outside `src/core/` was modified** — this lot changes no existing
   behaviour, which is why it can land on its own.

---

## Execution log — what the plan got wrong (2026-09-06)

The code below was written before it was ever run. Executing it found five
defects; all are fixed in the tree, and listed here so the plan matches the
code a reader will find.

| # | Defect | How it surfaced |
|---|---|---|
| 1 | **Task 2 said "do not edit `__init__.py` yet"** — but `test_engine.py` imports from the PACKAGE, not from `.engine`. The engine exports must be added in Task 2. | `ImportError: cannot import name 'next_occurrence'` |
| 2 | **`test_legacy_equivalence.py` was not Black-formatted**, while Task 5's gate promises a clean run. | `black --check` |
| 3 | **`series` measured CC 16**, over the shrink-only threshold of 15. Decomposed into `_walk_days` + `_fresh_instants` + `series` (CC 11) — never by raising the cap. | `test_cc_ratchet_guard.py`: 331 > 330 |
| 4 | **`_walk_days` returned `Any`** — `dateutil` is checked with `follow_imports = "skip"`. Made a generator so the type holds by construction, rather than asserting it with a cast. | `mypy: Returning Any from function declared to return "Iterator[datetime]"` |
| 5 | **The scan budget truncated in silence**: 3 999 of 5 000 requested occurrences, no signal. Rewritten to count CONSECUTIVE BARREN days and to log when it gives up. | Adversarial review, not a test |

Two findings from the adversarial review that needed no fix:

- **`Pacific/Apia` deleted 30 December 2011** to cross the date line. The
  de-duplication by instant absorbs it and the series stays strictly
  increasing — pinned by `test_a_civil_day_that_never_existed_is_absorbed`.
- **Mutation test**: flipping `fold=0` to `fold=1` turns two tests red,
  including the legacy-equivalence guard. The guards bite.

## Self-Review

**Spec coverage.** §3 (the model) → Task 1. §4.1-4.6, 4.9 → Tasks 1-2. §4.7
(re-arm) → **not in this lot**: it belongs to the executor, Lot 3, and is
recorded there. §4.8 → Task 1 (`_validate_reachable_dates`). §4.10 → Task 1
(`per_day` docstring) and rendered in Lot 5. §4.11 (`served_slot`) → Lot 3. §5
(genericity) → Tasks 1, 3, 6. §7.2 (composed sentence) → Task 4. §8
(non-regression) → Task 5. §9 tests 1-9 → Tasks 1, 2, 4, 5.

**Placeholder scan.** No "TBD", no "similar to Task N", no "add validation" —
every step carries the code it needs.

**Type consistency.** `RecurrenceSpec`, `DailyTimes`, `TimeOfDay`, `SeriesEnd`,
`RecurrenceLimits`, `RecurrenceError` are defined in Task 1 and used with those
exact names in Tasks 2, 4, 5, 6. `occurrences`, `next_occurrence`,
`slots_between`, `series` are defined in Task 2 and used in Tasks 5. `describe`
is defined in Task 4. `per_day()` and `validate_against()` are declared in
Task 1's Interfaces and used in Task 6.

**One deliberate gap.** Task 3 leaves a test red on purpose, and Task 4 Step 4
turns it green. That is a two-task cycle rather than a one-task cycle; it is
stated in both places so an executor reading Task 3 alone does not "fix" it by
deleting the assertion.
