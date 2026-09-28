"""The session's loop: it executes what the pure core decides, and is its only writer.

One loop drives one session, inside the session's lease (the caller holds it with
``locks.redis_claim.held_claim``: a successor taking the lease cancels this loop at its
next await). The loop is the ONLY writer of the session's state; everything else
talks to it through two narrow doors:

- the INBOX — what the routes write: where the player is (its last report) and
  whether the listener asked to stop. The loop reads it at every tick;
- the RESULTS — what a production task hands back when it ends. Productions run as
  tasks of the loop (one at a time once the listener hears the antenna, two before)
  and never touch the state: the loop applies their outcome.

At every tick the loop reads the inbox, files what the listener heard since the
last report (a line once the player has passed it — never what was only produced,
ADR-324 decision 35), plans the next slot when the running order needs one,
decides, starts what must start — after asking the spending ceilings, since no
voice engine asks them by itself — and publishes what the player is told.
A news flash runs beside the running order (ADR-324 decision 32): every
``flash_poll_s`` the loop asks what LIA just wrote to the listener, and one flash
at a time is produced as a task of its own; the player cuts the programme for it
and says, in its reports, which flash it heard.
It ends on the pure core's word — the farewell aired, the listener stopped, nobody
listening, a ceiling reached, productions failing — and then cancels what is still
in flight: a segment nobody will hear is not worth finishing, and every one is
billed to the listener.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, tzinfo
from typing import Protocol

import structlog

from src.core.constants import RADIO_FLASH_POLL_SECONDS_DEFAULT
from src.domains.radio.aired import HeardLine
from src.domains.radio.flash import (
    FlashNote,
    flash_allowed,
    flash_failed,
    flash_produced,
    flash_started,
    flash_watermark,
    flashes_heard,
    is_flash_seq,
    what_it_cuts,
    what_resumes,
)
from src.domains.radio.formats import Frequency, RadioFormat
from src.domains.radio.grid import next_segment
from src.domains.radio.pacing import Playhead, StageTimings, production_s, ran_late
from src.domains.radio.production import NothingAired, ProducedSegment
from src.domains.radio.programme import Slot, hand_over_to, preceding
from src.domains.radio.session import (
    DISCARD_AT_END,
    ActionKind,
    EndReason,
    SessionRules,
    SessionState,
    budget_reached,
    decide,
    ended_for,
    grid_inputs,
    needs_planning,
    plan,
    production_failed,
    production_started,
    production_succeeded,
    reported,
    stopped,
    withdrawn,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Listening:
    """What the loop knows of the listener for the whole session.

    Attributes:
        language: The listener's language (backend-canonical code).
        timezone: Their timezone (the grid's clock marks are local).
        frequencies: Their frequency per format.
        public_mode: No personal format may air.
        voices_by_format: How many distinct voices each programme is heard with.
        seed: The grid's draws derive from it (a restarted loop replays them).
    """

    language: str
    timezone: tzinfo
    frequencies: Mapping[RadioFormat, Frequency]
    public_mode: bool
    voices_by_format: Mapping[RadioFormat, int]
    seed: int


class Inbox(Protocol):
    """What the routes wrote for the loop."""

    async def playhead(self) -> Playhead | None:
        """The player's last report."""
        ...

    async def stop_requested(self) -> bool:
        """Whether the listener asked to stop."""
        ...


class Board(Protocol):
    """Where the loop publishes what the player is told, and keeps its state."""

    async def publish(self, state: SessionState, ready: Mapping[int, ProducedSegment]) -> None:
        """Save the state and the ready segments."""
        ...


class Producer(Protocol):
    """Produces one slot's segment (desk, writer, voices, mix) — and a news flash."""

    async def produce(
        self, slot: Slot, *, previous: RadioFormat | None, following: RadioFormat | None
    ) -> ProducedSegment | NothingAired | None:
        """The segment; ``NothingAired`` when the station chose not to air; ``None``
        on a failure."""
        ...

    async def produce_flash(
        self,
        notes: Sequence[FlashNote],
        *,
        seq: int,
        cuts: RadioFormat | None,
        resumes: RadioFormat | None,
    ) -> ProducedSegment | NothingAired | None:
        """A flash for ``notes``; ``NothingAired`` or ``None`` when there is none."""
        ...


class HeardLedger(Protocol):
    """Where what the listener heard is filed, for the next sessions (the aired ledger)."""

    async def remember(self, lines: Sequence[HeardLine]) -> None:
        """File the lines the listener just heard."""
        ...


class FlashSource(Protocol):
    """What LIA wrote to the listener lately — a news flash's material."""

    async def since(self, after: datetime) -> list[FlashNote]:
        """The notifications sent after ``after``, oldest first, as many as one flash tells."""
        ...


@dataclass(frozen=True, slots=True)
class LoopPorts:
    """The loop's collaborators.

    Attributes:
        inbox: What the routes wrote.
        board: Where the state and the ready segments are published.
        producer: Produces a slot.
        available: The formats that have something to say right now.
        spend_blocked: Whether a spending ceiling refuses the next production.
        aired: Where what the listener heard is filed.
        now: The clock (timezone-aware instants).
        sleep: How the loop waits between two ticks.
        flashes: What LIA wrote to the listener; None when nothing personal may
            air or the listener silenced the notifications — no flash then.
    """

    inbox: Inbox
    board: Board
    producer: Producer
    available: Callable[[], Awaitable[frozenset[RadioFormat]]]
    spend_blocked: Callable[[], Awaitable[bool]]
    aired: HeardLedger
    now: Callable[[], datetime]
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    flashes: FlashSource | None = None


@dataclass(frozen=True, slots=True)
class LoopTuning:
    """The loop's timings (settings, read by the caller).

    Attributes:
        tick_s: Seconds between two decisions.
        first_delay_s: Expected production time of the opening.
        timings: The stage timings the lookahead estimates with.
        rules: The session's bounds.
        flash_poll_s: How often the loop asks what LIA just wrote (a flash's delay).
    """

    tick_s: float
    first_delay_s: float
    timings: StageTimings
    rules: SessionRules
    flash_poll_s: float = RADIO_FLASH_POLL_SECONDS_DEFAULT


@dataclass(slots=True)
class _Run:
    state: SessionState
    ready: dict[int, ProducedSegment] = field(default_factory=dict)
    tasks: dict[int, asyncio.Task[ProducedSegment | NothingAired | None]] = field(
        default_factory=dict
    )
    flash_task: asyncio.Task[ProducedSegment | NothingAired | None] | None = None
    flash_seq: int = 0
    next_flash_look: datetime | None = None
    #: How many of each segment's remembered lines are filed as heard, by place.
    heard: dict[int, int] = field(default_factory=dict)
    #: When each production in flight started, by place.
    started_at: dict[int, datetime] = field(default_factory=dict)
    #: The most a production of this loop ran past the instance's estimate.
    lateness_s: float = 0.0

    def timings(self, tuning: LoopTuning) -> StageTimings:
        """The stage timings every estimate of this loop uses: the instance's, and
        what its own productions showed (:func:`pacing.ran_late`)."""
        return replace(tuning.timings, lateness_s=self.lateness_s)


async def _plan(run: _Run, listening: Listening, ports: LoopPorts, tuning: LoopTuning) -> None:
    """Complete the running order one slot ahead for scheduling. A planned
    successor is not named on air until its own audio is ready."""
    while needs_planning(run.state):
        before = len(run.state.slots)
        await _plan_one(run, listening, ports, tuning)
        if len(run.state.slots) == before:
            return


async def _plan_one(run: _Run, listening: Listening, ports: LoopPorts, tuning: LoopTuning) -> None:
    inputs = grid_inputs(
        run.state,
        now=ports.now(),
        first_delay_s=tuning.first_delay_s,
        timezone=listening.timezone,
        frequencies=listening.frequencies,
        available=await ports.available(),
        public_mode=listening.public_mode,
        voices_by_format=listening.voices_by_format,
    )
    rng = random.Random(listening.seed * 1_000 + len(run.state.slots))
    decision = next_segment(inputs, rng)
    if decision is not None:
        run.state = plan(run.state, decision, inputs.air_at)


def _start(run: _Run, slot: Slot, ports: LoopPorts) -> None:
    run.state = production_started(run.state, slot.seq)
    run.started_at[slot.seq] = ports.now()
    run.tasks[slot.seq] = asyncio.create_task(
        ports.producer.produce(
            slot,
            previous=preceding(run.state.slots, slot.seq),
            following=hand_over_to(run.state.slots, slot.seq, ready=run.state.produced),
        )
    )


def _outcome(
    seq: int, task: asyncio.Task[ProducedSegment | NothingAired | None]
) -> ProducedSegment | NothingAired | None:
    if task.cancelled():
        return None
    error = task.exception()
    if error is not None:
        logger.warning("radio_production_crashed", seq=seq, error=type(error).__name__)
        return None
    return task.result()


def _learn(run: _Run, seq: int, now: datetime, tuning: LoopTuning, language: str) -> None:
    """What one finished production says of the next ones' time — whatever it
    produced: a refusal or a failure took the time it took."""
    started = run.started_at.pop(seq, None)
    slot = next((s for s in run.state.slots if s.seq == seq), None)
    if started is None or slot is None:
        return  # produced again after a restart: its start died with the loop before
    run.lateness_s = ran_late(
        run.lateness_s,
        observed_s=(now - started).total_seconds(),
        expected_s=production_s(slot.format, tuning.timings, language),
    )


def _collect(run: _Run, now: datetime, tuning: LoopTuning, language: str) -> None:
    for seq, task in list(run.tasks.items()):
        if not task.done():
            continue
        del run.tasks[seq]
        if not task.cancelled():
            _learn(run, seq, now, tuning, language)
        segment = _outcome(seq, task)
        if isinstance(segment, ProducedSegment):
            run.ready[seq] = segment
            run.state = production_succeeded(run.state, seq, segment.duration_s)
        else:
            # The station's silence rests the format, and never counts toward the stop.
            run.state = production_failed(run.state, seq, at=now, counted=segment is None)


async def _read_inbox(run: _Run, ports: LoopPorts) -> None:
    playhead = await ports.inbox.playhead()
    if playhead is not None and playhead != run.state.playhead:
        run.state = flashes_heard(reported(run.state, playhead), playhead.flash_heard)
    if await ports.inbox.stop_requested():
        run.state = stopped(run.state)


def _lines_heard(
    state: SessionState, seq: int, segment: ProducedSegment, *, played_out: bool
) -> int:
    """How many of a segment's remembered lines the listener heard, by the player's word.

    A flash is heard whole once the player says so; a programme once the player
    moved past it, and up to its position while it plays. A place the player never
    reported playing — produced ahead, skipped — was heard by nobody. At an end the
    player plays out (``played_out``), what it has left — the rest of the programme
    on air and every programme ready after it — will be heard, with no loop left
    to read its reports.
    """
    playhead = state.playhead
    if playhead is None:
        return 0
    if is_flash_seq(seq):
        return len(segment.memory) if seq <= playhead.flash_heard else 0
    if played_out and seq >= playhead.seq:
        return len(segment.memory)
    started = any(slot.seq == seq and slot.reported for slot in state.slots)
    if not started or seq > playhead.seq:
        return 0
    if seq < playhead.seq:
        return len(segment.memory)
    return sum(1 for line in segment.memory if line.offset_s <= playhead.position_s)


async def _file_heard(run: _Run, ports: LoopPorts, *, played_out: bool = False) -> None:
    """File what the listener heard since the last report — a line once, when passed.

    At an end the player plays out (``played_out``), what it has left to play too.
    A ledger that fails costs the next session a repeat, never this one.
    """
    fresh: list[HeardLine] = []
    for seq in sorted(run.ready):
        segment = run.ready[seq]
        heard = _lines_heard(run.state, seq, segment, played_out=played_out)
        filed = run.heard.get(seq, 0)
        if heard > filed:
            fresh.extend(segment.memory[filed:heard])
            run.heard[seq] = heard
    if not fresh:
        return
    try:
        await ports.aired.remember(fresh)
    except Exception as exc:  # noqa: BLE001 — the next session may repeat, never this one
        logger.warning("radio_aired_ledger_unavailable", error_type=type(exc).__name__)


def _collect_flash(run: _Run) -> None:
    """Apply a finished flash: ready and waiting to be heard, or gone."""
    task = run.flash_task
    if task is None or not task.done():
        return
    run.flash_task = None
    segment = _outcome(run.flash_seq, task)
    if not isinstance(segment, ProducedSegment):
        run.state = flash_failed(run.state, run.flash_seq)
        return
    run.ready[run.flash_seq] = segment
    run.state = flash_produced(run.state, run.flash_seq, duration_s=segment.duration_s)


async def _flash(run: _Run, ports: LoopPorts, tuning: LoopTuning, language: str) -> None:
    """Collect a finished flash, and start one when LIA just wrote to the listener.

    The notifications are read at most every ``flash_poll_s``; a flash starts only
    while the listener hears the antenna and a spending ceiling allows it. What it
    cuts is judged at the moment it will be READY, on the same estimate the loop
    schedules its productions with.
    """
    _collect_flash(run)
    if ports.flashes is None or run.flash_task is not None or not flash_allowed(run.state):
        return
    now = ports.now()
    if run.next_flash_look is not None and now < run.next_flash_look:
        return
    run.next_flash_look = now + timedelta(seconds=tuning.flash_poll_s)
    try:
        notes = await ports.flashes.since(flash_watermark(run.state))
    except Exception as exc:  # noqa: BLE001 — a blind source costs a flash, never the session
        logger.warning("radio_flash_source_unavailable", error_type=type(exc).__name__)
        return
    if not notes or await ports.spend_blocked():
        return
    ready_in_s = (
        production_s(RadioFormat.FLASH, run.timings(tuning), language)
        * tuning.rules.lookahead_safety
        + tuning.rules.lookahead_margin_s
    )
    cuts = what_it_cuts(run.state, now=ports.now(), ready_in_s=ready_in_s)
    resumes = what_resumes(run.state, cuts)
    run.state, flash = flash_started(run.state, notes)
    run.flash_seq = flash.seq
    run.flash_task = asyncio.create_task(
        ports.producer.produce_flash(notes, seq=flash.seq, cuts=cuts, resumes=resumes)
    )


async def _cancel_all(run: _Run) -> None:
    tasks = [*run.tasks.values(), *([run.flash_task] if run.flash_task else [])]
    for task in tasks:
        task.cancel()
    for task in tasks:
        # Its outcome no longer matters: the session is over.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
    run.tasks.clear()
    run.flash_task = None


async def _end(run: _Run, ports: LoopPorts, reason: EndReason) -> EndReason:
    """Write the end into the state, publish it, and say why — whoever decided it.

    An end the pure core decided alone (nobody listening, productions failing)
    used to be returned and never written: the player waited on the station's
    music for minutes, and every report restarted a loop that ended again at
    once (measured on dev, 2026-09-26).
    """
    run.state = ended_for(run.state, reason)
    await ports.board.publish(run.state, run.ready)
    logger.info("radio_session_ended", reason=reason.value)
    return reason


async def run_session(
    state: SessionState,
    *,
    listening: Listening,
    ports: LoopPorts,
    tuning: LoopTuning,
    ready: Mapping[int, ProducedSegment] | None = None,
) -> EndReason:
    """Drive one session until the pure core says it ends.

    Args:
        state: Where the session stands (new, or reloaded after a restart).
        listening: What the loop knows of the listener.
        ports: The loop's collaborators.
        tuning: Its timings.
        ready: The segments a restarted loop finds published: heard after the
            restart, they are filed all the same.

    Returns:
        Why it ended.
    """
    run = _Run(state=state, ready=dict(ready or {}))
    try:
        while True:
            _collect(run, ports.now(), tuning, listening.language)
            await _read_inbox(run, ports)
            await _file_heard(run, ports)
            await _flash(run, ports, tuning, listening.language)
            await _plan(run, listening, ports, tuning)
            action = decide(
                run.state,
                now=ports.now(),
                timings=run.timings(tuning),
                language=listening.language,
                rules=tuning.rules,
            )
            if action.kind is ActionKind.PRODUCE and action.slot is not None:
                if await ports.spend_blocked():
                    run.state = budget_reached(run.state)
                else:
                    _start(run, action.slot, ports)
                continue
            if action.kind is ActionKind.END:
                reason = action.reason or EndReason.IDLE
                if reason not in DISCARD_AT_END:
                    # The player plays its queue out once this loop is gone: filed now.
                    await _file_heard(run, ports, played_out=True)
                return await _end(run, ports, reason)
            if action.kind is ActionKind.WITHDRAW and action.slot is not None:
                # A farewell the real running order finds early: the grid decides
                # again at the NEXT tick — never at once, so a case on the window's
                # edge cannot turn the loop into a spin.
                run.state = withdrawn(run.state, action.slot.seq)
            await ports.board.publish(run.state, run.ready)
            await ports.sleep(tuning.tick_s)
    finally:
        await _cancel_all(run)


def reloaded(state: SessionState) -> SessionState:
    """A state read back after a restart: what was in production died with its task,
    and is produced again — its slot, and the hand-over that announced it, stay.

    A news flash in production died too and goes, as one that could not be
    produced: one flash at a time, it would hold every later one for the rest of
    the session. A flash already produced is still to be heard.
    """
    return replace(
        state,
        in_production=frozenset(),
        flashes=tuple(flash for flash in state.flashes if flash.produced),
    )


__all__ = [
    "Board",
    "HeardLedger",
    "Inbox",
    "Listening",
    "LoopPorts",
    "LoopTuning",
    "Producer",
    "reloaded",
    "run_session",
]
