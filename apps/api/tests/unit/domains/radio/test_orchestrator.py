"""The session loop: the pure core's decisions executed, one writer, nothing left in flight."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.domains.radio import orchestrator as orchestrator_module
from src.domains.radio.aired import HeardLine
from src.domains.radio.constants import SIGN_OFF_WINDOW_SECONDS
from src.domains.radio.flash import FLASH_NOTES_MAX, FLASH_SEQ_BASE, Flash, FlashNote
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat
from src.domains.radio.orchestrator import (
    Listening,
    LoopPorts,
    LoopTuning,
    reloaded,
    run_session,
)
from src.domains.radio.pacing import Playhead, StageTimings, production_s
from src.domains.radio.production import NothingAired, ProducedSegment
from src.domains.radio.programme import Slot
from src.domains.radio.session import (
    Action,
    ActionKind,
    EndReason,
    SessionRules,
    SessionState,
    production_started,
    start,
)
from tests.unit.domains.radio.fakes import voices_by_format

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 26, 8, 50, tzinfo=UTC)
TUNING = LoopTuning(
    tick_s=1.0,
    first_delay_s=15.0,
    timings=StageTimings(
        writer_s=6.0, analysis_s=15.0, tts_realtime_factor=0.4, tts_concurrency=3, mix_s=0.5
    ),
    rules=SessionRules(
        idle_timeout_s=60,
        pause_timeout_s=900,
        failures_max=3,
        lookahead_safety=1.5,
        lookahead_margin_s=15,
    ),
)
LISTENING = Listening(
    language="en",
    timezone=UTC,
    frequencies={},
    public_mode=False,
    voices_by_format=voices_by_format(2),
    seed=7,
)


def segment(slot: Slot) -> ProducedSegment:
    duration_s = float(FORMAT_SPECS[slot.format].target_seconds)
    return ProducedSegment(
        title=slot.format.value,
        audio_path=Path(f"{slot.seq:04d}.mp3"),
        duration_s=duration_s,
        transcript=(),
        dropped_lines=0,
        unrendered=(),
        # Two lines: one at its start, one halfway through.
        memory=(
            HeardLine(offset_s=0.5, news=frozenset({f"{slot.seq}:first"})),
            HeardLine(offset_s=duration_s / 2, news=frozenset({f"{slot.seq}:second"})),
        ),
    )


#: The lines every test segment remembers (see ``segment``).
LINES = ("first", "second")


def remembered(world: World) -> list[str]:
    """The keys filed as heard, in the order they were filed."""
    return [key for line in world.remembered for key in sorted(line.news | line.personal)]


@dataclass
class World:
    """A clock, a player that hears what is ready, and the loop's doors."""

    now: datetime = T0
    playing: int | None = None
    position: float = 0.0
    last_played: int = 0
    stop: bool = False
    blocked: bool = False
    #: A spending ceiling reached during the session, from this instant.
    blocked_from: datetime | None = None
    hold: set[RadioFormat] = field(default_factory=set)
    crash: bool = False
    silent: bool = False
    #: Formats whose production answers nothing (a failure, not a crash).
    fail: set[RadioFormat] = field(default_factory=set)
    #: Formats the station chooses not to air (a script its editor refused).
    refuse: set[RadioFormat] = field(default_factory=set)
    #: Segments come out at this share of their format's target duration.
    shorten: float = 1.0
    produced: list[tuple[RadioFormat, RadioFormat | None, RadioFormat | None]] = field(
        default_factory=list
    )
    cancelled: list[int] = field(default_factory=list)
    ready: dict[int, ProducedSegment] = field(default_factory=dict)
    aired_at: dict[int, datetime] = field(default_factory=dict)
    sleeps: int = 0
    state: SessionState | None = None
    #: What LIA writes to the listener, and when (the flash source's rows).
    notes: list[FlashNote] = field(default_factory=list)
    #: The flash source answers (None: public mode, notifications silenced).
    flashing: bool = False
    #: What the flash's production answers instead of a segment, if anything.
    flash_instead: NothingAired | None = None
    fail_flash: bool = False
    asked: list[datetime] = field(default_factory=list)
    flashes_made: list[tuple[tuple[str, ...], RadioFormat | None, RadioFormat | None]] = field(
        default_factory=list
    )
    flash_heard: int = 0
    #: What the loop filed as heard, line by line (the aired ledger's writes).
    remembered: list[HeardLine] = field(default_factory=list)
    #: The aired ledger answers every write with an error.
    ledger_fails: bool = False
    #: Places the player skips (their audio would not come), never reporting them playing.
    skip: set[int] = field(default_factory=set)
    #: Every production takes the instance's estimate plus this many seconds.
    late_s: float = 0.0
    #: The instants the listener heard the music alone while a programme was due.
    waits: list[datetime] = field(default_factory=list)

    async def remember(self, lines: Sequence[HeardLine]) -> None:
        if self.ledger_fails:
            raise ConnectionError("redis down")
        self.remembered.extend(lines)

    async def playhead(self) -> Playhead | None:
        if self.silent:
            return None  # the player never reports
        seq = self.playing if self.playing is not None else self.last_played + 1
        return Playhead(
            seq=seq,
            position_s=self.position,
            reported_at=self.now,
            playing=bool(self.playing),
            flash_heard=self.flash_heard,
        )

    async def since(self, after: datetime) -> list[FlashNote]:
        self.asked.append(after)
        return [note for note in self.notes if after < note.sent_at <= self.now][:FLASH_NOTES_MAX]

    async def produce_flash(
        self,
        notes: Sequence[FlashNote],
        *,
        seq: int,
        cuts: RadioFormat | None,
        resumes: RadioFormat | None,
    ) -> ProducedSegment | NothingAired | None:
        self.flashes_made.append((tuple(note.id for note in notes), cuts, resumes))
        await asyncio.sleep(0)
        if self.fail_flash:
            return None
        if self.flash_instead is not None:
            return self.flash_instead
        return ProducedSegment(
            title="flash",
            audio_path=Path(f"{seq}.mp3"),
            duration_s=20.0,
            transcript=(),
            dropped_lines=0,
            unrendered=(),
            memory=(HeardLine(offset_s=0.5, personal=frozenset({f"flash:{seq}"})),),
        )

    async def stop_requested(self) -> bool:
        return self.stop

    async def publish(self, state: SessionState, ready: Mapping[int, ProducedSegment]) -> None:
        self.state = state
        self.ready = dict(ready)

    async def produce(
        self, slot: Slot, *, previous: RadioFormat | None, following: RadioFormat | None
    ) -> ProducedSegment | NothingAired | None:
        self.produced.append((slot.format, previous, following))
        try:
            if slot.format in self.hold:
                await asyncio.Event().wait()  # a production still in flight
            if self.late_s:
                expected = production_s(slot.format, TUNING.timings, LISTENING.language)
                done_at = self.now + timedelta(seconds=expected + self.late_s)
                while self.now < done_at:
                    await asyncio.sleep(0)
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            self.cancelled.append(slot.seq)
            raise
        if self.crash:
            raise RuntimeError("provider down")
        if slot.format in self.fail:
            return None
        if slot.format in self.refuse:
            return NothingAired("script_refused")
        made = segment(slot)
        return replace(made, duration_s=made.duration_s * self.shorten)

    async def available(self) -> frozenset[RadioFormat]:
        return frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW}

    async def spend_blocked(self) -> bool:
        return self.blocked or (self.blocked_from is not None and self.now >= self.blocked_from)

    async def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.now += timedelta(seconds=seconds)
        # A flash the loop published airs at once and is reported heard, the way
        # the player cuts the programme for it and then resumes it.
        heard = [f.seq for f in (self.state.flashes if self.state else ()) if f.produced]
        if heard:
            self.flash_heard = max(self.flash_heard, *heard)
        if self.playing is not None:
            self.position += seconds
            if self.position >= self.ready[self.playing].duration_s:
                self.last_played, self.playing = self.playing, None
        if self.playing is None:
            upcoming = sorted(seq for seq in self.ready if self.last_played < seq < FLASH_SEQ_BASE)
            while upcoming and upcoming[0] in self.skip:
                # Its audio would not come: the player moves past it, as the real one does.
                self.last_played = upcoming.pop(0)
            if upcoming:
                self.playing, self.position = upcoming[0], 0.0
                self.aired_at[upcoming[0]] = self.now
            elif self.aired_at and self._programme_due():
                self.waits.append(self.now)
        await asyncio.sleep(0)

    def _programme_due(self) -> bool:
        """Whether a programme is still to come — the music before the farewell's
        window is the station keeping the timer's promise, not a wait."""
        due = [
            slot.format
            for slot in (self.state.slots if self.state else ())
            if self.last_played < slot.seq < FLASH_SEQ_BASE
        ]
        return bool(due) and due[0] is not RadioFormat.SIGN_OFF

    def ports(self) -> LoopPorts:
        return LoopPorts(
            inbox=self,
            board=self,
            producer=self,
            available=self.available,
            spend_blocked=self.spend_blocked,
            aired=self,
            now=lambda: self.now,
            sleep=self.sleep,
            flashes=self if self.flashing else None,
        )


async def run(world: World, minutes: int = 3) -> EndReason:
    return await run_session(
        start(T0, T0 + timedelta(minutes=minutes)),
        listening=LISTENING,
        ports=world.ports(),
        tuning=TUNING,
    )


async def test_a_session_airs_from_its_opening_to_its_farewell() -> None:
    world = World()
    assert await run(world) is EndReason.TIMER
    formats = [produced for produced, _, _ in world.produced]
    assert formats[0] is RadioFormat.OPENING and formats[-1] is RadioFormat.SIGN_OFF
    assert world.produced[0][2] is None  # a planned successor may fail before it airs
    assert world.state is not None
    assert set(world.ready) == {slot.seq for slot in world.state.slots}


async def test_the_listener_stops_it_and_what_is_in_flight_is_cancelled() -> None:
    world = World(hold={RadioFormat.JOURNAL})

    async def stop_after_the_opening() -> None:
        while not world.ready:
            await asyncio.sleep(0)
        world.stop = True

    stopper = asyncio.create_task(stop_after_the_opening())
    assert await run(world, minutes=30) is EndReason.LISTENER
    await stopper
    assert world.cancelled == [2]  # the day, still being produced, never airs


async def test_a_spending_ceiling_ends_it_before_anything_is_produced() -> None:
    world = World(blocked=True)
    assert await run(world) is EndReason.BUDGET
    assert world.produced == []


async def test_productions_that_keep_failing_end_it_and_the_player_is_told() -> None:
    world = World(crash=True)
    assert await run(world, minutes=30) is EndReason.FAILURES
    # What every report reads: unpublished, the player waited for ever and each
    # report restarted a loop that ended again (measured on dev, 2026-09-26).
    assert world.state is not None and world.state.ended is EndReason.FAILURES


async def test_programmes_the_station_will_not_air_never_end_it_before_its_farewell() -> None:
    # Measured 2026-09-27: three refusals in a row ended a session 30 s in.
    refused = set(RadioFormat) - {RadioFormat.OPENING, RadioFormat.SIGN_OFF}
    world = World(refuse=refused)
    assert await run(world, minutes=12) is EndReason.TIMER
    formats = [produced for produced, _, _ in world.produced]
    assert len([fmt for fmt in formats if fmt in refused]) >= 3
    assert formats[-1] is RadioFormat.SIGN_OFF


async def test_a_session_nobody_listens_to_ends_and_says_so() -> None:
    world = World(silent=True)
    assert await run(world, minutes=30) is EndReason.IDLE
    assert world.state is not None and world.state.ended is EndReason.IDLE


async def test_segments_shorter_than_planned_never_bring_the_farewell_early() -> None:
    # Measured 2026-09-26: columns of a minute where three were projected — the
    # farewell, planned on the projection, aired nine minutes before the stop.
    world = World(shorten=0.3)
    minutes = 12
    assert await run(world, minutes=minutes) is EndReason.TIMER
    assert world.state is not None
    farewell = world.state.slots[-1]
    assert farewell.format is RadioFormat.SIGN_OFF
    # The loop ends once the farewell is ready; the player plays its queue out.
    for _ in range(600):
        if farewell.seq in world.aired_at:
            break
        await world.sleep(1.0)
    stop = T0 + timedelta(minutes=minutes)
    assert world.aired_at[farewell.seq] >= stop - timedelta(seconds=SIGN_OFF_WINDOW_SECONDS)
    assert all(following is not RadioFormat.SIGN_OFF for _, _, following in world.produced)


async def test_a_withdrawal_waits_for_the_next_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """A farewell withdrawn and planned again at the same instant must not spin the loop."""
    farewell = Slot(seq=1, format=RadioFormat.SIGN_OFF, station_id=False, air_at=T0, duration_s=12)
    answers = iter(
        [Action(ActionKind.WITHDRAW, slot=farewell)] * 3
        + [Action(ActionKind.END, reason=EndReason.TIMER)]
    )
    monkeypatch.setattr(orchestrator_module, "decide", lambda *args, **kwargs: next(answers))
    world = World()
    state = SessionState(started_at=T0, stop_at=T0 + timedelta(minutes=3), slots=(farewell,))
    ended = await run_session(state, listening=LISTENING, ports=world.ports(), tuning=TUNING)
    assert ended is EndReason.TIMER
    assert world.sleeps >= 3
    # The farewell left the running order: the grid decided again for its place.
    assert world.state is not None
    assert RadioFormat.SIGN_OFF not in [slot.format for slot in world.state.slots]


async def test_a_failed_production_rests_its_format_from_the_instant_it_failed() -> None:
    world = World(fail={RadioFormat.JOURNAL})
    await run(world, minutes=5)
    assert world.produced[0][2] is None  # never promise the journal that will be removed
    assert world.state is not None
    rested = [(seg.format, seg.air_at) for seg in world.state.failed]
    assert [fmt for fmt, _ in rested] == [RadioFormat.JOURNAL]
    assert T0 <= rested[0][1] <= world.now


async def test_a_restarted_loop_produces_again_what_died_with_its_task() -> None:
    slot = Slot(seq=1, format=RadioFormat.OPENING, station_id=True, air_at=T0, duration_s=25.0)
    state = SessionState(started_at=T0, stop_at=None, slots=(slot,))
    lost = production_started(state, 1)
    assert reloaded(lost).in_production == frozenset()
    assert reloaded(lost).slots == lost.slots


class TestLateness:
    """The stage timings are the instance's guess; the loop learns what its own
    productions take (measured 2026-09-27 on dev: a writer slot that thinks writes a
    programme in 15 to 65 s where the settings expect 12, and a simulated half-hour
    heard a minute of music alone waiting for the next programme)."""

    async def test_once_a_production_ran_late_the_listener_never_waits_for_the_next(
        self,
    ) -> None:
        world = World(late_s=40.0)
        assert await run(world, minutes=15) is EndReason.TIMER
        # The opening and the first programme are produced at once, before any
        # production could teach the loop anything; every later one is started
        # early enough.
        second = sorted(world.aired_at)[1]
        assert [at for at in world.waits if at > world.aired_at[second]] == []

    async def test_every_decision_after_a_late_production_expects_its_overrun(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[float] = []
        real_decide = orchestrator_module.decide

        def decide(state: SessionState, **kwargs: object) -> Action:
            timings = kwargs["timings"]
            assert isinstance(timings, StageTimings)
            seen.append(timings.lateness_s)
            return real_decide(state, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(orchestrator_module, "decide", decide)
        world = World(late_s=40.0)
        await run(world, minutes=5)
        assert seen[0] == 0.0  # nothing to learn from before a production ends
        assert seen == sorted(seen)  # the most seen stays
        # Learnt to the ticks: the fake production starts at the loop's next sleep,
        # returns one turn after its due time, and is collected at the next tick.
        assert 40.0 <= seen[-1] < 40.0 + 3 * TUNING.tick_s

    async def test_productions_on_time_teach_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[float] = []
        real_decide = orchestrator_module.decide

        def decide(state: SessionState, **kwargs: object) -> Action:
            timings = kwargs["timings"]
            assert isinstance(timings, StageTimings)
            seen.append(timings.lateness_s)
            return real_decide(state, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(orchestrator_module, "decide", decide)
        await run(World(), minutes=5)
        assert set(seen) == {0.0}


def test_a_flash_that_died_with_its_task_never_holds_the_next_one() -> None:
    # One flash at a time: a flash nobody will produce would hold every later one.
    dying = Flash(seq=FLASH_SEQ_BASE + 2, notes=("m2",))
    ready = Flash(seq=FLASH_SEQ_BASE + 1, notes=("m1",), produced=True)
    state = SessionState(started_at=T0, stop_at=None, slots=(), flashes=(ready, dying))
    assert reloaded(state).flashes == (ready,)  # a ready one is still to be heard


def note(ident: str, seconds: int) -> FlashNote:
    return FlashNote(
        id=ident, sent_at=T0 + timedelta(seconds=seconds), topic="interest", excerpt="Hello."
    )


class TestAFlash:
    """ADR-324 decision 32: what LIA writes while the listener hears the antenna airs at once."""

    async def test_it_is_produced_published_heard_and_never_told_twice(self) -> None:
        world = World(flashing=True, notes=[note("m1", 60)])
        assert await run(world) is EndReason.TIMER
        assert [ids for ids, _, _ in world.flashes_made] == [("m1",)]
        _, cuts, resumes = world.flashes_made[0]
        assert cuts in (None, resumes)  # a programme it cuts is the one it goes back to
        assert FLASH_SEQ_BASE + 1 in world.ready
        assert world.state is not None
        assert world.state.flashes == ()  # the player heard it
        assert world.state.flash_since == T0 + timedelta(seconds=60)
        assert world.state.flash_audio_s == 20.0

    async def test_it_names_what_it_cuts_only_while_it_will_still_be_on_air(self) -> None:
        # Measured 2026-09-27: written over the welcome and heard after it, a flash
        # said « back to the welcome ». At three times its target the welcome is
        # nearly over 40 s in, and the day ahead is ready; at ten times, it is not.
        nearly_over = World(flashing=True, notes=[note("m1", 40)], shorten=3.0)
        await run(nearly_over, minutes=12)
        assert nearly_over.flashes_made[0][1:] == (None, RadioFormat.JOURNAL)
        long = World(flashing=True, notes=[note("m1", 40)], shorten=10.0)
        await run(long, minutes=12)
        assert long.flashes_made[0][1:] == (RadioFormat.OPENING, RadioFormat.OPENING)

    async def test_what_came_before_the_session_is_never_flashed(self) -> None:
        world = World(flashing=True, notes=[note("m0", -30)])
        await run(world)
        assert world.flashes_made == []
        assert world.asked and set(world.asked) == {T0}

    async def test_notes_that_arrive_together_air_in_one_flash(self) -> None:
        world = World(flashing=True, notes=[note("m1", 50), note("m2", 55)])
        await run(world)
        assert [ids for ids, _, _ in world.flashes_made] == [("m1", "m2")]

    async def test_a_flash_that_could_not_be_produced_is_not_tried_again(self) -> None:
        world = World(flashing=True, fail_flash=True, notes=[note("m1", 60)])
        assert await run(world) is EndReason.TIMER
        assert [ids for ids, _, _ in world.flashes_made] == [("m1",)]
        assert world.state is not None and world.state.flashes == ()
        assert FLASH_SEQ_BASE + 1 not in world.ready

    async def test_a_flash_its_editor_refused_is_not_tried_again(self) -> None:
        world = World(
            flashing=True,
            flash_instead=NothingAired("script_refused"),
            notes=[note("m1", 60)],
        )
        assert await run(world) is EndReason.TIMER
        assert [ids for ids, _, _ in world.flashes_made] == [("m1",)]
        assert world.state is not None and world.state.flashes == ()
        assert FLASH_SEQ_BASE + 1 not in world.ready

    async def test_a_spending_ceiling_reached_meanwhile_starts_no_flash(self) -> None:
        world = World(
            flashing=True, notes=[note("m1", 60)], blocked_from=T0 + timedelta(seconds=60)
        )
        assert await run(world, minutes=12) is EndReason.BUDGET
        assert world.flashes_made == []

    async def test_the_notifications_are_read_at_most_once_per_period(self) -> None:
        world = World(flashing=True)
        minutes = 3
        await run(world, minutes=minutes)
        assert 0 < len(world.asked) <= minutes * 60 / TUNING.flash_poll_s + 1

    async def test_with_the_notifications_silenced_nothing_is_read(self) -> None:
        world = World(notes=[note("m1", 60)])
        await run(world)
        assert world.asked == [] and world.flashes_made == []

    async def test_a_source_that_breaks_never_breaks_the_session(self) -> None:
        class Broken(World):
            async def since(self, after: datetime) -> list[FlashNote]:
                raise ConnectionError("database down")

        world = Broken(flashing=True)
        assert await run(world) is EndReason.TIMER
        assert world.flashes_made == []


async def _stop_at(world: World, seq: int, position_s: float) -> None:
    """The listener presses stop once the player reached ``position_s`` into ``seq``."""
    while not (world.playing == seq and world.position >= position_s):
        await asyncio.sleep(0)
    world.stop = True


class TestWhatWasHeard:
    """The ledger holds what the listener HEARD, line by line, never what was only produced
    (ADR-324 decision 35) — measured on dev 2026-09-27: at least four news programmes in ten
    filed as heard had never aired, produced ahead of a session stopped early."""

    async def test_what_was_only_produced_is_never_remembered(self) -> None:
        world = World()
        stopper = asyncio.create_task(_stop_at(world, 1, 1.0))
        assert await run(world, minutes=30) is EndReason.LISTENER
        await stopper
        assert 2 in world.ready  # produced ahead…
        assert remembered(world) == ["1:first"]  # …and never heard

    async def test_a_programme_cut_short_is_remembered_up_to_where_it_stopped(self) -> None:
        world = World()
        stopper = asyncio.create_task(_stop_at(world, 2, 1.0))
        assert await run(world, minutes=30) is EndReason.LISTENER
        await stopper
        assert remembered(world) == ["1:first", "1:second", "2:first"]

    async def test_every_line_heard_is_remembered_once(self) -> None:
        world = World()
        assert await run(world) is EndReason.TIMER
        keys = remembered(world)
        assert len(keys) == len(set(keys))
        assert world.state is not None
        played = [slot.seq for slot in world.state.slots if slot.reported]
        assert {f"{seq}:first" for seq in played} <= set(keys)

    async def test_a_programme_the_player_skipped_is_not_remembered(self) -> None:
        world = World(skip={2})
        stopper = asyncio.create_task(_stop_at(world, 3, 1.0))
        assert await run(world, minutes=30) is EndReason.LISTENER
        await stopper
        assert remembered(world) == ["1:first", "1:second", "3:first"]

    async def test_a_flash_is_remembered_once_the_player_says_it_heard_it(self) -> None:
        world = World(flashing=True, notes=[note("m1", 60)])
        assert await run(world) is EndReason.TIMER
        flashed = [key for key in remembered(world) if key.startswith("flash:")]
        assert flashed == [f"flash:{FLASH_SEQ_BASE + 1}"]

    @pytest.mark.parametrize(
        ("world", "minutes", "reason"),
        [
            (World(), 3, EndReason.TIMER),
            (World(blocked_from=T0 + timedelta(seconds=5)), 12, EndReason.BUDGET),
        ],
        ids=["timer", "budget"],
    )
    async def test_the_queue_a_session_plays_out_is_remembered_at_its_end(
        self, world: World, minutes: int, reason: EndReason
    ) -> None:
        """Ended on its timer or a spending ceiling, a session keeps its audio and the
        player plays its queue out after the loop is gone — the rest of the programme on
        air, what is ready after it, the farewell: filed at the end, once, or the next
        session would retell it."""
        assert await run(world, minutes=minutes) is reason
        queue = [seq for seq in world.ready if seq < FLASH_SEQ_BASE]
        # What the player had not heard when the loop ended: it plays it out afterwards.
        left = {f"{seq}:{line}" for seq in queue if seq not in world.aired_at for line in LINES}
        if world.playing is not None:
            on_air = world.ready[world.playing].memory
            left |= {key for line in on_air if line.offset_s > world.position for key in line.news}
        assert left
        keys = remembered(world)
        assert left <= set(keys)
        assert len(keys) == len(set(keys))

    async def test_an_end_nobody_plays_out_files_nothing_more(self) -> None:
        """Nobody listening: nothing is heard after the end, and nothing is filed for it."""
        world = World(silent=True)
        assert await run(world, minutes=30) is EndReason.IDLE
        assert world.ready and remembered(world) == []

    async def test_a_ledger_that_fails_costs_the_next_session_never_this_one(self) -> None:
        world = World(ledger_fails=True)
        assert await run(world) is EndReason.TIMER

    async def test_a_restarted_loop_files_what_was_produced_before_it(self) -> None:
        """A loop restarted (a deploy, a reload) starts from the segments already published:
        heard after the restart, they are filed all the same."""
        opening = Slot(
            seq=1,
            format=RadioFormat.OPENING,
            station_id=True,
            air_at=T0,
            duration_s=float(FORMAT_SPECS[RadioFormat.OPENING].target_seconds),
            reported=True,
        )
        state = replace(
            start(T0, T0 + timedelta(minutes=30)), slots=(opening,), produced=frozenset({1})
        )
        world = World(playing=1)
        world.ready = {1: segment(opening)}
        stopper = asyncio.create_task(_stop_at(world, 1, opening.duration_s - 1))
        reason = await run_session(
            state,
            listening=LISTENING,
            ports=world.ports(),
            tuning=TUNING,
            ready={1: segment(opening)},
        )
        await stopper
        assert reason is EndReason.LISTENER
        assert remembered(world)[:2] == ["1:first", "1:second"]
