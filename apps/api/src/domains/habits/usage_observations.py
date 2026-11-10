"""Gather what one person's usage shows, for the proposal rules (ADR-375).

Everything the rules read is already recorded by LIA — nothing here stores a
new fact: the request ledger (per-domain days and hours), the activity rollup
(days and hours present), the person's routines and their runs, what those runs
read (the treatments register, through ``usage_ports``), what proactive
notifications met (``usage_ports``), the active connectors and the person's
earlier decisions. The rules stay pure; this module is their only I/O.

« Unknown » is never folded into « none »: a routine that could serve a need
but has no run naming its turn reads as unknown (``read_domains=None``), a
missing port as an absent fact, an unreadable ledger as ``readable=False`` —
and the rules hold what those facts feed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.recurrence import RecurrenceSpec
from src.core.time_utils import resolve_user_timezone
from src.domains.connectors.models import Connector, ConnectorStatus, get_functional_category
from src.domains.habits.models import HabitKind
from src.domains.habits.need_domains import NEED_DOMAINS
from src.domains.habits.needs import Need, NeedThresholds, detect_need
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.habits.proposal_rules import (
    ProactiveFeedback,
    RoutineRun,
    RoutineView,
    UsageObservations,
)
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.usage_ports import proactive_feedback_reader, routine_reads_reader
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.run_repository import ScheduledActionRunRepository
from src.infrastructure.cache import recurrence_store

logger = structlog.get_logger(__name__)

_ALL_DAYS = frozenset(range(7))


@dataclass(frozen=True, slots=True)
class LedgerView:
    """The request ledger of one person, as read tonight.

    Attributes:
        readable: False when Redis could not be read — never « empty ».
        days_by_domain: Per signature, per local day, the hours asked.
        intents: Per signature, the dominant analyzer intent, when recorded.
    """

    readable: bool
    days_by_domain: Mapping[str, Mapping[date, list[float]]]
    intents: Mapping[str, str | None]


async def read_ledger(user_id: UUID) -> LedgerView:
    """Read every ledger key of a person; a failure is ``readable=False``.

    Args:
        user_id: Owner.

    Returns:
        The ledger view.
    """
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return LedgerView(readable=False, days_by_domain={}, intents={})
        days: dict[str, dict[date, list[float]]] = {}
        intents: dict[str, str | None] = {}
        async for key in redis.scan_iter(match=recurrence_store.user_key_pattern(str(user_id))):
            signature = recurrence_store.signature_from_key(key, str(user_id))
            if not signature:
                continue
            payload = await recurrence_store.load(redis, key)
            days[signature] = recurrence_store.parse_days(payload)
            intents[signature] = recurrence_store.dominant_intent(payload)
        return LedgerView(readable=True, days_by_domain=days, intents=intents)
    except Exception as exc:  # noqa: BLE001 — never conclude on doubt
        logger.warning(
            "habit_ledger_unreadable", user_id=str(user_id), error_type=type(exc).__name__
        )
        return LedgerView(readable=False, days_by_domain={}, intents={})


def needs_from_ledger(
    ledger: LedgerView, *, active_days: int, today: date, thresholds: NeedThresholds
) -> tuple[Need, ...]:
    """The person's recurring needs, one per registered domain.

    A composed legacy signature (``email+contact``) or a stray spelling is not
    a registered domain: no need is read from it.

    Args:
        ledger: The ledger view.
        active_days: Days the person used LIA inside the window.
        today: The person's local date.
        thresholds: The need bars.

    Returns:
        The needs, sorted by domain; empty when the ledger was unreadable.
    """
    if not ledger.readable:
        return ()
    found = (
        detect_need(domain, days, active_days=active_days, today=today, thresholds=thresholds)
        for domain, days in sorted(ledger.days_by_domain.items())
        if domain in NEED_DOMAINS
    )
    return tuple(need for need in found if need is not None)


def routine_schedule(spec: RecurrenceSpec | None) -> tuple[tuple[float, ...], frozenset[int]]:
    """A routine's daily times and the weekdays it fires on EVERY week.

    A calendar that skips days (every other day or week, a monthly, yearly or
    single date) fires on no weekday every week: it serves no daily or weekly
    need.

    Args:
        spec: The routine's schedule; None for a condition routine.

    Returns:
        ``(local hours, weekdays 0=Monday..6=Sunday)``.
    """
    if spec is None:
        return (), frozenset()
    times = tuple(moment.hour + moment.minute / 60 for moment in spec.times.materialise())
    if spec.interval != 1:
        return times, frozenset()
    if spec.freq == "daily":
        return times, _ALL_DAYS
    if spec.freq == "weekly":
        return times, frozenset(day - 1 for day in spec.byweekday)
    return times, frozenset()


def _routine_run(run: Any, tz: ZoneInfo) -> RoutineRun:
    """One run row, in the person's local time."""
    local = run.started_at.astimezone(tz)
    return RoutineRun(
        day=local.date(),
        hour=local.hour + local.minute / 60,
        manual=bool(run.manual),
        outcome=str(getattr(run.outcome, "value", run.outcome)),
        run_id=run.run_id,
    )


def _read_domains(
    could_serve: bool, linked: list[str], reads: Mapping[str, frozenset[str]] | None
) -> frozenset[str] | None:
    """What a routine's runs consulted — None when that is UNKNOWN.

    A routine that could serve a need (enabled, on a clock, with days) and has
    no run linked to its turn, or no reader installed, is an unknown: it holds
    the automation proposals rather than reading as « serves nothing ».
    """
    if reads is None or not linked:
        return None if could_serve else frozenset()
    return frozenset().union(*(reads.get(run_id, frozenset()) for run_id in linked))


def _routine_view(
    action: ScheduledAction,
    runs: list[Any],
    reads: Mapping[str, frozenset[str]] | None,
    tz: ZoneInfo,
) -> RoutineView:
    spec = action.recurrence_spec
    times, fires_on = routine_schedule(spec)
    could_serve = bool(action.is_enabled) and action.trigger_kind == "time" and bool(fires_on)
    return RoutineView(
        id=str(action.id),
        title=action.title,
        enabled=bool(action.is_enabled),
        status=str(action.status),
        trigger_kind=str(action.trigger_kind),
        times=times,
        fires_on=fires_on,
        consecutive_failures=int(action.consecutive_failures or 0),
        runs=tuple(_routine_run(run, tz) for run in runs),
        read_domains=_read_domains(could_serve, [run.run_id for run in runs if run.run_id], reads),
        fixed_times=spec is not None and spec.times.mode == "at",
    )


async def _routine_views(
    db: AsyncSession, user_id: UUID, tz: ZoneInfo, since: datetime
) -> tuple[RoutineView, ...]:
    actions = (
        (await db.execute(select(ScheduledAction).where(ScheduledAction.user_id == user_id)))
        .scalars()
        .all()
    )
    runs_by_action: dict[UUID, list[Any]] = defaultdict(list)
    for run in await ScheduledActionRunRepository(db).list_since(user_id, since):
        runs_by_action[run.scheduled_action_id].append(run)
    linked = [run.run_id for runs in runs_by_action.values() for run in runs if run.run_id]
    reader = routine_reads_reader()
    reads = None if reader is None else (await reader(db, user_id, linked) if linked else {})
    return tuple(
        _routine_view(action, runs_by_action.get(action.id, []), reads, tz) for action in actions
    )


async def _connector_categories(db: AsyncSession, user_id: UUID) -> frozenset[str]:
    types = (
        await db.execute(
            select(Connector.connector_type).where(
                Connector.user_id == user_id, Connector.status == ConnectorStatus.ACTIVE
            )
        )
    ).scalars()
    return frozenset(
        category for category in (get_functional_category(kind) for kind in types) if category
    )


async def gather_usage_observations(
    db: AsyncSession,
    user: Any,
    *,
    ledger: LedgerView,
    today: date,
    settings: Any,
) -> UsageObservations:
    """Everything the proposal rules read about one person, for one night.

    Args:
        db: The recompute's session (every read rides it; none opens another).
        user: The ``User`` row (timezone, notification preferences).
        ledger: The ledger view read for the same night.
        today: The person's local date.
        settings: The application settings.

    Returns:
        The observations.
    """
    tz = resolve_user_timezone(user)
    window_days = int(settings.recurrence_window_days)
    window_start = today - timedelta(days=window_days)
    since = datetime.combine(window_start, time(0, 0), tzinfo=tz).astimezone(UTC)

    habits = HabitsRepository(db)
    rollup = {
        day: frozenset(hours)
        for day, hours in (await habits.fetch_activity_rollup(user.id)).items()
        if window_start < day <= today and hours
    }
    needs = needs_from_ledger(
        ledger,
        active_days=len(rollup),
        today=today,
        thresholds=NeedThresholds.from_settings(settings),
    )
    need_rows = await habits.list_habits(user.id, HabitKind.RECURRING_REQUEST.value)
    feedback_reader = proactive_feedback_reader()
    proactive: ProactiveFeedback | None = (
        await feedback_reader(db, user.id, since) if feedback_reader is not None else None
    )
    return UsageObservations(
        today=today,
        needs=needs,
        need_status={row.key: row.status for row in need_rows},
        asked_days={
            domain: sum(1 for day, hours in days.items() if window_start < day <= today and hours)
            for domain, days in ledger.days_by_domain.items()
        },
        routines=await _routine_views(db, user.id, tz, since),
        presence=rollup,
        heartbeat_enabled=bool(user.heartbeat_enabled),
        heartbeat_window=(
            int(user.heartbeat_notify_start_hour),
            int(user.heartbeat_notify_end_hour),
        ),
        proactive=proactive,
        connector_categories=await _connector_categories(db, user.id),
        refusals=await HabitProposalRepository(db).refusal_counts(user.id),
        ledger_readable=ledger.readable,
    )
