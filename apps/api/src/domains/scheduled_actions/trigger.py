"""When a routine next needs the executor — one answer for every kind (ADR-322).

A routine runs on ONE of three clocks, never two:

- a **time** routine follows its ``RecurrenceSpec`` — the person's own
  schedule, armed by the recurrence engine;
- a **condition** routine has no schedule at all. It waits for something, and
  the SYSTEM checks whether that something happened, at a cadence declared per
  condition type, day and night, until the optional last day it watches;
- a **webhook** routine has neither: another system calls its address, and the
  call arms it for the next pass (ADR-386). The plan only says when to look
  again; whether calls wait is the executor's gate to read.

The second clock replaces what used to be a schedule on BOTH kinds: a condition
was only evaluated at the hours its recurrence named, so a mail watch set up
from the briefing was read twice a day and could announce an awaited reply
eight to sixteen hours late (N-07 phase 1 said so: « cron stays the clock for
both kinds »).

Three rules the cadence turns on:

- **it is declared, per condition type, in ONE table** (:data:`CONDITION_CHECKS`)
  whose completeness is asserted at import — the scheduler imports this module
  at boot, so a condition type added without a cadence refuses to boot instead
  of dying invisibly (ADR-085);
- **a check is never faster than the cache its source reads through.** The
  mail search is cached (``emails_cache_search_ttl_seconds``): a faster check
  would re-read Redis, and file a consultation for a mailbox nobody opened;
- **each routine keeps its own phase**, derived from its id. Twenty watches
  created in the same minute would otherwise check the same providers in the
  same second forever — the rule ``jitter_seconds_for`` enforces on interval
  jobs, applied here to rows. A phase never drifts: a check that took seven
  seconds re-arms on the same grid.

Pure: no database, no provider. The service arms, the executor re-arms, and
both ask this module.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.constants import (
    ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS,
    SCHEDULED_ACTIONS_CATCH_UP_LOOKBACK_DAYS,
)
from src.core.i18n_routine_triggers import condition_cadence, webhook_trigger
from src.core.recurrence import (
    RecurrenceSpec,
    describe,
    describe_until,
    join_clauses,
    latest_occurrence,
    next_occurrence,
    rearm_after,
)
from src.domains.scheduled_actions.models import (
    CONDITION_TYPE_CALENDAR_EVENT,
    CONDITION_TYPE_DOCUMENT_ADDED,
    CONDITION_TYPE_MAIL_MATCH,
    CONDITION_TYPE_PAGE_CHANGE,
    CONDITION_TYPE_TASK_OVERDUE,
    CONDITION_TYPE_WEATHER_CHANGE,
    CONDITION_TYPES,
    TriggerKind,
)

#: The key of the last watched day inside ``condition_config``.
CONDITION_UNTIL_KEY: Final[str] = "until"


@dataclass(frozen=True, slots=True)
class ConditionCheck:
    """How often one condition type is checked.

    Attributes:
        interval_setting: The ``settings`` attribute holding the cadence, in
            minutes.
        source_ttl_setting: The ``settings`` attribute holding the TTL, in
            seconds, of the cache the source reads through — ``None`` when the
            source reads live. Declared only where a cache is actually applied:
            a TTL setting nobody reads would make this table a claim.
    """

    interval_setting: str
    source_ttl_setting: str | None = None


#: The cadence of every condition type. The four connector sources share one
#: setting; the forecast has its own, slower one.
CONDITION_CHECKS: Final[Mapping[str, ConditionCheck]] = MappingProxyType(
    {
        CONDITION_TYPE_TASK_OVERDUE: ConditionCheck("scheduled_actions_condition_check_minutes"),
        CONDITION_TYPE_MAIL_MATCH: ConditionCheck(
            "scheduled_actions_condition_check_minutes",
            # The Gmail search is the one cached read of the four.
            source_ttl_setting="emails_cache_search_ttl_seconds",
        ),
        CONDITION_TYPE_DOCUMENT_ADDED: ConditionCheck("scheduled_actions_condition_check_minutes"),
        CONDITION_TYPE_CALENDAR_EVENT: ConditionCheck("scheduled_actions_condition_check_minutes"),
        CONDITION_TYPE_WEATHER_CHANGE: ConditionCheck("scheduled_actions_weather_check_minutes"),
        # A public page, read at its own pace (ADR-387).
        CONDITION_TYPE_PAGE_CHANGE: ConditionCheck("scheduled_actions_page_check_minutes"),
    }
)


def _assert_cadence_completeness() -> None:
    """Refuse to import with a condition type the table does not cover.

    Raises:
        RuntimeError: When the table and ``CONDITION_TYPES`` disagree, or a
            declared setting does not exist.
    """
    missing = CONDITION_TYPES - CONDITION_CHECKS.keys()
    unknown = CONDITION_CHECKS.keys() - CONDITION_TYPES
    if missing or unknown:
        raise RuntimeError(
            f"Condition cadence table incomplete: missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )
    for condition_type, check in CONDITION_CHECKS.items():
        for attribute in (check.interval_setting, check.source_ttl_setting):
            if attribute is not None and not hasattr(settings, attribute):
                raise RuntimeError(
                    f"Condition cadence of {condition_type!r} names an unknown "
                    f"setting: {attribute!r}"
                )


_assert_cadence_completeness()


def check_interval(condition_type: str) -> timedelta:
    """How often a condition of this type is checked.

    Args:
        condition_type: One of ``CONDITION_TYPES``.

    Returns:
        The larger of the declared cadence and the source's cache TTL.

    Raises:
        KeyError: For a type the vocabulary does not know — never guessed.
    """
    check = CONDITION_CHECKS[condition_type]
    interval = timedelta(minutes=int(getattr(settings, check.interval_setting)))
    if check.source_ttl_setting is None:
        return interval
    return max(interval, timedelta(seconds=int(getattr(settings, check.source_ttl_setting))))


def next_check(action_id: UUID, interval: timedelta, now: datetime) -> datetime:
    """The routine's next check: strictly after ``now``, on its own phase.

    The phase is derived from the id, so it is stable for the life of the
    routine and spread across routines; the grid is anchored on the epoch, so
    re-arming a few seconds late lands on the same grid rather than drifting.

    Args:
        action_id: The routine.
        interval: Its check interval (whole seconds).
        now: Reference instant (UTC).

    Returns:
        The first instant of the routine's grid strictly after ``now``.
    """
    period = max(1, int(interval.total_seconds()))
    phase = int(action_id.hex[:8], 16) % period
    elapsed = int(now.timestamp()) - phase
    return datetime.fromtimestamp((elapsed // period + 1) * period + phase, UTC)


def watch_end(until: date | None, timezone: str) -> datetime | None:
    """The instant a watch stops: the local midnight AFTER its last day.

    Built from the calendar, never by adding 24 hours to an instant: a day of
    clock change lasts 23 or 25 hours.

    Args:
        until: The last local day watched, included; ``None`` for no end.
        timezone: The routine's IANA zone.

    Returns:
        The end instant (UTC), or ``None`` when the watch has no end.
    """
    if until is None:
        return None
    following = until + timedelta(days=1)
    local_midnight = datetime.combine(following, datetime.min.time(), tzinfo=ZoneInfo(timezone))
    return local_midnight.replace(fold=0).astimezone(UTC)


def condition_until(condition_config: Mapping[str, Any] | None) -> date | None:
    """The last day a stored condition watches, read forgivingly.

    Writes are strict (the API schema validates the date); a value no writer
    produces reads as « no end » rather than taking a background tick down.

    Args:
        condition_config: The stored ``condition_config``.

    Returns:
        The day, or ``None``.
    """
    if not condition_config:
        return None
    raw = condition_config.get(CONDITION_UNTIL_KEY)
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


class _RoutineRow(Protocol):
    """The fields of a routine a plan is read from."""

    @property
    def id(self) -> UUID: ...

    @property
    def trigger_kind(self) -> str: ...

    @property
    def recurrence_spec(self) -> RecurrenceSpec | None: ...

    @property
    def condition_config(self) -> dict[str, Any] | None: ...

    @property
    def user_timezone(self) -> str: ...


@dataclass(frozen=True, slots=True)
class DueOccurrence:
    """An occurrence the scheduler found due, and how long it may still be served.

    Attributes:
        at: The occurrence (UTC).
        late_after: Past this instant it no longer starts; ``None`` when
            nothing follows it — it is then never given up.
        retry_until: Until when it stays armed for an account found busy.
    """

    at: datetime
    late_after: datetime | None
    retry_until: datetime

    def is_late(self, now: datetime) -> bool:
        """Whether ``now`` is past the catch-up window of this occurrence."""
        return self.late_after is not None and now > self.late_after


@dataclass(frozen=True, slots=True)
class TriggerPlan:
    """Everything that decides when one routine runs, and nothing else.

    Attributes:
        action_id: The routine — the phase of its checks.
        trigger_kind: ``time``, ``condition`` or ``webhook``.
        recurrence: The schedule of a time routine; ``None`` for a condition.
        condition_config: The condition of a condition routine, ``until``
            included; ``None`` for a time routine.
        timezone: The zone its days are read in.
    """

    action_id: UUID
    trigger_kind: str
    recurrence: RecurrenceSpec | None
    condition_config: Mapping[str, Any] | None
    timezone: str

    @classmethod
    def of(cls, action: _RoutineRow, *, timezone: str | None = None) -> TriggerPlan:
        """The plan of a stored routine.

        Args:
            action: The routine.
            timezone: A zone replacing the stored one — a person who just
                moved keeps « 08:00 where I live ».

        Returns:
            The plan.
        """
        return cls(
            action_id=action.id,
            trigger_kind=action.trigger_kind,
            recurrence=action.recurrence_spec,
            condition_config=action.condition_config,
            timezone=timezone or action.user_timezone,
        )

    @property
    def is_condition(self) -> bool:
        """Whether the system's clock, rather than a schedule, drives it."""
        return self.trigger_kind == TriggerKind.CONDITION.value

    @property
    def is_webhook(self) -> bool:
        """Whether another system's signed call drives it (ADR-386)."""
        return self.trigger_kind == TriggerKind.WEBHOOK.value

    def first(self, now: datetime) -> datetime | None:
        """The instant to arm when the routine is created, edited, re-enabled or moved.

        A webhook routine looks at once: the next pass serves the calls that
        waited (a pause keeps them), and finding none it sleeps until a call
        wakes it (ADR-386).

        Args:
            now: Reference instant (UTC).

        Returns:
            The instant, or ``None`` when nothing follows.
        """
        if self.is_webhook:
            return now
        if self.is_condition:
            return self._check_after(now)
        if self.recurrence is None:
            return None
        return next_occurrence(self.recurrence, self.timezone, after=now)

    def after_tick(
        self, *, due_at: datetime | None, now: datetime, failed: bool = False
    ) -> datetime | None:
        """The instant to arm once a tick has ended.

        A condition re-arms from NOW: a missed check is missed, three days of
        downtime replay nothing. A schedule keeps ``rearm_after``'s rule — a
        manual run ahead of its slot leaves the slot armed. A webhook routine
        looks again at the next pass, where its gate serves what still waits or
        settles with nothing armed; after a FAILED run it backs off first, the
        run having already retried inside itself (ADR-386).

        Args:
            due_at: The pending due instant when the tick started, or ``None``.
            now: Reference instant (UTC).
            failed: Whether the tick's run failed. Only a webhook routine reads
                it: the other clocks re-arm the same way whatever the outcome.

        Returns:
            The instant, or ``None`` when nothing follows.
        """
        if self.is_webhook:
            return now + timedelta(seconds=ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS) if failed else now
        if self.is_condition:
            return self._check_after(now)
        if self.recurrence is None:
            return None
        return rearm_after(self.recurrence, self.timezone, due_at=due_at, now=now)

    def catch_up_deadline(self, due_at: datetime) -> datetime | None:
        """The last instant an occurrence due at ``due_at`` may still start.

        Half the gap to the occurrence that follows it, capped by the
        operator's maximum (ADR-265 amendment 2026-11-12 b): the routine's own
        rhythm says when its occurrence is stale. An occurrence whose successor
        has already come is therefore ALWAYS past its deadline — only the most
        recent occurrence can still start.

        Args:
            due_at: The occurrence (UTC).

        Returns:
            The deadline, or ``None`` when the occurrence is never given up: a
            condition routine has no occurrence, and one nothing follows is all
            that is left of what the person asked for.
        """
        if self.is_condition or self.recurrence is None:
            return None
        following = next_occurrence(self.recurrence, self.timezone, after=due_at)
        if following is None:
            return None
        return due_at + min((following - due_at) / 2, _catch_up_maximum())

    def retry_deadline(self, due_at: datetime) -> datetime | None:
        """Until when an occurrence that found its account busy stays armed.

        As long as it may still start. The last occurrence of a series is
        never given up for lateness, but an account busy for hours is not a
        turn under way: its wait is bounded by the same maximum.

        Args:
            due_at: The occurrence (UTC).

        Returns:
            The instant, or ``None`` for a routine with no occurrence.
        """
        if self.is_condition or self.recurrence is None:
            return None
        return self.catch_up_deadline(due_at) or due_at + _catch_up_maximum()

    def due_occurrence(
        self, *, due_at: datetime | None, started_at: datetime
    ) -> DueOccurrence | None:
        """The occurrence a tick was due for, with its catch-up bounds.

        Args:
            due_at: The pending due instant when the tick started.
            started_at: When the tick started (UTC).

        Returns:
            The occurrence, or ``None`` when none was due: a run the person
            started ahead of its slot, a finished series, a watch.
        """
        if due_at is None or due_at > started_at:
            return None
        retry_until = self.retry_deadline(due_at)
        if retry_until is None:
            return None
        return DueOccurrence(
            at=due_at, late_after=self.catch_up_deadline(due_at), retry_until=retry_until
        )

    def after_missed(self, *, due_at: datetime, now: datetime) -> datetime | None:
        """The instant to arm once the occurrence due at ``due_at`` is given up.

        The most recent occurrence that came since, when it may still start —
        an outage ending twenty minutes after today's slot serves TODAY — else
        the next one to come. Never an occurrence in between: a missed slot is
        missed, and three days of outage replay nothing (``rearm_after``'s rule).

        Args:
            due_at: The occurrence given up (UTC).
            now: Reference instant (UTC).

        Returns:
            The instant, or ``None`` when nothing follows.
        """
        if self.is_condition:
            return self._check_after(now)
        if self.recurrence is None:
            return None
        latest = latest_occurrence(
            self.recurrence,
            self.timezone,
            after=due_at,
            until=now,
            max_days=SCHEDULED_ACTIONS_CATCH_UP_LOOKBACK_DAYS,
        )
        if latest is not None:
            deadline = self.catch_up_deadline(latest)
            if deadline is None or now <= deadline:
                return latest
        return next_occurrence(self.recurrence, self.timezone, after=now)

    @property
    def condition_type(self) -> str:
        """The stored condition type, ``""`` for a time routine."""
        return str((self.condition_config or {}).get("type") or "")

    def _check_after(self, now: datetime) -> datetime | None:
        """The next check, or ``None`` once the last watched day is over."""
        if self.condition_type not in CONDITION_CHECKS:
            return None
        armed = next_check(self.action_id, check_interval(self.condition_type), now)
        end = watch_end(condition_until(self.condition_config), self.timezone)
        if end is not None and armed >= end:
            return None
        return armed


def _catch_up_maximum() -> timedelta:
    """The longest an occurrence may start late, read at each call."""
    return timedelta(minutes=settings.scheduled_actions_catch_up_max_minutes)


def check_minutes(plan: TriggerPlan) -> int | None:
    """The interval a person is told a condition routine is checked at.

    The figure APPLIED — the larger of the cadence and the source's cache —
    rounded up to the minute, so the sentence never promises a faster check
    than the one that happens.

    Args:
        plan: The routine's plan.

    Returns:
        Whole minutes, or ``None`` for a time routine or an unknown type.
    """
    if not plan.is_condition or plan.condition_type not in CONDITION_CHECKS:
        return None
    return _whole_minutes(check_interval(plan.condition_type))


def published_check_minutes() -> dict[str, int]:
    """The check interval of every condition type, as a person is told it.

    Returns:
        ``{condition_type: whole minutes}``, from the same rule as
        :func:`check_minutes`.
    """
    return {
        condition_type: _whole_minutes(check_interval(condition_type))
        for condition_type in sorted(CONDITION_CHECKS)
    }


def _whole_minutes(interval: timedelta) -> int:
    """An interval in whole minutes, rounded UP — never a promise of a faster check."""
    return math.ceil(interval.total_seconds() / 60)


def schedule_sentence(plan: TriggerPlan, language: str) -> str:
    """The one sentence saying when a routine runs, in the reader's language.

    Read by the studio card, the hub and the chat's listing tool alike, so a
    condition routine is never described by a schedule it no longer has.

    Args:
        plan: The routine's plan.
        language: The reader's language, raw.

    Returns:
        The recurrence sentence of a time routine; the check cadence of a
        condition routine, followed by its last day when it has one; what
        starts a webhook routine.
    """
    if plan.is_webhook:
        return webhook_trigger(language)
    if not plan.is_condition:
        return describe(plan.recurrence, language) if plan.recurrence is not None else ""
    minutes = check_minutes(plan)
    if minutes is None:
        return ""
    until = condition_until(plan.condition_config)
    return join_clauses(
        [
            condition_cadence(language, minutes=minutes),
            describe_until(until, language) if until is not None else "",
        ],
        language,
    )


__all__ = [
    "CONDITION_CHECKS",
    "CONDITION_UNTIL_KEY",
    "ConditionCheck",
    "DueOccurrence",
    "TriggerPlan",
    "check_interval",
    "check_minutes",
    "condition_until",
    "next_check",
    "published_check_minutes",
    "schedule_sentence",
    "watch_end",
]
