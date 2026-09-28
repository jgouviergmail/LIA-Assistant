"""One session's decisions: what to produce next, and when the antenna stops.

A session is a running order (:mod:`~src.domains.radio.programme`) produced
ahead of a listener. What happens next is decided here from a small,
serialisable state — the orchestrator keeps it (it must survive a worker's
restart), executes the decision (plans a slot, produces a segment, ends) and
feeds the outcome back through the transitions below:

- **plan** — two slots wait unproduced at all times: the next to produce, and
  the one after it, so its writer can hand over to it by name;
- **produce** — one segment at a time once the listener hears the antenna;
  before the first sound, two at once (the opening is short and what follows
  it must be ready when it ends, or the start is heard as a gap — the player
  reports from the click, so « before the first report » would never apply);
- **wait** — the audio ahead covers the next production;
- **withdraw** — the farewell is the next to produce but the REAL running order
  leaves more than its window before the stop: it was planned on durations
  projected at the formats' targets, and a segment that came out shorter, or
  one that failed, moved it early (measured 2026-09-26: nine minutes before a
  thirty-minute stop). It leaves the order, and the grid decides again;
- **end** — the sign-off is produced and nothing is left in production (the
  timer's end: nothing follows a sign-off), the listener stopped, nobody has
  reported for too long or the player has sat paused too long (the antenna
  only runs while someone listens — and every segment is billed to them),
  productions keep failing, or a spending ceiling refuses the next one (the
  orchestrator asks before every production: no voice engine asks the ceilings
  by itself).

The timer counts LISTENING time: while the listener has paused, the stop moves
with the clock (:func:`effective_stop_at`), and resuming moves it by the whole
pause (owner decision 2026-09-26).

A failed production drops its slot from the running order: the next one moves
up, failures are counted until a production succeeds, and the format is
remembered with the instant it failed at — the grid rests it.

Pure: no clock, no store, no provider — instants are inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, tzinfo
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from src.domains.radio.constants import SIGN_OFF_WINDOW_SECONDS
from src.domains.radio.formats import Frequency, RadioFormat
from src.domains.radio.grid import AiredSegment, GridDecision, GridInputs
from src.domains.radio.pacing import (
    Playhead,
    QueuedSegment,
    StageTimings,
    audio_ahead_s,
    must_produce_next,
    production_s,
)
from src.domains.radio.programme import (
    Slot,
    aired_segments,
    append,
    mark_aired,
    mark_produced,
    next_air_at,
    remove,
)

if TYPE_CHECKING:
    # The flash module reads this one at run time; this one only names its record.
    from src.domains.radio.flash import Flash


class EndReason(StrEnum):
    """Why a session ended — a bounded vocabulary (a metric label, the player's word)."""

    TIMER = "timer"
    LISTENER = "listener"
    IDLE = "idle"
    FAILURES = "failures"
    BUDGET = "budget"


#: The ends after which nobody plays what is left — the listener stopped, or nobody
#: listens: its audio goes at once, and nothing more is heard. After any other end the
#: session keeps its audio and the player plays its queue out, the loop gone
#: (ADR-324 decision 35: what it has left to play is filed as heard at the end).
DISCARD_AT_END: Final[frozenset[EndReason]] = frozenset({EndReason.LISTENER, EndReason.IDLE})


class ActionKind(StrEnum):
    """What the orchestrator does next."""

    PRODUCE = "produce"
    WAIT = "wait"
    WITHDRAW = "withdraw"
    END = "end"


@dataclass(frozen=True, slots=True)
class Action:
    """One decision.

    Attributes:
        kind: What to do.
        slot: The slot to produce (``PRODUCE``) or to take out (``WITHDRAW``).
        reason: Why it ends (``END`` only).
    """

    kind: ActionKind
    slot: Slot | None = None
    reason: EndReason | None = None


@dataclass(frozen=True, slots=True)
class SessionRules:
    """The bounds a session runs under (settings, read by the caller).

    Attributes:
        idle_timeout_s: Seconds without a report before the antenna stops.
        pause_timeout_s: Seconds paused before it stops.
        failures_max: Failed productions in a row before it stops.
        lookahead_safety: Factor on a production's expected time.
        lookahead_margin_s: Seconds added on top.
        startup_parallel: Productions at once before the first sound.
    """

    idle_timeout_s: float
    pause_timeout_s: float
    failures_max: int
    lookahead_safety: float
    lookahead_margin_s: float
    startup_parallel: int = 2


@dataclass(frozen=True, slots=True)
class SessionState:
    """What a session remembers between two decisions.

    Attributes:
        started_at: When it started (UTC).
        stop_at: The automatic stop, if any (UTC) — moved forward by every
            finished pause (see :func:`effective_stop_at` for one in progress).
        slots: The running order (failed slots removed).
        produced: The places whose audio is ready.
        in_production: The places being produced.
        playhead: The player's last report.
        paused_since: When the listener paused, while they stay paused.
        failures: Failed productions since the last success.
        ended: Why it ended, once it has.
        failed: The latest failed production of each format that failed, with
            the instant it failed at (the grid rests the format).
        planned_s: The listening the timer planned, in seconds (a pause moves
            the stop, never this); None without a timer.
        flashes: The news flashes in production or waiting to be heard — outside
            the running order (:mod:`~src.domains.radio.flash`).
        flash_since: The newest notification a flash took; the session's start
            before the first.
        flashes_made: How many flashes the session started (their numbers follow).
        flash_audio_s: The seconds of radio the flashes produced (the cost
            estimate's rate counts them).
        gap_s: The station's music between two programmes, fixed at the start
            (ADR-324 decision 36): every projection leaves it, and the player
            waits as long before the next programme.
    """

    started_at: datetime
    stop_at: datetime | None
    slots: tuple[Slot, ...] = ()
    produced: frozenset[int] = frozenset()
    in_production: frozenset[int] = frozenset()
    playhead: Playhead | None = None
    paused_since: datetime | None = None
    failures: int = 0
    ended: EndReason | None = None
    failed: tuple[AiredSegment, ...] = ()
    planned_s: float | None = None
    flashes: tuple[Flash, ...] = ()
    flash_since: datetime | None = None
    flashes_made: int = 0
    flash_audio_s: float = 0.0
    gap_s: float = 0.0

    def __post_init__(self) -> None:
        for name in ("started_at", "stop_at", "paused_since", "flash_since"):
            value = getattr(self, name)
            if value is not None:
                if value.tzinfo is None:
                    raise ValueError(f"{name} must be timezone-aware")
                object.__setattr__(self, name, value.astimezone(UTC))


def start(started_at: datetime, stop_at: datetime | None, *, gap_s: float = 0.0) -> SessionState:
    """A new session, nothing planned yet but how long it is meant to be heard.

    Args:
        started_at: When it starts (timezone-aware).
        stop_at: The automatic stop, if any.
        gap_s: The station's music between two programmes.

    Returns:
        The session's first state.
    """
    planned_s = (stop_at - started_at).total_seconds() if stop_at is not None else None
    return SessionState(started_at=started_at, stop_at=stop_at, planned_s=planned_s, gap_s=gap_s)


def grid_inputs(
    state: SessionState,
    *,
    now: datetime,
    first_delay_s: float,
    timezone: tzinfo,
    frequencies: Mapping[RadioFormat, Frequency],
    available: frozenset[RadioFormat],
    public_mode: bool,
    voices_by_format: Mapping[RadioFormat, int],
) -> GridInputs:
    """What the grid reads to plan the slot after the running order's last."""
    return GridInputs(
        session_started_at=state.started_at,
        aired=aired_segments(state.slots),
        air_at=next_air_at(state.slots, now=now, first_delay_s=first_delay_s, gap_s=state.gap_s),
        timezone=timezone,
        frequencies=frequencies,
        available=available,
        public_mode=public_mode,
        voices_by_format=voices_by_format,
        stop_at=effective_stop_at(state, now),
        failed=state.failed,
    )


def effective_stop_at(state: SessionState, now: datetime) -> datetime | None:
    """The automatic stop as it stands at ``now``: a pause in progress does not count.

    Args:
        state: The session.
        now: The current instant (timezone-aware).

    Returns:
        The stop, moved by the pause in progress if any; ``None`` for no timer.
    """
    if state.stop_at is None or state.paused_since is None:
        return state.stop_at
    return state.stop_at + max(timedelta(0), now.astimezone(UTC) - state.paused_since)


def _waiting(state: SessionState) -> list[Slot]:
    return [
        slot
        for slot in state.slots
        if slot.seq not in state.produced and slot.seq not in state.in_production
    ]


def needs_planning(state: SessionState) -> bool:
    """Whether the grid must plan another slot before anything is produced.

    True while fewer than two slots wait unproduced (the next to produce and
    the one its writer hands over to); never once a sign-off is planned.
    """
    if state.ended is not None or any(s.format is RadioFormat.SIGN_OFF for s in state.slots):
        return False
    return len(_waiting(state)) < 2


def plan(state: SessionState, decision: GridDecision, air_at: datetime) -> SessionState:
    """The running order with the grid's next slot at its end."""
    return replace(state, slots=append(state.slots, decision, air_at))


def _queue(state: SessionState) -> list[QueuedSegment]:
    return [
        QueuedSegment(seq=slot.seq, duration_s=slot.duration_s, ready=slot.seq in state.produced)
        for slot in state.slots
    ]


def _seconds_since(moment: datetime, now: datetime) -> float:
    return (now.astimezone(UTC) - moment.astimezone(UTC)).total_seconds()


def _abandoned(state: SessionState, now: datetime, rules: SessionRules) -> bool:
    last = state.playhead.reported_at if state.playhead is not None else state.started_at
    if _seconds_since(last, now) > rules.idle_timeout_s:
        return True
    return state.paused_since is not None and (
        _seconds_since(state.paused_since, now) > rules.pause_timeout_s
    )


def hearing(state: SessionState) -> bool:
    """Whether the player has reported a segment playing (its air time is anchored)."""
    return state.playhead is not None and any(slot.reported for slot in state.slots)


def _startup_slot(state: SessionState, slot: Slot, rules: SessionRules) -> bool:
    """Whether ``slot`` is produced at once, beside another: one of the first
    slots, before the listener hears anything — never a third one, whose cost
    a listener who stops at once would pay for nothing."""
    if hearing(state) or len(state.in_production) >= rules.startup_parallel:
        return False
    return state.slots.index(slot) < rules.startup_parallel


def decide(
    state: SessionState,
    *,
    now: datetime,
    timings: StageTimings,
    language: str,
    rules: SessionRules,
) -> Action:
    """What the orchestrator does now.

    Args:
        state: The session.
        now: The current instant (timezone-aware).
        timings: The instance's stage timings.
        language: The listener's language (sizes productions).
        rules: The session's bounds.

    Returns:
        The decision — ``WAIT`` also when nothing is left to produce (plan
        first: see :func:`needs_planning`).
    """
    if state.ended is not None:
        return Action(ActionKind.END, reason=state.ended)
    if _abandoned(state, now, rules):
        return Action(ActionKind.END, reason=EndReason.IDLE)
    if state.failures >= rules.failures_max:
        return Action(ActionKind.END, reason=EndReason.FAILURES)
    waiting = _waiting(state)
    if not waiting:
        return Action(ActionKind.WAIT)
    slot = waiting[0]
    if _startup_slot(state, slot, rules):
        return Action(ActionKind.PRODUCE, slot=slot)
    if state.in_production or state.playhead is None:
        return Action(ActionKind.WAIT)
    if slot.format is RadioFormat.SIGN_OFF and _farewell_early(state, slot, now):
        return Action(ActionKind.WITHDRAW, slot=slot)
    ahead = audio_ahead_s(_queue(state), state.playhead, now)
    lead = _lead_s(waiting, timings, language)
    if must_produce_next(
        ahead, lead, safety=rules.lookahead_safety, margin_s=rules.lookahead_margin_s
    ):
        return Action(ActionKind.PRODUCE, slot=slot)
    return Action(ActionKind.WAIT)


def _farewell_early(state: SessionState, slot: Slot, now: datetime) -> bool:
    """Whether the farewell, confirmed on the real running order, would air early.

    Read only once nothing before it is in production: every slot ahead of it
    then carries its real duration, and a reported one its real start.
    """
    stop = effective_stop_at(state, now)
    if stop is None:
        return False
    airs_at = max(slot.air_at, now.astimezone(UTC))
    return (stop - airs_at).total_seconds() > SIGN_OFF_WINDOW_SECONDS


def _lead_s(waiting: list[Slot], timings: StageTimings, language: str) -> float:
    """The production time the audio ahead must cover before the next one starts.

    Productions run one at a time once the listener hears the antenna, so the
    next segment must also leave room for the one after it: a short segment
    followed by a long production (a brief, then an analysis) needs the
    difference now, or the listener waits (measured by the half-hour
    simulation once the targets matched what the formats really last).
    """
    first = production_s(waiting[0].format, timings, language)
    if len(waiting) < 2:
        return first
    second = production_s(waiting[1].format, timings, language)
    return max(first, first + second - waiting[0].duration_s)


def production_started(state: SessionState, seq: int) -> SessionState:
    """A slot's production has begun."""
    return replace(state, in_production=state.in_production | {seq})


def _signed_off(state: SessionState) -> bool:
    """The sign-off is ready and nothing before it is still being produced."""
    return not state.in_production and any(
        slot.format is RadioFormat.SIGN_OFF and slot.seq in state.produced for slot in state.slots
    )


def production_succeeded(state: SessionState, seq: int, duration_s: float) -> SessionState:
    """A slot is ready; once the sign-off is, and nothing else is in flight, it ends."""
    produced = replace(
        state,
        slots=mark_produced(state.slots, seq, duration_s, gap_s=state.gap_s),
        produced=state.produced | {seq},
        in_production=state.in_production - {seq},
        failures=0,
    )
    if produced.ended is None and _signed_off(produced):
        return replace(produced, ended=EndReason.TIMER)
    return produced


def production_failed(
    state: SessionState, seq: int, *, at: datetime, counted: bool = True
) -> SessionState:
    """A slot could not be produced: it leaves the running order, the next moves up.

    Its format rests from then, and the slots planned for it BEFORE the failure
    and not started leave with it: the same attempt at once mostly fails the
    same way, and each would count again — measured, a second column planned
    while the first was in production made the third failure in a row. A slot
    of that format already in production is paid for, and finishes.

    Only a FAILURE counts toward the stop. Nothing to say, or a script its
    editor refused, is the station choosing not to air: it rests the format
    the same way and says nothing of the station's health — counted, three
    of them ended a default account's session 30 s in (measured 2026-09-27).

    Args:
        state: The session.
        seq: The slot whose production failed.
        at: When it failed (timezone-aware) — its format rests from then.
        counted: Whether it was a failure (False: nothing aired, by choice).

    Returns:
        The new state.
    """
    format_failed = next((slot.format for slot in state.slots if slot.seq == seq), None)
    failed_formats = state.failed
    slots = remove(state.slots, seq, gap_s=state.gap_s)
    if format_failed is not None:
        failed_formats = (
            *(seg for seg in state.failed if seg.format is not format_failed),
            AiredSegment(format_failed, at),
        )
        for twin in _waiting(state):
            if twin.format is format_failed:
                slots = remove(slots, twin.seq, gap_s=state.gap_s)
    failed = replace(
        state,
        slots=slots,
        in_production=state.in_production - {seq},
        failures=state.failures + 1 if counted else state.failures,
        failed=failed_formats,
    )
    if failed.ended is None and _signed_off(failed):
        return replace(failed, ended=EndReason.TIMER)
    return failed


def withdrawn(state: SessionState, seq: int) -> SessionState:
    """A planned slot taken out of the running order before its production.

    Nothing failed: no failure is counted and its format does not rest — the
    grid simply decides again for that place.
    """
    return replace(state, slots=remove(state.slots, seq, gap_s=state.gap_s))


def reported(state: SessionState, playhead: Playhead) -> SessionState:
    """The player said where it is.

    A PLAYING report anchors its slot's air time (reported instant minus
    position). A PAUSED report — the listener paused, over a segment or over
    the station's music — is timed from its first such report; the first report
    that is not paused any more moves the stop by the whole pause, so the timer
    counts listening time. Anything else is the station's music filling a wait,
    never a pause.
    """
    slots = state.slots
    stop_at = state.stop_at
    paused_since: datetime | None = None
    if playhead.paused:
        paused_since = state.paused_since or playhead.reported_at.astimezone(UTC)
    else:
        if state.paused_since is not None and stop_at is not None:
            stop_at = stop_at + max(
                timedelta(0), playhead.reported_at.astimezone(UTC) - state.paused_since
            )
        if playhead.playing and playhead.seq in state.produced:
            started = playhead.reported_at - timedelta(seconds=playhead.position_s)
            slots = mark_aired(state.slots, playhead.seq, started, gap_s=state.gap_s)
    return replace(
        state, slots=slots, playhead=playhead, paused_since=paused_since, stop_at=stop_at
    )


def ended_for(state: SessionState, reason: EndReason) -> SessionState:
    """The session ended for ``reason`` — the first reason to end it stands."""
    return state if state.ended is not None else replace(state, ended=reason)


def stopped(state: SessionState) -> SessionState:
    """The listener stopped the session."""
    return ended_for(state, EndReason.LISTENER)


def budget_reached(state: SessionState) -> SessionState:
    """A spending ceiling refuses the next production: the antenna stops."""
    return ended_for(state, EndReason.BUDGET)


__all__ = [
    "DISCARD_AT_END",
    "Action",
    "ActionKind",
    "EndReason",
    "SessionRules",
    "SessionState",
    "decide",
    "effective_stop_at",
    "ended_for",
    "grid_inputs",
    "hearing",
    "needs_planning",
    "plan",
    "production_failed",
    "production_started",
    "production_succeeded",
    "reported",
    "budget_reached",
    "start",
    "stopped",
    "withdrawn",
]
