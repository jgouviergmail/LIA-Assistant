"""Per-source fetchers and pure row→event mappers (Lot 1-A1).

Contract per fetcher (briefing doctrine):
- Acquires its OWN session via ``get_db_context()`` — the service runs
  fetchers in parallel and AsyncSession is not concurrent-safe.
- Returns ``list[KindBundle]``: one bundle per event kind it produces
  (open loops produce two), each carrying the exact windowed total and a
  ``truncated`` flag when the cap dropped rows (stated, never silent).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from src.domains.activity.constants import (
    ACTIVITY_KIND_HABIT_DETECTED,
    ACTIVITY_KIND_HEARTBEAT_NOTIFICATION,
    ACTIVITY_KIND_INTEREST_NOTIFICATION,
    ACTIVITY_KIND_JOURNAL_ENTRY,
    ACTIVITY_KIND_OPEN_LOOP_CLOSED,
    ACTIVITY_KIND_OPEN_LOOP_CREATED,
    ACTIVITY_KIND_SCHEDULED_ACTION_RUN,
)
from src.domains.activity.repository import ActivityReadRepository
from src.domains.activity.schemas import ActivityEvent
from src.domains.open_loops.models import OpenLoopStatus
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from collections.abc import Sequence

_ENDED_LOOP_STATUSES = (OpenLoopStatus.CLOSED.value, OpenLoopStatus.EXPIRED.value)


@dataclass(frozen=True)
class KindBundle:
    """Events of one kind plus its exact windowed total."""

    kind: str
    events: list[ActivityEvent]
    total: int
    truncated: bool


# =============================================================================
# Row shapes (structural): what each mapper actually reads. Keeps mappers
# strictly typed without coupling them to the ORM classes — SimpleNamespace
# test rows satisfy them structurally.
# =============================================================================


class NotificationRow(Protocol):
    """Heartbeat/interest notification row surface consumed by mappers."""

    id: UUID
    content: str | None
    created_at: datetime


class HeartbeatRow(NotificationRow, Protocol):
    """Heartbeat notification row (adds the priority qualifier)."""

    priority: str


class JournalRow(Protocol):
    """Automatic journal entry row surface."""

    id: UUID
    title: str
    source: str
    created_at: datetime


class HabitRow(Protocol):
    """Detected habit row surface."""

    id: UUID
    key: str
    status: str
    created_at: datetime


class LoopRow(Protocol):
    """Open-loop row surface (lifecycle events)."""

    id: UUID
    subject: str
    status: str
    closed_reason: str | None
    created_at: datetime
    updated_at: datetime


class ScheduledActionRow(Protocol):
    """Scheduled action row surface (last execution)."""

    id: UUID
    title: str
    last_executed_at: datetime | None


class FetchFn(Protocol):
    """Signature every timeline source fetcher satisfies."""

    async def __call__(
        self, *, user_id: UUID, since: datetime, cap: int
    ) -> list[KindBundle]:  # pragma: no cover - protocol
        ...


# =============================================================================
# Pure mappers (SimpleNamespace-friendly: attribute access only)
# =============================================================================


def map_heartbeat_notification(row: HeartbeatRow) -> ActivityEvent:
    """Heartbeat notification row → event (text=content, status=priority)."""
    return ActivityEvent(
        kind=ACTIVITY_KIND_HEARTBEAT_NOTIFICATION,
        ref_id=str(row.id),
        occurred_at=row.created_at,
        text=row.content,
        status=row.priority,
    )


def map_interest_notification(row: NotificationRow) -> ActivityEvent:
    """Interest notification row → event. ``content`` may be NULL (pre-2026-08-03)."""
    return ActivityEvent(
        kind=ACTIVITY_KIND_INTEREST_NOTIFICATION,
        ref_id=str(row.id),
        occurred_at=row.created_at,
        text=row.content,
    )


def map_journal_entry(row: JournalRow) -> ActivityEvent:
    """Automatic journal entry row → event (text=title, status=source)."""
    return ActivityEvent(
        kind=ACTIVITY_KIND_JOURNAL_ENTRY,
        ref_id=str(row.id),
        occurred_at=row.created_at,
        text=row.title,
        status=row.source,
    )


def map_habit(row: HabitRow) -> ActivityEvent:
    """Detected habit row → event (text=key, status=current status)."""
    return ActivityEvent(
        kind=ACTIVITY_KIND_HABIT_DETECTED,
        ref_id=str(row.id),
        occurred_at=row.created_at,
        text=row.key,
        status=row.status,
    )


def map_scheduled_action(row: ScheduledActionRow) -> ActivityEvent:
    """Scheduled action row → event anchored on its LAST execution.

    Raises:
        ValueError: If the row has never executed — the repository filters
            ``last_executed_at IS NOT NULL``, so this is a contract breach.
    """
    if row.last_executed_at is None:
        raise ValueError(f"scheduled action {row.id} has no last_executed_at")
    return ActivityEvent(
        kind=ACTIVITY_KIND_SCHEDULED_ACTION_RUN,
        ref_id=str(row.id),
        occurred_at=row.last_executed_at,
        text=row.title,
    )


def map_open_loop(row: LoopRow, *, since: datetime) -> list[ActivityEvent]:
    """Loop row → 0-2 lifecycle events (created and/or ended in window).

    An ended loop's timestamp is ``updated_at``: a loop leaves OPEN exactly
    once and is never mutated afterwards (open_loops repository contract).
    Expired loops surface their end honestly with status ``expired``.
    """
    events: list[ActivityEvent] = []
    if row.created_at >= since:
        events.append(
            ActivityEvent(
                kind=ACTIVITY_KIND_OPEN_LOOP_CREATED,
                ref_id=str(row.id),
                occurred_at=row.created_at,
                text=row.subject,
            )
        )
    if row.status in _ENDED_LOOP_STATUSES and row.updated_at >= since:
        status = row.closed_reason if row.status == OpenLoopStatus.CLOSED.value else row.status
        events.append(
            ActivityEvent(
                kind=ACTIVITY_KIND_OPEN_LOOP_CLOSED,
                ref_id=str(row.id),
                occurred_at=row.updated_at,
                text=row.subject,
                status=status,
            )
        )
    return events


# =============================================================================
# Fetchers (own session each — parallel-safe)
# =============================================================================


def _bundle(kind: str, events: Sequence[ActivityEvent], total: int) -> KindBundle:
    return KindBundle(kind=kind, events=list(events), total=total, truncated=total > len(events))


async def fetch_heartbeat_notifications(
    *, user_id: UUID, since: datetime, cap: int
) -> list[KindBundle]:
    """Heartbeat notifications sent in the window."""
    async with get_db_context() as db:
        rows, total = await ActivityReadRepository(db).heartbeat_notifications_since(
            user_id, since, cap
        )
    return [
        _bundle(
            ACTIVITY_KIND_HEARTBEAT_NOTIFICATION,
            [map_heartbeat_notification(r) for r in rows],
            total,
        )
    ]


async def fetch_interest_notifications(
    *, user_id: UUID, since: datetime, cap: int
) -> list[KindBundle]:
    """Interest notifications sent in the window."""
    async with get_db_context() as db:
        rows, total = await ActivityReadRepository(db).interest_notifications_since(
            user_id, since, cap
        )
    return [
        _bundle(
            ACTIVITY_KIND_INTEREST_NOTIFICATION,
            [map_interest_notification(r) for r in rows],
            total,
        )
    ]


async def fetch_journal_entries(*, user_id: UUID, since: datetime, cap: int) -> list[KindBundle]:
    """Automatic journal entries written in the window."""
    async with get_db_context() as db:
        rows, total = await ActivityReadRepository(db).journal_entries_since(user_id, since, cap)
    return [_bundle(ACTIVITY_KIND_JOURNAL_ENTRY, [map_journal_entry(r) for r in rows], total)]


async def fetch_habits(*, user_id: UUID, since: datetime, cap: int) -> list[KindBundle]:
    """Habits detected in the window."""
    async with get_db_context() as db:
        rows, total = await ActivityReadRepository(db).habits_since(user_id, since, cap)
    return [_bundle(ACTIVITY_KIND_HABIT_DETECTED, [map_habit(r) for r in rows], total)]


async def fetch_open_loops(*, user_id: UUID, since: datetime, cap: int) -> list[KindBundle]:
    """Open-loop lifecycle events (created / ended) in the window."""
    async with get_db_context() as db:
        rows, created_total, closed_total = await ActivityReadRepository(db).open_loops_since(
            user_id, since, cap
        )
    created: list[ActivityEvent] = []
    closed: list[ActivityEvent] = []
    for row in rows:
        for event in map_open_loop(row, since=since):
            (created if event.kind == ACTIVITY_KIND_OPEN_LOOP_CREATED else closed).append(event)
    return [
        _bundle(ACTIVITY_KIND_OPEN_LOOP_CREATED, created, created_total),
        _bundle(ACTIVITY_KIND_OPEN_LOOP_CLOSED, closed, closed_total),
    ]


async def fetch_scheduled_action_runs(
    *, user_id: UUID, since: datetime, cap: int
) -> list[KindBundle]:
    """Scheduled actions whose last execution falls in the window."""
    async with get_db_context() as db:
        rows, total = await ActivityReadRepository(db).scheduled_action_runs_since(
            user_id, since, cap
        )
    return [
        _bundle(
            ACTIVITY_KIND_SCHEDULED_ACTION_RUN,
            [map_scheduled_action(r) for r in rows],
            total,
        )
    ]


@dataclass(frozen=True)
class TimelineSource:
    """Registry entry binding a fetcher to the kinds it produces."""

    kinds: tuple[str, ...]
    fetch: FetchFn


# Registry: every declared kind is produced by exactly one fetcher — the
# completeness is guarded by tests/unit/domains/activity/test_fetchers.py.
ALL_SOURCE_FETCHERS: tuple[TimelineSource, ...] = (
    TimelineSource((ACTIVITY_KIND_HEARTBEAT_NOTIFICATION,), fetch_heartbeat_notifications),
    TimelineSource((ACTIVITY_KIND_INTEREST_NOTIFICATION,), fetch_interest_notifications),
    TimelineSource((ACTIVITY_KIND_JOURNAL_ENTRY,), fetch_journal_entries),
    TimelineSource((ACTIVITY_KIND_HABIT_DETECTED,), fetch_habits),
    TimelineSource(
        (ACTIVITY_KIND_OPEN_LOOP_CREATED, ACTIVITY_KIND_OPEN_LOOP_CLOSED), fetch_open_loops
    ),
    TimelineSource((ACTIVITY_KIND_SCHEDULED_ACTION_RUN,), fetch_scheduled_action_runs),
)
