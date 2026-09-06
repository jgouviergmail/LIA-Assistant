"""What a SCHEDULED THING does with the instants the engine computes.

The engine answers "when does this fire". Three questions are left: which
instants fall in the CURRENT week, which slot a run SERVED, and what to arm
NEXT.

They lived in the routine domain, under the claim that "only a routine asks
them". The reminders lot refuted it: a reminder asks exactly the same three,
and reaching for them across domains would be the import this codebase forbids.
They are pure functions of a spec, a zone and an instant — they name no
routine, no reminder, and no table — so they belong beside the engine they
question.

The two daylight-saving repairs this module used to carry are gone with the
cron: the engine enumerates calendar days and localises them, so it never asks
a trigger which day comes next — the defect that dropped 142 runs a year across
73 zones, `Europe/Paris` included.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

# `datetime.now(UTC)` rather than `core.time_utils.now_utc`, which is that
# exact call plus an import of `core.config`. Measured 2026-09-06: adding it
# here is not merely impure, it is FATAL — `core.constants` reads
# `RecurrenceLimits` from this package, so the chain closes on a
# partially-initialised `core.config` and nothing boots. Pinned by
# `tests/unit/core/recurrence/test_no_domain_import.py`.
from src.core.recurrence.engine import next_occurrence, slots_between
from src.core.recurrence.spec import RecurrenceSpec


def week_start(tz: ZoneInfo, *, now: datetime | None = None) -> date:
    """The local Monday of the ISO week containing ``now``.

    Args:
        tz: The subject's zone — the week is the SUBJECT's week, not the
            server's, which may still be on Sunday when Auckland is on Monday.
        now: Reference instant (UTC). Defaults to now.

    Returns:
        The Monday, as a local calendar date.
    """
    local_today = (now or datetime.now(UTC)).astimezone(tz).date()
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
    """Every instant a schedule fires at during the ISO week containing ``now``.

    Past days included: the weekly timeline colours every cell of the current
    week, and it colours them by EQUALITY with a run's ``slot_at`` — so these
    must be the very instants the executor armed, from the very same engine.

    Args:
        spec: The recurrence to walk.
        timezone: Its IANA zone.
        now: Reference instant (UTC). Defaults to now.

    Returns:
        The week's instants, ascending; empty when nothing fires this week
        (a monthly recurrence outside its day, for instance).
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
    """Every instant a schedule fires at on ONE local day.

    A LIST, not a single instant: a day may now hold several moments, and a
    caller that took the first would silently ignore the rest.

    Args:
        spec: The recurrence to walk.
        timezone: Its IANA zone.
        day: The local calendar day.

    Returns:
        The day's instants, ascending; empty when that day is not served.
    """
    tz = ZoneInfo(timezone)
    return slots_between(
        spec,
        timezone,
        start=_local_midnight(day, tz),
        end=_local_midnight(day + timedelta(days=1), tz),
    )


def served_slot(
    spec: RecurrenceSpec, timezone: str, *, due_at: datetime | None, now: datetime
) -> datetime | None:
    """Which slot a run starting now serves — the cell it will colour.

    A DUE run (``due_at <= now``) serves its due instant. A MANUAL one serves
    the LATEST slot of its local day that has already passed, and nothing at
    all when none has: a "test now" at 07:00 of an 08:00 schedule is a
    rehearsal, not the day's execution.

    With a single slot a day the rule reduces EXACTLY to the previous
    behaviour — verified over 140 scenarios, zero divergence — so no past run
    row stops matching its cell.

    Args:
        spec: The recurrence to walk.
        timezone: Its IANA zone.
        due_at: The pending due instant when the run started (UTC),
            or ``None`` when the series is over and nothing was pending — a
            manual run on an exhausted series reaches here.
        now: When the run started (UTC).

    Returns:
        The served instant, or ``None`` for a rehearsal.
    """
    if due_at is not None and due_at <= now:
        return due_at
    local_day = now.astimezone(ZoneInfo(timezone)).date()
    passed = [slot for slot in day_slots(spec, timezone, day=local_day) if slot <= now]
    return passed[-1] if passed else None


def rearm_after(
    spec: RecurrenceSpec, timezone: str, *, due_at: datetime | None, now: datetime | None = None
) -> datetime | None:
    """The instant to arm after a tick — scheduled or manual.

    **From ``max(due_at, now)``, never from ``due_at`` alone.** Measured
    2026-09-06 on a routine firing every 30 minutes: re-arming from the due
    instant fired 145 runs back-to-back when the server came back from a
    three-day outage; from ``max``, exactly one. A missed slot is missed — the
    system never replays three days of agent pipelines at restart.

    Taking the maximum also keeps a manual run ahead of schedule honest:
    testing an 08:00 schedule at 07:00 leaves today's 08:00 armed, because
    ``due_at`` is still ahead of ``now``.

    Args:
        spec: The recurrence to walk.
        timezone: Its IANA zone.
        due_at: The pending due instant when the tick started (UTC), or
            ``None`` when nothing was pending — a manual run on a series that
            is already over reaches here, and must not crash on a comparison
            against None.
        now: Current instant (UTC). Defaults to now.

    Returns:
        The next instant, or ``None`` when the series is over — which the
        caller stores as a null trigger.
    """
    reference = now or datetime.now(UTC)
    if due_at is not None and due_at > reference:
        # Nothing was consumed: the pending slot stands.
        return due_at
    return next_occurrence(spec, timezone, after=reference)
