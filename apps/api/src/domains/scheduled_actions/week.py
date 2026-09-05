"""The current week of every routine, cell by cell (ADR-265).

Pure: routines and run rows in, one ``ActionWeek`` per routine out. The
service fetches, the router serialises, and everything a test wants to pin —
which run colours which cell, what "today" is in Auckland when the server is
still on Sunday — lives here without a database.

The rule, in one sentence: **a cell takes the LAST run whose ``slot_at``
equals the week's instant for that day.** Equality, never a window: the
instants come from the same engine that armed the runs
(:func:`~src.domains.scheduled_actions.schedule_helpers.week_slots`), so a
schedule change moves them and old runs stop matching by construction. A
rehearsal (``slot_at`` NULL) colours nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.time_utils import now_utc
from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionRun,
    ScheduledRunOutcome,
)
from src.domains.scheduled_actions.schedule_helpers import week_slots, week_start


@dataclass(frozen=True)
class WeekCell:
    """One configured day of the current week for one routine."""

    day: int
    """ISO weekday, 1 = Monday … 7 = Sunday, in the routine's zone."""
    date: date
    """The local calendar date."""
    slot_at: datetime
    """The instant the routine fires at that day (UTC)."""
    outcome: ScheduledRunOutcome | None
    """How the LAST run serving this slot ended; ``None`` = no run served it."""
    run_at: datetime | None
    """When that run started (UTC)."""
    error: str | None
    """Its error, for a failure."""
    manual: bool | None
    """Whether that run was started by the user."""


@dataclass(frozen=True)
class ActionWeek:
    """The current week of one routine."""

    action_id: UUID
    timezone: str
    week_start: date
    today: int
    """ISO weekday of NOW in the routine's zone — the column to highlight."""
    cells: list[WeekCell]


def week_read_lower_bound(
    actions: Sequence[ScheduledAction], *, now: datetime | None = None
) -> datetime | None:
    """The earliest instant a run of THIS week could have started at.

    One bound for the whole account, so the runs come back in one query: the
    earliest local Monday midnight across the zones the routines use.

    Args:
        actions: The account's routines.
        now: Reference instant (UTC). Defaults to now.

    Returns:
        The bound, or ``None`` when there is no routine to read for.
    """
    reference = now or now_utc()
    bounds: list[datetime] = []
    for zone in {action.user_timezone for action in actions}:
        tz = ZoneInfo(zone)
        monday = week_start(tz, now=reference)
        bounds.append(datetime.combine(monday, datetime.min.time(), tzinfo=tz))
    return min(bounds) if bounds else None


def fold_runs_by_slot(
    runs: Iterable[ScheduledActionRun],
) -> dict[tuple[UUID, datetime], ScheduledActionRun]:
    """The LAST run per (routine, slot), rehearsals dropped.

    Args:
        runs: Run rows, oldest first (the repository's order) — a later row
            simply overwrites an earlier one for the same slot.

    Returns:
        The latest run for every served slot.
    """
    latest: dict[tuple[UUID, datetime], ScheduledActionRun] = {}
    for run in runs:
        if run.slot_at is None:
            continue
        key = (run.scheduled_action_id, run.slot_at)
        previous = latest.get(key)
        if previous is None or run.started_at >= previous.started_at:
            latest[key] = run
    return latest


def build_week(
    actions: Sequence[ScheduledAction],
    runs: Iterable[ScheduledActionRun],
    *,
    now: datetime | None = None,
) -> list[ActionWeek]:
    """One ``ActionWeek`` per routine, in the order the routines were given.

    Args:
        actions: The account's routines, paused ones included — a paused
            routine keeps its cells (grey is the client's call, from
            ``is_enabled``), so pausing never blanks the history of the week.
        runs: The account's run rows since :func:`week_read_lower_bound`.
        now: Reference instant (UTC). Defaults to now.

    Returns:
        The weeks.
    """
    reference = now or now_utc()
    latest = fold_runs_by_slot(runs)
    weeks: list[ActionWeek] = []
    for action in actions:
        tz = ZoneInfo(action.user_timezone)
        monday = week_start(tz, now=reference)
        cells: list[WeekCell] = []
        for slot in week_slots(
            action.days_of_week,
            action.trigger_hour,
            action.trigger_minute,
            action.user_timezone,
            now=reference,
        ):
            local = slot.astimezone(tz)
            run = latest.get((action.id, slot))
            cells.append(
                WeekCell(
                    day=local.isoweekday(),
                    date=local.date(),
                    slot_at=slot,
                    outcome=run.outcome if run is not None else None,
                    run_at=run.started_at if run is not None else None,
                    error=run.error if run is not None else None,
                    manual=run.manual if run is not None else None,
                )
            )
        weeks.append(
            ActionWeek(
                action_id=action.id,
                timezone=action.user_timezone,
                week_start=monday,
                today=reference.astimezone(tz).isoweekday(),
                cells=cells,
            )
        )
    return weeks
