# Generic Recurrence — Lot 2A: scheduled_actions on the engine (backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, **inline** (owner directive: no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scheduled_actions` stores a `RecurrenceSpec` and reads every instant
from `core/recurrence`. The cron engine and its three schedule columns are
gone; no routine loses an occurrence.

**Architecture:** One authority — a JSONB `recurrence` column, filled by an SQL
migration that is a strict equivalence, with `days_of_week`, `trigger_hour` and
`trigger_minute` DROPPED. `next_trigger_at` becomes nullable: NULL means
nothing follows. `schedule_helpers.py` keeps only what the DOMAIN does with
instants — the ISO week, the served slot, the re-arm — and delegates the
calculation.

**Tech Stack:** Python 3.14, SQLAlchemy 2 (asyncpg), Alembic, Pydantic v2,
pytest, MyPy strict.

**Spec:** `docs/superpowers/specs/2026-09-06-generic-recurrence-design.md`
(§4.7, §4.10, §4.11, §6, §8), and lot 1 (`core/recurrence`, already merged).

> **This lot leaves the FRONTEND broken on purpose.** It removes three fields
> the browser reads. Lot 2B restores it; the two are one change split for
> review, never a deployable state on their own.

## Global Constraints

- **Never `git commit` / `git push`** (owner rule). Every "Commit" step is **"Run the gate"**.
- **No subagents**: execute inline.
- MyPy strict; Google docstrings in **English**; `structlog` only.
- Timezone-aware UTC everywhere (AST guard `test_no_hardcoded_timezone_guard.py`).
- **JSONB is never mutated in place** — always a new dict (AST guard `test_jsonb_mutation_guard.py`).
- No empty `except: pass` (AST guard `test_no_empty_except_guard.py`).
- File-size ratchet: 600 logical SLOC. Complexity ratchet: no function at CC ≥ 15 (shrink-only; lot 1 had to decompose `series` for exactly this).
- The SQL `comment=` of a column mirrors its migration EXACTLY.
- Run from `apps/api` with `.venv/Scripts/python.exe -m pytest ... --no-cov` for targeted runs.

## Measured facts this plan rests on (2026-09-06)

| Fact | Measurement |
|---|---|
| The migration is expressible in pure SQL | `jsonb_build_object` over the 4 real dev rows |
| Its JSON round-trips through `RecurrenceSpec` | `model_validate` → `model_dump_json` → identical |
| No occurrence is lost on real rows | 4 routines × 3 references, 0 lost |
| `NULL <= now()` is **UNKNOWN** | the poll excludes finished series by construction |
| `ORDER BY ASC` puts NULLs **last** | made explicit rather than inherited |
| Re-arm from `max(due, now)` | **1** run after a 3-day outage, against 145 |
| `served_slot`'s new rule is retro-compatible | **0 divergence over 140 scenarios** with one slot a day |

## File Structure

| File | Change |
|---|---|
| `src/domains/scheduled_actions/schedule_helpers.py` | **Rewritten**: 14 functions → 5. Keeps `week_start`, `week_slots`, `day_slots`, `served_slot`, `rearm_after`. |
| `src/domains/scheduled_actions/models.py` | `recurrence` JSONB; `next_trigger_at` nullable; 3 columns dropped |
| `src/domains/scheduled_actions/schemas.py` | `recurrence` in/out; `times_of_day`, `runs_per_day`; the 3 fields gone |
| `src/domains/scheduled_actions/service.py` | Engine-driven create/update/toggle/recalculate |
| `src/domains/scheduled_actions/repository.py` | `NULLS LAST` explicit; index predicate narrowed |
| `src/domains/scheduled_actions/week.py` | One cell per INSTANT, carrying its local hour |
| `src/domains/scheduled_actions/runs.py` | `served_slot` on the spec |
| `src/infrastructure/scheduler/scheduled_action_executor.py` | 5 re-arm sites → `rearm_after` |
| `alembic/versions/2026_09_06_*_recurrence_spec.py` | The migration |
| `tests/unit/domains/scheduled_actions/*` | Rewritten against the spec |

---

### Task 1: `schedule_helpers` on the engine

**Files:**
- Modify: `apps/api/src/domains/scheduled_actions/schedule_helpers.py` (full rewrite)
- Test: `apps/api/tests/unit/domains/scheduled_actions/test_schedule_helpers.py` (full rewrite)

**Interfaces:**
- Consumes: `src.core.recurrence` — `RecurrenceSpec`, `occurrences`, `next_occurrence`, `slots_between`.
- Produces:
  - `week_start(tz: ZoneInfo, *, now: datetime | None = None) -> date` (unchanged)
  - `week_slots(spec: RecurrenceSpec, timezone: str, *, now: datetime | None = None) -> list[datetime]`
  - `day_slots(spec: RecurrenceSpec, timezone: str, *, day: date) -> list[datetime]`
  - `served_slot(spec: RecurrenceSpec, timezone: str, *, due_at: datetime, now: datetime) -> datetime | None`
  - `rearm_after(spec: RecurrenceSpec, timezone: str, *, due_at: datetime, now: datetime | None = None) -> datetime | None`

**What disappears, and why it is safe:** `compute_next_trigger_utc`,
`compute_next_triggers_utc`, `compute_next_trigger_after_execution`,
`compute_rearm_trigger`, `local_day_slot`, `validate_days_of_week`,
`format_schedule_display`, `_cron`, `_skipped_gap_run`, `_next_fire`. Every one
of them is a cron-shaped answer the engine now gives generically, and the two
DST repairs (`_skipped_gap_run`, the fall-back de-duplication) are unnecessary
because the engine enumerates days instead of asking a cron for them.

- [ ] **Step 1: Write the failing test**

Replace `apps/api/tests/unit/domains/scheduled_actions/test_schedule_helpers.py`
entirely:

```python
"""What the DOMAIN does with the instants the engine computes.

`core/recurrence` answers "when does this fire"; this module answers the
questions only a routine asks — which week, which slot a run served, and what
to arm next. The calculation is never re-implemented here.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.schedule_helpers import (
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/domains/scheduled_actions/test_schedule_helpers.py -q --no-cov
```

Expected: collection error — `cannot import name 'day_slots'`.

- [ ] **Step 3: Write the implementation**

Replace `apps/api/src/domains/scheduled_actions/schedule_helpers.py` entirely:

```python
"""What the routine domain does with the instants the engine computes.

`core/recurrence` answers "when does this fire". Three questions are left, and
they belong to this domain because only a routine asks them: which instants
fall in the CURRENT week, which slot a run SERVED, and what to arm NEXT.

The two daylight-saving repairs this module used to carry are gone with the
cron: the engine enumerates calendar days and localises them, so it never asks
a trigger which day comes next — the defect that dropped 142 runs a year across
73 zones, `Europe/Paris` included.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.core.recurrence import RecurrenceSpec, next_occurrence, slots_between
from src.core.time_utils import now_utc


def week_start(tz: ZoneInfo, *, now: datetime | None = None) -> date:
    """The local Monday of the ISO week containing ``now``.

    Args:
        tz: The routine's zone — the week is the ROUTINE's week, not the
            server's, which may still be on Sunday when Auckland is on Monday.
        now: Reference instant (UTC). Defaults to now.

    Returns:
        The Monday, as a local calendar date.
    """
    local_today = (now or now_utc()).astimezone(tz).date()
    return local_today - timedelta(days=local_today.isoweekday() - 1)


def _local_midnight(day: date, tz: ZoneInfo) -> datetime:
    """The instant local midnight of ``day`` happens at.

    A local day is not 24 hours: 29 March lasts 23 in Paris. Both bounds of a
    day window are therefore built from the CALENDAR, never by adding a day to
    an instant (measured: doing so counted 48 slots where 46 exist).

    Args:
        day: The local calendar day.
        tz: The zone.

    Returns:
        The UTC instant of that local midnight.
    """
    return datetime.combine(day, datetime.min.time(), tzinfo=tz).replace(fold=0).astimezone(UTC)


def week_slots(
    spec: RecurrenceSpec, timezone: str, *, now: datetime | None = None
) -> list[datetime]:
    """Every instant a routine fires at during the ISO week containing ``now``.

    Past days included: the weekly timeline colours every cell of the current
    week, and it colours them by EQUALITY with a run's ``slot_at`` — so these
    must be the very instants the executor armed, from the very same engine.

    Args:
        spec: The routine's recurrence.
        timezone: The routine's IANA zone.
        now: Reference instant (UTC). Defaults to now.

    Returns:
        The week's instants, ascending; empty when the routine fires no day of
        this week (a monthly routine outside its day, for instance).
    """
    tz = ZoneInfo(timezone)
    monday = week_start(tz, now=now)
    return slots_between(
        spec,
        timezone,
        start=_local_midnight(monday, tz),
        end=_local_midnight(monday + timedelta(days=7), tz),
    )


def day_slots(spec: RecurrenceSpec, timezone: str, *, day: date) -> list[datetime]:
    """Every instant a routine fires at on ONE local day.

    A LIST, not a single instant: a day may now hold several moments, and a
    caller that took the first would silently ignore the rest.

    Args:
        spec: The routine's recurrence.
        timezone: The routine's IANA zone.
        day: The local calendar day.

    Returns:
        The day's instants, ascending; empty when the routine skips that day.
    """
    tz = ZoneInfo(timezone)
    return slots_between(
        spec,
        timezone,
        start=_local_midnight(day, tz),
        end=_local_midnight(day + timedelta(days=1), tz),
    )


def served_slot(
    spec: RecurrenceSpec, timezone: str, *, due_at: datetime, now: datetime
) -> datetime | None:
    """Which slot a run starting now serves — the cell it will colour.

    A DUE run (``due_at <= now``) serves its due instant. A MANUAL one serves
    the LATEST slot of its local day that has already passed, and nothing at
    all when none has: a "test now" at 07:00 of an 08:00 routine is a
    rehearsal, not the day's execution.

    With a single slot a day the rule reduces EXACTLY to the previous
    behaviour — verified over 140 scenarios, zero divergence — so no past run
    row stops matching its cell.

    Args:
        spec: The routine's recurrence.
        timezone: The routine's IANA zone.
        due_at: The routine's pending due instant when the run started (UTC).
        now: When the run started (UTC).

    Returns:
        The served instant, or ``None`` for a rehearsal.
    """
    if due_at <= now:
        return due_at
    local_day = now.astimezone(ZoneInfo(timezone)).date()
    passed = [slot for slot in day_slots(spec, timezone, day=local_day) if slot <= now]
    return passed[-1] if passed else None


def rearm_after(
    spec: RecurrenceSpec, timezone: str, *, due_at: datetime, now: datetime | None = None
) -> datetime | None:
    """The instant to arm after a tick — scheduled or manual.

    **From ``max(due_at, now)``, never from ``due_at`` alone.** Measured
    2026-09-06 on a routine firing every 30 minutes: re-arming from the due
    instant fired 145 runs back-to-back when the server came back from a
    three-day outage; from ``max``, exactly one. A missed slot is missed — the
    system never replays three days of agent pipelines at restart.

    Taking the maximum also keeps a manual run ahead of schedule honest:
    testing an 08:00 routine at 07:00 leaves today's 08:00 armed, because
    ``due_at`` is still ahead of ``now``.

    Args:
        spec: The routine's recurrence.
        timezone: The routine's IANA zone.
        due_at: The routine's pending due instant when the tick started (UTC).
        now: Current instant (UTC). Defaults to now.

    Returns:
        The next instant, or ``None`` when the series is over — which the
        caller stores as a null trigger.
    """
    reference = now or now_utc()
    if due_at > reference:
        # Nothing was consumed: the pending slot stands.
        return due_at
    return next_occurrence(spec, timezone, after=reference)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/domains/scheduled_actions/test_schedule_helpers.py -q --no-cov
```

Expected: PASS, 17 tests.

Note on `test_a_manual_run_ahead_of_schedule_keeps_the_upcoming_slot`: the
implementation returns `due_at` unchanged when it is still ahead. That is the
same decision `compute_rearm_trigger` made, for the same reason — a rehearsal
must not consume the day.

- [ ] **Step 5: Run the gate**

```bash
cd apps/api && .venv/Scripts/python.exe -m black --check src/domains/scheduled_actions tests/unit/domains/scheduled_actions \
  && .venv/Scripts/python.exe -m ruff check src/domains/scheduled_actions \
  && .venv/Scripts/python.exe -m mypy src/domains/scheduled_actions/schedule_helpers.py
cd ../.. && apps/api/.venv/Scripts/python.exe scripts/audit/measure_cc.py apps/api/src/domains/scheduled_actions | head -6
```

Expected: clean, and no function at CC ≥ 15.

---

### Task 2: The model and its migration

**Files:**
- Modify: `apps/api/src/domains/scheduled_actions/models.py:112-141`
- Create: `apps/api/alembic/versions/2026_09_06_0000-e9f0a1b2c3d4_recurrence_spec.py`
- Test: `apps/api/tests/unit/domains/scheduled_actions/test_recurrence_column.py`

**Interfaces:**
- Consumes: `RecurrenceSpec` (lot 1).
- Produces: `ScheduledAction.recurrence: Mapped[dict]`, `ScheduledAction.next_trigger_at: Mapped[datetime | None]`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/unit/domains/scheduled_actions/test_recurrence_column.py`:

```python
"""The stored shape of a routine's schedule.

One authority: a JSONB column holding a `RecurrenceSpec`. The three cron
columns are gone — a routine that fires twice a day cannot be described by one
hour and one minute, and keeping them would make the row disagree with itself.
"""

from datetime import date

from sqlalchemy import inspect

from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.models import ScheduledAction


def test_the_cron_columns_are_gone() -> None:
    columns = {c.key for c in inspect(ScheduledAction).columns}
    assert "days_of_week" not in columns
    assert "trigger_hour" not in columns
    assert "trigger_minute" not in columns


def test_the_recurrence_column_exists_and_is_not_nullable() -> None:
    column = inspect(ScheduledAction).columns["recurrence"]
    assert column.nullable is False


def test_next_trigger_at_is_nullable() -> None:
    """NULL means nothing follows: an exhausted series, or a consumed single
    occurrence. `NULL <= now()` is UNKNOWN, so the poll excludes such a row by
    construction (verified on PostgreSQL 2026-09-06)."""
    assert inspect(ScheduledAction).columns["next_trigger_at"].nullable is True


def test_a_spec_round_trips_through_the_column_shape() -> None:
    """The serialisation pair must survive a round trip over EVERY field — the
    repo's standing rule for `to_serializable_dict` / `reconstruct_*` pairs."""
    spec = RecurrenceSpec(
        freq="monthly",
        times=DailyTimes(
            mode="every",
            step_minutes=30,
            start=TimeOfDay(hour=8, minute=0),
            end=TimeOfDay(hour=9, minute=30),
        ),
        anchor_date=date(2026, 9, 1),
        interval=3,
        bymonthday=(15,),
    )
    stored = spec.model_dump(mode="json")
    assert RecurrenceSpec.model_validate(stored) == spec
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/domains/scheduled_actions/test_recurrence_column.py -q --no-cov
```

Expected: 3 failures (`days_of_week` still present, no `recurrence` column,
`next_trigger_at` not nullable); the round-trip already passes.

- [ ] **Step 3: Change the model**

In `apps/api/src/domains/scheduled_actions/models.py`, replace the schedule
block (the four columns `days_of_week`, `trigger_hour`, `trigger_minute` and
the `next_trigger_at` declaration) with:

```python
    # Schedule — ONE authority (generic recurrence, lot 1).
    # The three cron columns this replaces could not describe a routine that
    # fires twice a day, and keeping them beside the spec would let the row
    # disagree with itself. SQL `comment=` mirrors the migration EXACTLY.
    recurrence: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="RecurrenceSpec: which calendar days, and which moments in them.",
    )
    user_timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DEFAULT_USER_DISPLAY_TIMEZONE,
        doc="IANA timezone for schedule evaluation",
    )

    # Computed trigger time (UTC) — recalculated after each execution.
    # NULLABLE since the recurrence rework: NULL means nothing follows (an
    # exhausted series, a consumed single occurrence). `NULL <= now()` is
    # UNKNOWN in SQL, so the scheduler's poll excludes such a row by
    # construction rather than by a filter someone must remember to write.
    next_trigger_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Next execution (UTC); NULL = nothing follows.",
    )
```

Then remove the now-unused imports `ARRAY` and `SmallInteger` **only if no
other column in the file uses them** — `ScheduledActionRun` uses
`SmallInteger`, so keep that one and drop `ARRAY` alone.

Narrow the partial index in `__table_args__` so it stops holding rows the poll
can never match:

```python
    __table_args__ = (
        Index(
            "ix_scheduled_actions_due",
            "next_trigger_at",
            postgresql_where=(
                "is_enabled = true AND status = 'active' AND next_trigger_at IS NOT NULL"
            ),
        ),
    )
```

- [ ] **Step 4: Write the migration**

Create `apps/api/alembic/versions/2026_09_06_0000-e9f0a1b2c3d4_recurrence_spec.py`.
Set `down_revision` to the current head — read it first:

```bash
cd apps/api && .venv/Scripts/python.exe -m alembic heads
```

```python
"""A routine stores a RecurrenceSpec, not three cron columns.

`days_of_week` + `trigger_hour` + `trigger_minute` could express one time a
day on a set of weekdays and nothing else. The replacement is a JSONB
`RecurrenceSpec` (`src/core/recurrence`), and the conversion is a strict
equivalence: a weekly rule, interval 1, on the same days, at the one time.

Verified on the real dev rows 2026-09-06: the produced JSON round-trips through
`RecurrenceSpec`, and the instants it yields lose nothing against the cron
engine over three reference dates.

`next_trigger_at` becomes nullable — NULL means nothing follows — and the
partial index that serves the poll gains `next_trigger_at IS NOT NULL`, since
`NULL <= now()` is UNKNOWN and such a row can never match.

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-09-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The conversion, as one SQL expression. Pure SQL rather than a Python loop:
#: it runs in one statement whatever the row count, and it cannot half-apply.
_TO_RECURRENCE = """
    UPDATE scheduled_actions SET recurrence = jsonb_build_object(
        'freq', 'weekly',
        'interval', 1,
        'anchor_date', to_char((created_at AT TIME ZONE user_timezone)::date, 'YYYY-MM-DD'),
        'byweekday', to_jsonb(days_of_week),
        'bymonthday', '[]'::jsonb,
        'bymonth', '[]'::jsonb,
        'nth_weekday', 'null'::jsonb,
        'times', jsonb_build_object(
            'mode', 'at',
            'at', jsonb_build_array(
                jsonb_build_object('hour', trigger_hour, 'minute', trigger_minute)
            )
        ),
        'end', jsonb_build_object('kind', 'never', 'on_date', null, 'after_count', null)
    )
"""

#: The reverse, for a routine the new model can still express in the old one.
#: A recurrence the cron columns cannot hold (monthly, several times a day)
#: has no faithful answer, so the downgrade REFUSES rather than inventing one.
_FROM_RECURRENCE = """
    UPDATE scheduled_actions SET
        days_of_week = ARRAY(
            SELECT jsonb_array_elements_text(recurrence->'byweekday')::smallint
        ),
        trigger_hour = (recurrence->'times'->'at'->0->>'hour')::smallint,
        trigger_minute = (recurrence->'times'->'at'->0->>'minute')::smallint
"""

_DOWNGRADABLE = """
    SELECT count(*) FROM scheduled_actions
     WHERE recurrence->>'freq' <> 'weekly'
        OR (recurrence->>'interval')::int <> 1
        OR recurrence->'times'->>'mode' <> 'at'
        OR jsonb_array_length(recurrence->'times'->'at') <> 1
        OR recurrence->'end'->>'kind' <> 'never'
"""


def upgrade() -> None:
    """Add the spec, fill it from the cron columns, drop them."""
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "recurrence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,  # filled below, then made NOT NULL
            comment="RecurrenceSpec: which calendar days, and which moments in them.",
        ),
    )
    op.execute(_TO_RECURRENCE)
    op.alter_column("scheduled_actions", "recurrence", nullable=False)

    op.drop_column("scheduled_actions", "days_of_week")
    op.drop_column("scheduled_actions", "trigger_hour")
    op.drop_column("scheduled_actions", "trigger_minute")

    op.alter_column(
        "scheduled_actions",
        "next_trigger_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        comment="Next execution (UTC); NULL = nothing follows.",
    )

    # The poll reads `next_trigger_at <= now()`, which is UNKNOWN for a NULL:
    # such a row can never match, so it has no business in the index.
    op.drop_index("ix_scheduled_actions_due", table_name="scheduled_actions")
    op.create_index(
        "ix_scheduled_actions_due",
        "scheduled_actions",
        ["next_trigger_at"],
        postgresql_where=sa.text(
            "is_enabled = true AND status = 'active' AND next_trigger_at IS NOT NULL"
        ),
    )


def downgrade() -> None:
    """Restore the cron columns, refusing what they cannot express."""
    connection = op.get_bind()
    blocking = connection.execute(sa.text(_DOWNGRADABLE)).scalar_one()
    if blocking:
        raise RuntimeError(
            f"{blocking} routine(s) use a recurrence the cron columns cannot "
            "express (monthly, an interval, several times a day, or an end "
            "date). Downgrading would silently rewrite their schedule; delete "
            "or simplify them first."
        )

    op.add_column(
        "scheduled_actions",
        sa.Column("days_of_week", postgresql.ARRAY(sa.SmallInteger()), nullable=True),
    )
    op.add_column("scheduled_actions", sa.Column("trigger_hour", sa.SmallInteger(), nullable=True))
    op.add_column(
        "scheduled_actions", sa.Column("trigger_minute", sa.SmallInteger(), nullable=True)
    )
    op.execute(_FROM_RECURRENCE)
    for column in ("days_of_week", "trigger_hour", "trigger_minute"):
        op.alter_column("scheduled_actions", column, nullable=False)

    op.execute("UPDATE scheduled_actions SET next_trigger_at = now() WHERE next_trigger_at IS NULL")
    op.alter_column(
        "scheduled_actions",
        "next_trigger_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_column("scheduled_actions", "recurrence")

    op.drop_index("ix_scheduled_actions_due", table_name="scheduled_actions")
    op.create_index(
        "ix_scheduled_actions_due",
        "scheduled_actions",
        ["next_trigger_at"],
        postgresql_where=sa.text("is_enabled = true AND status = 'active'"),
    )
```

- [ ] **Step 5: Run the test and the replay check**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/domains/scheduled_actions/test_recurrence_column.py -q --no-cov
cd ../.. && task db:migrate:replay-check
```

Expected: the unit test passes; the replay check runs every migration from an
empty database and ends on a single head.

- [ ] **Step 6: Apply to the dev database and verify the real rows**

```bash
cd apps/api && .venv/Scripts/python.exe -m alembic upgrade head
```

Then read the converted rows back and confirm each one parses:

```bash
cd apps/api && DATABASE_URL="postgresql+psycopg://u:p@localhost/db" \
  REDIS_URL="redis://localhost:6379/0" SECRET_KEY="$(python -c 'print("x"*48)')" \
  FERNET_KEY="GHy1cW7bkc7VQFYQeCBcMGmZMOR1sRTaQ4S39aMbF4A=" \
  .venv/Scripts/python.exe -c "
import json, subprocess
from src.core.recurrence import RecurrenceSpec
rows = subprocess.run(['docker','exec','lia-postgres-dev','psql','-U','<USER>','-d','<DB>','-tAc',
                       'SELECT recurrence FROM scheduled_actions'],
                      capture_output=True, text=True).stdout.strip().splitlines()
for raw in rows:
    spec = RecurrenceSpec.model_validate(json.loads(raw))
    print('OK', spec.freq, spec.byweekday, [(t.hour, t.minute) for t in spec.times.materialise()])
print(f'{len(rows)} row(s) parsed')
"
```

Expected: every row parses. Read `<USER>`/`<DB>` from `.env`
(`POSTGRES_USER` / `POSTGRES_DB`), stripping the trailing comment.

- [ ] **Step 7: Run the gate**

```bash
cd apps/api && .venv/Scripts/python.exe -m black --check src/domains/scheduled_actions alembic/versions \
  && .venv/Scripts/python.exe -m ruff check src/domains/scheduled_actions alembic/versions \
  && .venv/Scripts/python.exe -m mypy src/domains/scheduled_actions/models.py
```

---

### Task 3: The API contract

**Files:**
- Modify: `apps/api/src/domains/scheduled_actions/schemas.py`
- Test: `apps/api/tests/unit/domains/scheduled_actions/test_schemas.py` (rewrite)

**Interfaces:**
- Produces:
  - `ScheduledActionCreate(title, action_prompt, recurrence, trigger_kind, condition_config, requires_approval)`
  - `ScheduledActionUpdate(... recurrence: RecurrenceSpec | None ...)`
  - `ScheduledActionResponse(..., recurrence, schedule_display, times_of_day, runs_per_day, next_occurrences, next_trigger_at: datetime | None)`
  - `ScheduledActionWeekCell(day, date, slot_at, hour, minute, outcome, run_at, error, manual)`

**Why `times_of_day` exists:** the browser must never materialise a `mode:
"every"` step — that would be a second reading of the schedule, the very thing
ADR-265 forbids. The server publishes the moments it computed; the client
sorts and labels from them.

- [ ] **Step 1: Write the failing test**

Replace `apps/api/tests/unit/domains/scheduled_actions/test_schemas.py`. Keep
the existing `ConditionConfig` tests verbatim (they are unaffected) and replace
every test that mentions `days_of_week`, `trigger_hour` or `trigger_minute`
with:

```python
"""The scheduled-action contract, on the recurrence spec."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.schemas import (
    ScheduledActionCreate,
    ScheduledActionResponse,
    ScheduledActionUpdate,
)


def at(*pairs: tuple[int, int]) -> DailyTimes:
    return DailyTimes(mode="at", at=tuple(TimeOfDay(hour=h, minute=m) for h, m in pairs))


def weekly(*pairs: tuple[int, int]) -> RecurrenceSpec:
    return RecurrenceSpec(
        freq="weekly",
        times=at(*pairs),
        anchor_date=date(2026, 9, 7),
        byweekday=(1, 2, 3, 4, 5),
    )


def test_create_carries_a_recurrence() -> None:
    data = ScheduledActionCreate(
        title="Revue de presse", action_prompt="fais-moi une revue", recurrence=weekly((8, 0))
    )
    assert data.recurrence.freq == "weekly"


def test_create_refuses_a_recurrence_beyond_the_routine_cap() -> None:
    """A routine runs an agent pipeline: its ceiling is lower than a
    reminder's, and it is INJECTED, never owned by the model."""
    dense = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=30,
            start=TimeOfDay(hour=0, minute=0),
            end=TimeOfDay(hour=23, minute=30),
        ),
        anchor_date=date(2026, 9, 7),
    )
    with pytest.raises(ValidationError):
        ScheduledActionCreate(title="t", action_prompt="p", recurrence=dense)


def test_update_leaves_the_recurrence_alone_when_absent() -> None:
    update = ScheduledActionUpdate(title="new title")
    assert "recurrence" not in update.model_dump(exclude_unset=True)


def test_response_publishes_the_materialised_moments() -> None:
    """The browser never expands a step itself: it would be a second reading
    of the schedule, and the two would disagree at the DST edges."""
    response = ScheduledActionResponse(
        id=uuid4(),
        user_id=uuid4(),
        title="t",
        action_prompt="p",
        recurrence=RecurrenceSpec(
            freq="daily",
            times=DailyTimes(
                mode="every",
                step_minutes=120,
                start=TimeOfDay(hour=8, minute=0),
                end=TimeOfDay(hour=14, minute=0),
            ),
            anchor_date=date(2026, 9, 7),
        ),
        user_timezone="Europe/Paris",
        trigger_kind="time",
        condition_config=None,
        requires_approval=False,
        next_trigger_at=datetime(2026, 9, 8, 6, 0, tzinfo=UTC),
        is_enabled=True,
        status="active",
        last_executed_at=None,
        execution_count=0,
        consecutive_failures=0,
        last_error=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert response.times_of_day == ["08:00", "10:00", "12:00", "14:00"]
    assert response.runs_per_day == 4
    assert response.schedule_display
    assert response.next_occurrences


def test_response_accepts_a_null_trigger_for_a_finished_series() -> None:
    response = ScheduledActionResponse(
        id=uuid4(),
        user_id=uuid4(),
        title="t",
        action_prompt="p",
        recurrence=RecurrenceSpec(
            freq="once", times=at((9, 0)), anchor_date=date(2026, 1, 1)
        ),
        user_timezone="Europe/Paris",
        trigger_kind="time",
        condition_config=None,
        requires_approval=False,
        next_trigger_at=None,
        is_enabled=True,
        status="active",
        last_executed_at=None,
        execution_count=1,
        consecutive_failures=0,
        last_error=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert response.next_trigger_at is None
    assert response.next_occurrences == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/domains/scheduled_actions/test_schemas.py -q --no-cov
```

- [ ] **Step 3: Rewrite the schema fields**

In `apps/api/src/domains/scheduled_actions/schemas.py`, replace the three
schedule fields of `ScheduledActionCreate` with:

```python
    recurrence: RecurrenceSpec = Field(
        ...,
        description="Which calendar days the routine serves, and the moments inside them.",
    )

    @model_validator(mode="after")
    def validate_against_routine_limits(self) -> ScheduledActionCreate:
        """Refuse a recurrence beyond what a ROUTINE may ask.

        The cap is injected rather than owned by the recurrence model: a
        routine runs an agent pipeline on every occurrence, a reminder sends a
        notification, and one engine serves both.

        Returns:
            The validated instance.

        Raises:
            ValidationError: Pydantic wraps the ``RecurrenceError`` raised when
                the recurrence exceeds `RECURRENCE_ROUTINE_LIMITS`.
        """
        self.recurrence.validate_against(RECURRENCE_ROUTINE_LIMITS)
        return self
```

The same field, optional, on `ScheduledActionUpdate`, with the validator
guarding only when it is set:

```python
    recurrence: RecurrenceSpec | None = Field(
        default=None, description="New recurrence; absent leaves the schedule alone."
    )

    @model_validator(mode="after")
    def validate_against_routine_limits(self) -> ScheduledActionUpdate:
        """Refuse a new recurrence beyond what a routine may ask.

        Returns:
            The validated instance.

        Raises:
            ValidationError: On a recurrence over the routine cap.
        """
        if self.recurrence is not None:
            self.recurrence.validate_against(RECURRENCE_ROUTINE_LIMITS)
        return self
```

And on `ScheduledActionResponse`, replace the three fields and the computed
block:

```python
    recurrence: RecurrenceSpec
    next_trigger_at: datetime | None
    ...
    #: The moments of a served day, `HH:MM`, MATERIALISED here. The browser
    #: never expands a `mode: "every"` step itself — that would be a second
    #: reading of the schedule, and the two would disagree at the DST edges.
    times_of_day: list[str] = Field(default_factory=list)
    #: How many times a served day fires, as an UPPER BOUND: a clock change
    #: makes the real count differ on one day a year (24 declared, 23 served).
    runs_per_day: int = 0

    @model_validator(mode="after")
    def compute_display_fields(self) -> ScheduledActionResponse:
        """Fill the sentence, the moments and the upcoming runs."""
        if not self.schedule_display:
            self.schedule_display = describe(self.recurrence, DEFAULT_LANGUAGE)
        if not self.times_of_day:
            self.times_of_day = [
                f"{moment.hour:02d}:{moment.minute:02d}"
                for moment in self.recurrence.times.materialise()
            ]
        if not self.runs_per_day:
            self.runs_per_day = self.recurrence.per_day()
        if not self.next_occurrences:
            self.next_occurrences = occurrences(
                self.recurrence,
                self.user_timezone,
                after=now_utc(),
                count=SCHEDULED_ACTION_OCCURRENCES_PREVIEW,
            )
        return self
```

Add `hour` and `minute` to `ScheduledActionWeekCell`:

```python
    hour: int = Field(..., ge=0, le=23, description="Local hour of the slot.")
    minute: int = Field(..., ge=0, le=59, description="Local minute of the slot.")
```

Imports to add at the top of the module:

```python
from src.core.constants import (
    RECURRENCE_ROUTINE_LIMITS,
    SCHEDULED_ACTION_OCCURRENCES_PREVIEW,
)
from src.core.i18n import DEFAULT_LANGUAGE
from src.core.recurrence import RecurrenceSpec, describe, occurrences
from src.core.time_utils import now_utc
```

and remove the imports of `compute_next_triggers_utc` and
`format_schedule_display`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/domains/scheduled_actions/test_schemas.py -q --no-cov
```

- [ ] **Step 5: Run the gate**

```bash
cd apps/api && .venv/Scripts/python.exe -m black --check src/domains/scheduled_actions \
  && .venv/Scripts/python.exe -m ruff check src/domains/scheduled_actions \
  && .venv/Scripts/python.exe -m mypy src/domains/scheduled_actions/schemas.py
```

---

### Task 4: Service, repository, week, runs and executor

**Files:**
- Modify: `src/domains/scheduled_actions/service.py` (4 call sites)
- Modify: `src/domains/scheduled_actions/repository.py` (ordering)
- Modify: `src/domains/scheduled_actions/week.py` (cells by instant)
- Modify: `src/domains/scheduled_actions/runs.py` (served slot)
- Modify: `src/infrastructure/scheduler/scheduled_action_executor.py` (5 re-arm sites)
- Test: the matching test files

**Interfaces:**
- Consumes: Task 1's helpers, Task 3's schemas.
- Produces: no new public name; every existing signature keeps its shape except
  that schedules travel as a `RecurrenceSpec` and `next_trigger_at` may be
  `None`.

- [ ] **Step 1: Write the failing tests**

Add to `apps/api/tests/unit/domains/scheduled_actions/test_week.py`:

```python
def test_a_day_with_two_moments_produces_two_cells() -> None:
    """A cell is keyed by INSTANT, not by day: a routine firing at 08:00 and
    18:00 draws two chips on Monday, and `cells.find(c => c.day === day)` would
    have kept only the first."""
    action = _action(
        recurrence=RecurrenceSpec(
            freq="weekly",
            times=DailyTimes(
                mode="at",
                at=(TimeOfDay(hour=8, minute=0), TimeOfDay(hour=18, minute=0)),
            ),
            anchor_date=date(2026, 9, 7),
            byweekday=(1,),
        )
    )
    week = build_week([action], [], now=datetime(2026, 9, 9, 12, 0, tzinfo=UTC))[0]
    monday = [cell for cell in week.cells if cell.day == 1]
    assert len(monday) == 2
    assert [(c.hour, c.minute) for c in monday] == [(8, 0), (18, 0)]


def test_each_cell_carries_its_local_hour_so_the_client_never_reads_a_schedule() -> None:
    action = _action(
        recurrence=RecurrenceSpec(
            freq="daily",
            times=DailyTimes(mode="at", at=(TimeOfDay(hour=6, minute=45),)),
            anchor_date=date(2026, 9, 1),
        )
    )
    week = build_week([action], [], now=datetime(2026, 9, 9, 12, 0, tzinfo=UTC))[0]
    assert {(c.hour, c.minute) for c in week.cells} == {(6, 45)}
```

Add to `apps/api/tests/unit/infrastructure/scheduler/test_scheduled_action_executor.py`:

```python
async def test_a_finished_series_arms_nothing_and_is_not_polled_again(...) -> None:
    """`rearm_after` returns None for an exhausted series; the row keeps a NULL
    trigger, which `NULL <= now()` excludes from the poll by construction."""
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/domains/scheduled_actions tests/unit/infrastructure/scheduler/test_scheduled_action_executor.py -q --no-cov
```

- [ ] **Step 3: Apply the five changes**

**`service.py`** — the four `compute_next_trigger_utc` call sites become
`next_occurrence(action.recurrence, timezone, after=now_utc())`, and `create`
stores `data.recurrence.model_dump(mode="json")` — a NEW dict, never a mutation
(JSONB rule). `update` recomputes when `recurrence` is in the payload, and
`recalculate_all_for_user` re-derives from the stored spec under the new zone.

**`repository.py`** — `get_all_for_user` orders
`ScheduledAction.next_trigger_at.asc().nullslast()`: PostgreSQL already puts
NULLs last for ASC, and saying it makes the contract independent of that
default.

**`week.py`** — `build_week` iterates `week_slots(action.recurrence,
action.user_timezone, now=reference)` and builds one `WeekCell` per instant,
adding `hour=local.hour, minute=local.minute` to the dataclass.

**`runs.py`** — `record_run` calls
`served_slot(action.recurrence, action.user_timezone, due_at=due_at, now=started_at)`.

**`scheduled_action_executor.py`** — the five `compute_rearm_trigger(...)`
blocks become:

```python
                next_trigger = rearm_after(
                    action.recurrence_spec,
                    action.user_timezone,
                    due_at=due_at,
                    now=started_at,
                )
```

where `recurrence_spec` is a small read-only property on the model that parses
the column once:

```python
    @property
    def recurrence_spec(self) -> RecurrenceSpec:
        """The stored schedule, parsed.

        A property rather than a column type: the row keeps plain JSONB, so a
        migration or an admin query never depends on the Python model.

        Returns:
            The recurrence this routine follows.
        """
        return RecurrenceSpec.model_validate(self.recurrence)
```

The repository's `mark_execution_success`, `mark_execution_failure` and
`reschedule` take `next_trigger_at: datetime | None`.

- [ ] **Step 4: Run the tests**

```bash
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/domains/scheduled_actions tests/unit/infrastructure/scheduler -q --no-cov
```

- [ ] **Step 5: Run the gate**

```bash
cd apps/api && .venv/Scripts/python.exe -m black --check src tests \
  && .venv/Scripts/python.exe -m ruff check src tests \
  && .venv/Scripts/python.exe -m mypy src/domains/scheduled_actions src/infrastructure/scheduler/scheduled_action_executor.py
```

---

### Task 5: Every other consumer, and the full suite

**Files:**
- Modify: `src/domains/agents/tools/automation_tools.py` (draft input + listing)
- Modify: `src/domains/briefing/fetchers.py` (already guards `None`; confirm)
- Modify: `tests/unit/domains/agents/drafts/test_scheduled_action_draft.py`
- Modify: `tests/integration/domains/scheduled_actions/test_runs_pg.py`
- Verify: `tests/unit/domains/habits/*`, `tests/unit/domains/heartbeat/test_habit_context.py` — **must not change**: habits carry their OWN `days_of_week`, 0-indexed on Monday, in a JSONB payload. Two homonymous contracts with opposite conventions; only the routine one moves.

- [ ] **Step 1: Find every remaining reference**

```bash
cd d:/Developpement/LIA && grep -rn "days_of_week\|trigger_hour\|trigger_minute" --include=*.py apps/api/src | grep -v __pycache__
```

Expected after Task 4: only `domains/heartbeat/habit_context.py` and
`domains/agents/services/recurrence_ledger.py` — both the HABITS contract,
which this lot does not touch.

- [ ] **Step 2: Update the automation tool's draft**

`ScheduledActionDraftInput` carries `recurrence: dict` and keeps
`schedule_human`, now produced by `describe(spec, locale)`. The tool's
signature is lot 2B/3's concern (the chat vocabulary); here it only has to keep
compiling and to persist a valid spec.

- [ ] **Step 3: Run the whole backend suite**

```bash
cd d:/Developpement/LIA && task test:backend:unit:fast
```

Expected: green. Any failure naming `days_of_week` on a HABITS test is a
mistake in this lot, not a test to update.

- [ ] **Step 4: Run every gate, including the ratchets**

```bash
cd d:/Developpement/LIA && task lint:backend
cd apps/api && .venv/Scripts/python.exe -m pytest tests/unit/test_cc_ratchet_guard.py tests/unit/test_file_size_ratchet_guard.py tests/unit/test_jsonb_mutation_guard.py tests/unit/test_no_hardcoded_timezone_guard.py -q --no-cov
cd ../.. && task test:markers
```

- [ ] **Step 5: Update the ratchets that IMPROVED**

`schedule_helpers.py` loses nine functions, so its file-size and complexity
figures drop. Lock the gains in — the ratchets only ever move down:

```bash
cd d:/Developpement/LIA && task ratchet:update
apps/api/.venv/Scripts/python.exe scripts/audit/measure_cc.py apps/api/src --update-ratchet
```

Run the guard suite again afterwards and report the before/after numbers.

---

## Test plan additions for lot 2A

Beyond the design's list, this lot adds:

| # | What it pins | Where |
|---|---|---|
| 31 | The cron columns are gone from the model | `test_recurrence_column.py` |
| 32 | `next_trigger_at` is nullable and NULL is excluded from the poll | `test_recurrence_column.py`, repository test |
| 33 | The migration converts the real dev rows and they all parse | Task 2 Step 6 |
| 34 | The downgrade REFUSES a recurrence the cron columns cannot hold | migration test |
| 35 | A day with two moments draws two cells, each with its local hour | `test_week.py` |
| 36 | The routine cap is enforced at the contract boundary | `test_schemas.py` |
| 37 | `times_of_day` is materialised server-side | `test_schemas.py` |
| 38 | The habits contract is untouched | `grep` in Task 5 Step 1 |

## Self-Review

**Spec coverage.** §4.7 → Task 1 (`rearm_after`). §4.10 → Task 3
(`runs_per_day` as an upper bound). §4.11 → Task 1 (`served_slot`, `day_slots`).
§6 → Tasks 2-4. §7.1 R5 (`NULLS LAST`) → Task 4. §7.1 R6 (`local_day_slot`
returns a list) → Task 1. §8 → Task 2 Step 6 plus lot 1's standing guard.

**Placeholder scan.** One deliberate `d8e9f0a1b2c3` in the migration, with
the command to read it in the same step. `<USER>`/`<DB>` likewise, with the
file to read them from.

**Type consistency.** `week_slots`, `day_slots`, `served_slot`, `rearm_after`
are declared in Task 1's Interfaces and used with those exact signatures in
Tasks 4 and 5. `RecurrenceSpec` comes from lot 1. `recurrence_spec` is
introduced in Task 4 Step 3 and used only there.

**Known gap, stated rather than hidden.** This lot leaves the frontend broken:
it removes three fields the browser reads. Lot 2B is not optional.
