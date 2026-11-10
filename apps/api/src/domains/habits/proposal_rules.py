"""Proposal rules — what LIA offers from what it observed, decided by code (ADR-375).

Six kinds, each a pure rule over plain observations gathered by
``usage_observations``; no model, no I/O. A rule fires on facts the person can
check on the card (days, hours, counts), and its payload carries everything
the action needs, so nothing is re-derived when the person accepts.

An observation LIA could not make HOLDS the kinds it feeds — a routine whose
reads are unknown, a feedback source never installed, a ledger that could not
be read. A held kind proposes nothing new and withdraws nothing open: doubt
never reads as « nothing to propose » (the ADR-292 doctrine, applied here).

Three refusals of one kind silence that kind for the person: that is the
learning from decisions, and it needs no storage of its own.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.domains.habits.models import ProposalKind
from src.domains.habits.need_domains import automatable_domains, connector_category_of
from src.domains.habits.needs import Need, median_hour
from src.domains.habits.proposal_facts import (
    AutomateNeedFacts,
    CitedRoutine,
    ConnectSourceFacts,
    ExtendWindowFacts,
    FixRoutineFacts,
    ProposalFacts,
    ReviewNotificationsFacts,
    ShiftRoutineFacts,
)

#: The key of the two kinds that concern the proactive notifications as a whole.
HEARTBEAT_KEY = "heartbeat"
#: A need the person paused or blocked in the panel is never proposed.
_SILENT_NEED_STATUSES = frozenset({"paused", "blocked"})


@dataclass(frozen=True, slots=True)
class ProposalThresholds:
    """The bars every rule is held to — read once from settings."""

    window_days: int
    routine_gap_hours: float
    manual_min_runs: int
    manual_min_days: int
    failure_streak: int
    window_min_days: int
    window_min_cells: int
    window_min_share: float
    window_max_extension_hours: int
    silent_min_notifications: int
    connector_min_days: int
    mute_after_refusals: int

    @classmethod
    def from_settings(cls, settings: Any) -> ProposalThresholds:
        """Read every bar from a settings view.

        Args:
            settings: The application settings (or a test view of them).

        Returns:
            The thresholds.
        """
        return cls(
            window_days=int(settings.recurrence_window_days),
            routine_gap_hours=float(settings.habits_proposal_routine_gap_hours),
            manual_min_runs=int(settings.habits_proposal_manual_min_runs),
            manual_min_days=int(settings.habits_proposal_manual_min_days),
            failure_streak=int(settings.habits_proposal_failure_streak),
            window_min_days=int(settings.habits_proposal_window_min_days),
            window_min_cells=int(settings.habits_proposal_window_min_cells),
            window_min_share=float(settings.habits_proposal_window_min_share),
            window_max_extension_hours=int(settings.habits_proposal_window_max_extension_hours),
            silent_min_notifications=int(settings.habits_proposal_silent_min_notifications),
            connector_min_days=int(settings.habits_proposal_connector_min_days),
            mute_after_refusals=int(settings.habits_proposal_mute_after_refusals),
        )


@dataclass(frozen=True, slots=True)
class RoutineRun:
    """One run of a routine inside the window, in the person's local time."""

    day: date
    hour: float
    manual: bool
    outcome: str
    run_id: str | None


@dataclass(frozen=True, slots=True)
class RoutineView:
    """A routine as the rules read it.

    Attributes:
        id: The routine's id (string form).
        title: Its title, as the person named it.
        enabled: Whether it runs.
        status: ``active``, ``error`` (disabled by the system after failures), ...
        trigger_kind: ``time`` or ``condition``.
        times: Local hours a time routine fires at (empty for a condition one).
        fires_on: Weekdays it fires on (0=Monday..6=Sunday; empty when its
            calendar is monthly, yearly or once).
        consecutive_failures: Failures since its last success.
        runs: Its runs inside the window.
        read_domains: Domains its linked runs READ inside the window, or None
            when LIA cannot tell (a routine that could serve a need but has no
            run naming its turn yet).
        fixed_times: Whether its moments are listed one by one, so one of them
            can be moved; a step (« every 30 minutes ») has none to move.
    """

    id: str
    title: str
    enabled: bool
    status: str
    trigger_kind: str
    times: tuple[float, ...]
    fires_on: frozenset[int]
    consecutive_failures: int
    runs: tuple[RoutineRun, ...]
    read_domains: frozenset[str] | None
    fixed_times: bool


@dataclass(frozen=True, slots=True)
class ProactiveFeedback:
    """Proactive notifications sent inside the window, and how many got a reaction."""

    sent: int
    reacted: int


@dataclass(frozen=True, slots=True)
class UsageObservations:
    """Everything the rules read about one person, for one night.

    Attributes:
        today: The person's local date.
        needs: Their recurring needs (``needs.detect_need``).
        need_status: Status of each need's habit row, by domain.
        asked_days: Distinct days each domain was asked inside the window.
        routines: Their routines.
        presence: Local hours with activity, by local day, inside the window.
        heartbeat_enabled: Whether proactive notifications are on.
        heartbeat_window: Their notification hours (start, exclusive end; may wrap).
        proactive: What the notifications met, or None when LIA cannot tell.
        connector_categories: Categories with an active connector.
        refusals: Refused proposals, counted by kind.
        ledger_readable: Whether the request ledger could be read tonight.
    """

    today: date
    needs: tuple[Need, ...]
    need_status: Mapping[str, str]
    asked_days: Mapping[str, int]
    routines: tuple[RoutineView, ...]
    presence: Mapping[date, frozenset[int]]
    heartbeat_enabled: bool
    heartbeat_window: tuple[int, int]
    proactive: ProactiveFeedback | None
    connector_categories: frozenset[str]
    refusals: Mapping[str, int]
    ledger_readable: bool


@dataclass(frozen=True, slots=True)
class ProposalCandidate:
    """One proposal a rule wants open: its identity and its facts."""

    kind: ProposalKind
    key: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProposalEvaluation:
    """The night's verdict: what should be open, and what could not be judged."""

    candidates: tuple[ProposalCandidate, ...] = ()
    held: frozenset[ProposalKind] = field(default_factory=frozenset)


def _candidate(kind: ProposalKind, key: str, facts: ProposalFacts) -> ProposalCandidate:
    """A candidate whose payload is its kind's facts, JSON-safe (``proposal_facts``)."""
    return ProposalCandidate(kind, key, facts.model_dump(mode="json"))


def _hour_minute(hour: float) -> tuple[int, int]:
    total = int(round(hour * 60)) % (24 * 60)
    return total // 60, total % 60


def _floor_quarter(hour: float) -> float:
    return math.floor(hour * 4) / 4


def _hour_distance(a: float, b: float) -> float:
    """Shortest distance between two local hours on the 24-hour circle."""
    return min((a - b) % 24, (b - a) % 24)


def _covers_cadence(routine: RoutineView, need: Need) -> bool:
    """Whether a routine fires on the days a need is asked."""
    if need.cadence == "weekly":
        return need.weekday in routine.fires_on
    if need.cadence == "weekdays":
        return frozenset(range(5)) <= routine.fires_on
    return len(routine.fires_on) >= 5


def _readers_of(need: Need, routines: tuple[RoutineView, ...]) -> list[RoutineView]:
    return [
        routine
        for routine in routines
        if routine.enabled
        and routine.trigger_kind == "time"
        and routine.read_domains is not None
        and need.domain in routine.read_domains
        and _covers_cadence(routine, need)
    ]


def _automate_need(
    need: Need, routines: tuple[RoutineView, ...], gap: float
) -> ProposalCandidate | None:
    # The nearest reading time decides, the routine id breaking a tie: rows
    # arrive unordered, and a cited routine that changed from night to night
    # would refresh the proposal forever.
    nearest = min(
        ((routine, time) for routine in _readers_of(need, routines) for time in routine.times),
        key=lambda pair: (_hour_distance(pair[1], need.prefill_hour), pair[0].id),
        default=None,
    )
    if nearest is not None and _hour_distance(nearest[1], need.prefill_hour) < gap:
        return None
    hour, minute = _hour_minute(need.prefill_hour)
    cited = None
    if nearest is not None:
        routine, time = nearest
        cited_hour, cited_minute = _hour_minute(time)
        cited = CitedRoutine(
            id=routine.id, title=routine.title, hour=cited_hour, minute=cited_minute
        )
    return _candidate(
        ProposalKind.AUTOMATE_NEED,
        need.domain,
        AutomateNeedFacts(
            domain=need.domain,
            cadence=need.cadence,
            weekday=need.weekday,
            hour=hour,
            minute=minute,
            distinct_days=need.distinct_days,
            active_days=need.active_days,
            part_of_day=need.part_of_day,
            existing_routine=cited,
        ),
    )


def _served(domain: str, connected: frozenset[str]) -> bool:
    """Whether the connector a domain's asks depend on is active, or none is needed.

    A routine on a domain whose connector is not active would fail every
    morning: the need is proposed for connecting first (ADR-184, 2026-10-14).
    """
    category = connector_category_of(domain)
    return category is None or category in connected


def _automation_candidates(
    obs: UsageObservations, thresholds: ProposalThresholds
) -> list[ProposalCandidate]:
    automatable = automatable_domains()
    out = []
    for need in sorted(obs.needs, key=lambda n: n.domain):
        if (
            need.at_automation_bar
            and need.domain in automatable
            and obs.need_status.get(need.domain) not in _SILENT_NEED_STATUSES
            and _served(need.domain, obs.connector_categories)
        ):
            candidate = _automate_need(need, obs.routines, thresholds.routine_gap_hours)
            if candidate is not None:
                out.append(candidate)
    return out


def _shift_routine(
    routine: RoutineView, thresholds: ProposalThresholds
) -> ProposalCandidate | None:
    if (
        not routine.enabled
        or routine.trigger_kind != "time"
        or not routine.fixed_times
        or not routine.times
    ):
        return None
    manual = [run for run in routine.runs if run.manual]
    days = {run.day for run in manual}
    if len(manual) < thresholds.manual_min_runs or len(days) < thresholds.manual_min_days:
        return None
    usual = median_hour([run.hour for run in manual])
    nearest = min(routine.times, key=lambda time: _hour_distance(time, usual))
    if _hour_distance(nearest, usual) < thresholds.routine_gap_hours:
        return None
    from_hour, from_minute = _hour_minute(nearest)
    hour, minute = _hour_minute(_floor_quarter(usual))
    return _candidate(
        ProposalKind.SHIFT_ROUTINE,
        routine.id,
        ShiftRoutineFacts(
            routine_id=routine.id,
            routine_title=routine.title,
            from_hour=from_hour,
            from_minute=from_minute,
            hour=hour,
            minute=minute,
            manual_runs=len(manual),
            manual_days=len(days),
        ),
    )


def _fix_routine(routine: RoutineView, thresholds: ProposalThresholds) -> ProposalCandidate | None:
    disabled = routine.status == "error"
    if not disabled and not (
        routine.enabled and routine.consecutive_failures >= thresholds.failure_streak
    ):
        return None
    return _candidate(
        ProposalKind.FIX_ROUTINE,
        routine.id,
        FixRoutineFacts(
            routine_id=routine.id,
            routine_title=routine.title,
            failures=routine.consecutive_failures,
            disabled=disabled,
        ),
    )


def _in_window(hour: int, start: int, end: int) -> bool:
    """The heartbeat's own window rule (wrap-aware, start == end is empty)."""
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def _extended_window(start: int, end: int, frequent: set[int], max_steps: int) -> tuple[int, int]:
    """Grow the window by CONTIGUOUS frequent hours, never closing it on itself."""
    new_end = end
    for _ in range(max_steps):
        if new_end % 24 not in frequent or (new_end + 1) % 24 == start:
            break
        new_end = (new_end + 1) % 24
    new_start = start
    for _ in range(max_steps):
        previous = (new_start - 1) % 24
        if previous not in frequent or previous == new_end:
            break
        new_start = previous
    return new_start, new_end


@dataclass(frozen=True, slots=True)
class _OutsidePresence:
    """Where the person's presence fell against the notification window.

    Attributes:
        total: Presence hours observed (one per day and clock hour).
        outside: Those outside the window.
        days: Days with at least one hour outside.
        hour_days: Per clock hour outside, the days it was seen.
    """

    total: int
    outside: int
    days: int
    hour_days: Counter[int]


def _outside_presence(
    presence: Mapping[date, frozenset[int]], start: int, end: int
) -> _OutsidePresence:
    outside_by_day = [
        [hour for hour in hours if not _in_window(hour, start, end)] for hours in presence.values()
    ]
    return _OutsidePresence(
        total=sum(len(hours) for hours in presence.values()),
        outside=sum(len(hours) for hours in outside_by_day),
        days=sum(1 for hours in outside_by_day if hours),
        hour_days=Counter(hour for hours in outside_by_day for hour in hours),
    )


def _is_a_pattern(stats: _OutsidePresence, thresholds: ProposalThresholds) -> bool:
    """Whether the presence outside the window is a habit, not a few late nights."""
    return (
        stats.total > 0
        and stats.days >= thresholds.window_min_days
        and stats.outside >= thresholds.window_min_cells
        and stats.outside / stats.total >= thresholds.window_min_share
    )


def _extend_window(
    obs: UsageObservations, thresholds: ProposalThresholds
) -> ProposalCandidate | None:
    if not obs.heartbeat_enabled:
        return None
    start, end = obs.heartbeat_window
    stats = _outside_presence(obs.presence, start, end)
    if not _is_a_pattern(stats, thresholds):
        return None
    frequent = {
        hour for hour, days in stats.hour_days.items() if days >= thresholds.window_min_days
    }
    new_start, new_end = _extended_window(
        start, end, frequent, thresholds.window_max_extension_hours
    )
    if (new_start, new_end) == (start, end):
        return None
    return _candidate(
        ProposalKind.EXTEND_NOTIFICATION_WINDOW,
        HEARTBEAT_KEY,
        ExtendWindowFacts(
            start=start,
            end=end,
            new_start=new_start,
            new_end=new_end,
            outside_days=stats.days,
            outside_share=round(stats.outside / stats.total, 2),
        ),
    )


def _review_notifications(
    obs: UsageObservations, thresholds: ProposalThresholds
) -> ProposalCandidate | None:
    feedback = obs.proactive
    if (
        not obs.heartbeat_enabled
        or feedback is None
        or feedback.sent < thresholds.silent_min_notifications
        or feedback.reacted
    ):
        return None
    return _candidate(
        ProposalKind.REVIEW_NOTIFICATIONS,
        HEARTBEAT_KEY,
        ReviewNotificationsFacts(sent=feedback.sent, window_days=thresholds.window_days),
    )


def _connect_candidates(
    obs: UsageObservations, thresholds: ProposalThresholds
) -> list[ProposalCandidate]:
    best: dict[str, tuple[int, str]] = {}
    for domain, days in obs.asked_days.items():
        category = connector_category_of(domain)
        if (
            category is None
            or category in obs.connector_categories
            or days < thresholds.connector_min_days
            or obs.need_status.get(domain) in _SILENT_NEED_STATUSES
        ):
            continue
        if days > best.get(category, (0, ""))[0]:
            best[category] = (days, domain)
    return [
        _candidate(
            ProposalKind.CONNECT_SOURCE,
            category,
            ConnectSourceFacts(category=category, domain=domain, days=days),
        )
        for category, (days, domain) in sorted(best.items())
    ]


def _held_kinds(obs: UsageObservations) -> set[ProposalKind]:
    held: set[ProposalKind] = set()
    if not obs.ledger_readable or any(
        routine.enabled and routine.trigger_kind == "time" and routine.read_domains is None
        for routine in obs.routines
    ):
        held.add(ProposalKind.AUTOMATE_NEED)
    if not obs.ledger_readable:
        held.add(ProposalKind.CONNECT_SOURCE)
    if obs.heartbeat_enabled and obs.proactive is None:
        held.add(ProposalKind.REVIEW_NOTIFICATIONS)
    return held


def evaluate_proposals(
    obs: UsageObservations, thresholds: ProposalThresholds
) -> ProposalEvaluation:
    """Every proposal the night's observations support, and the kinds left unjudged.

    Args:
        obs: The person's observations.
        thresholds: The bars.

    Returns:
        The candidates (one per kind and key) and the held kinds.
    """
    held = _held_kinds(obs)
    muted = {
        kind for kind in ProposalKind if obs.refusals.get(kind, 0) >= thresholds.mute_after_refusals
    }
    candidates: list[ProposalCandidate] = []
    if ProposalKind.AUTOMATE_NEED not in held:
        candidates += _automation_candidates(obs, thresholds)
    for routine in sorted(obs.routines, key=lambda r: r.id):
        candidates += [
            candidate
            for candidate in (
                _shift_routine(routine, thresholds),
                _fix_routine(routine, thresholds),
            )
            if candidate is not None
        ]
    candidates += [
        candidate
        for candidate in (_extend_window(obs, thresholds), _review_notifications(obs, thresholds))
        if candidate is not None
    ]
    if ProposalKind.CONNECT_SOURCE not in held:
        candidates += _connect_candidates(obs, thresholds)
    return ProposalEvaluation(
        candidates=tuple(c for c in candidates if c.kind not in muted and c.kind not in held),
        held=frozenset(held - muted),
    )
