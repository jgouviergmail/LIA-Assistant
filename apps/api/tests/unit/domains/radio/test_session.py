"""A session's decisions, alone and over a simulated half hour of listening."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.radio.constants import SIGN_OFF_WINDOW_SECONDS
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat
from src.domains.radio.grid import GridDecision, GridReason, next_segment
from src.domains.radio.pacing import Playhead, StageTimings, production_s
from src.domains.radio.programme import hand_over_to
from src.domains.radio.session import (
    ActionKind,
    EndReason,
    SessionRules,
    SessionState,
    budget_reached,
    decide,
    effective_stop_at,
    ended_for,
    grid_inputs,
    needs_planning,
    plan,
    production_failed,
    production_started,
    production_succeeded,
    reported,
    start,
    stopped,
    withdrawn,
)
from tests.unit.domains.radio.fakes import voices_by_format

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 26, 8, 50, tzinfo=UTC)
TIMINGS = StageTimings(
    writer_s=6.0, analysis_s=15.0, tts_realtime_factor=0.42, tts_concurrency=3, mix_s=0.5
)
RULES = SessionRules(
    idle_timeout_s=60,
    pause_timeout_s=900,
    failures_max=3,
    lookahead_safety=1.5,
    lookahead_margin_s=15,
)


def decision(fmt: RadioFormat) -> GridDecision:
    return GridDecision(format=fmt, reason=GridReason.ROTATION, station_id_due=False)


def planned(*formats: RadioFormat) -> SessionState:
    state = start(T0, T0 + timedelta(minutes=30))
    for fmt in formats:
        air_at = grid_inputs(
            state,
            now=T0,
            first_delay_s=15,
            timezone=UTC,
            frequencies={},
            available=frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW},
            public_mode=False,
            voices_by_format=voices_by_format(2),
        ).air_at
        state = plan(state, decision(fmt), air_at)
    return state


def act(state: SessionState, now: datetime = T0) -> ActionKind:
    return decide(state, now=now, timings=TIMINGS, language="fr", rules=RULES).kind


class TestDecide:
    def test_two_slots_wait_planned_the_next_and_its_hand_over(self) -> None:
        assert needs_planning(planned(RadioFormat.OPENING))
        assert not needs_planning(planned(RadioFormat.OPENING, RadioFormat.JOURNAL))
        assert not needs_planning(planned(RadioFormat.OPENING, RadioFormat.SIGN_OFF))

    def test_before_the_first_sound_two_productions_run_at_once(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.JOURNAL, RadioFormat.HEADLINES)
        # The player reports from the click: waiting for the opening is no listening.
        state = reported(state, Playhead(seq=1, position_s=0.0, reported_at=T0, playing=False))
        first = decide(state, now=T0, timings=TIMINGS, language="fr", rules=RULES)
        assert first.kind is ActionKind.PRODUCE and first.slot and first.slot.seq == 1
        state = production_started(state, 1)
        second = decide(state, now=T0, timings=TIMINGS, language="fr", rules=RULES)
        assert second.slot is not None and second.slot.seq == 2
        assert act(production_started(state, 2)) is ActionKind.WAIT

    def test_once_listening_one_production_at_a_time_and_only_when_needed(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.JOURNAL, RadioFormat.HEADLINES)
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        state = production_succeeded(production_started(state, 2), 2, 90.0)
        now = T0 + timedelta(seconds=20)
        state = reported(state, Playhead(seq=1, position_s=5.0, reported_at=now))
        # 20 s of opening + 90 s of my day ahead: the headlines can wait.
        assert act(state, now) is ActionKind.WAIT
        later = now + timedelta(seconds=80)
        state = reported(state, Playhead(seq=2, position_s=60.0, reported_at=later))
        assert act(state, later) is ActionKind.PRODUCE

    def test_a_short_segment_starts_early_when_a_long_production_follows_it(self) -> None:
        """A brief heard in half a minute cannot cover the analysis produced after it."""
        state = planned(
            RadioFormat.OPENING, RadioFormat.JOURNAL, RadioFormat.BRIEF, RadioFormat.ANALYSIS
        )
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        state = production_succeeded(production_started(state, 2), 2, 90.0)
        brief = production_s(RadioFormat.BRIEF, TIMINGS, "fr")
        analysis = production_s(RadioFormat.ANALYSIS, TIMINGS, "fr")
        heard_in = FORMAT_SPECS[RadioFormat.BRIEF].target_seconds
        alone = brief * RULES.lookahead_safety + RULES.lookahead_margin_s
        chained = (brief + analysis - heard_in) * RULES.lookahead_safety + RULES.lookahead_margin_s
        ahead = (alone + chained) / 2
        assert alone < ahead < chained <= 90.0
        now = T0 + timedelta(seconds=200)
        state = reported(state, Playhead(seq=2, position_s=90.0 - ahead, reported_at=now))
        assert act(state, now) is ActionKind.PRODUCE

    def test_the_produced_sign_off_ends_the_session(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.SIGN_OFF)
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        state = production_started(state, 2)
        state = production_succeeded(state, 2, 12.0)
        assert state.ended is EndReason.TIMER
        assert act(state) is ActionKind.END

    def test_the_sign_off_waits_for_what_is_still_in_flight(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.SIGN_OFF)
        state = production_started(production_started(state, 1), 2)
        state = production_succeeded(state, 2, 12.0)
        assert state.ended is None
        assert production_succeeded(state, 1, 25.0).ended is EndReason.TIMER

    def test_nobody_listening_stops_the_antenna(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.JOURNAL)
        assert act(state, T0 + timedelta(seconds=61)) is ActionKind.END

    def test_a_long_pause_stops_it_but_the_stations_music_is_no_pause(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.JOURNAL)
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        waiting = reported(state, Playhead(seq=2, position_s=0.0, reported_at=T0, playing=False))
        assert waiting.paused_since is None
        # A ready segment not playing yet is no pause either: only the listener pauses.
        about_to_play = reported(
            state, Playhead(seq=1, position_s=0.0, reported_at=T0, playing=False)
        )
        assert about_to_play.paused_since is None
        paused = reported(state, pause_at(1, T0))
        later = T0 + timedelta(seconds=901)
        still = reported(paused, pause_at(1, later))
        assert still.paused_since == T0
        assert act(still, later) is ActionKind.END

    def test_repeated_failures_stop_it_and_a_failed_slot_leaves_the_order(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.JOURNAL, RadioFormat.HEADLINES)
        opening_air = state.slots[0].air_at
        state = production_failed(production_started(state, 1), 1, at=T0)
        assert [s.seq for s in state.slots] == [2, 3]
        assert state.slots[0].air_at == opening_air  # the next one moves up
        for seq in (2, 3):
            state = production_failed(production_started(state, seq), seq, at=T0)
        assert act(state) is ActionKind.END


def pause_at(seq: int, when: datetime, position_s: float = 4.0) -> Playhead:
    return Playhead(seq=seq, position_s=position_s, reported_at=when, playing=False, paused=True)


def play_at(seq: int, when: datetime, position_s: float = 4.0) -> Playhead:
    return Playhead(seq=seq, position_s=position_s, reported_at=when, playing=True)


class TestTimer:
    """The automatic stop counts LISTENING time: a pause does not run it down."""

    def heard(self) -> SessionState:
        state = planned(RadioFormat.OPENING, RadioFormat.JOURNAL)
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        return reported(state, play_at(1, T0, position_s=0.0))

    def test_a_pause_freezes_the_timer_while_it_lasts(self) -> None:
        state = self.heard()
        stop = state.stop_at
        assert stop is not None
        paused = reported(state, pause_at(1, T0 + timedelta(seconds=10)))
        assert effective_stop_at(paused, T0 + timedelta(seconds=10)) == stop
        assert effective_stop_at(paused, T0 + timedelta(seconds=70)) == stop + timedelta(seconds=60)

    def test_resuming_moves_the_stop_by_the_whole_pause(self) -> None:
        state = self.heard()
        stop = state.stop_at
        assert stop is not None
        paused = reported(state, pause_at(1, T0 + timedelta(seconds=10)))
        paused = reported(paused, pause_at(1, T0 + timedelta(seconds=15)))
        resumed = reported(paused, play_at(1, T0 + timedelta(seconds=130)))
        assert resumed.paused_since is None
        assert resumed.stop_at == stop + timedelta(seconds=120)
        assert effective_stop_at(resumed, T0 + timedelta(seconds=500)) == resumed.stop_at

    def test_a_pause_over_the_stations_music_is_a_pause_too(self) -> None:
        state = self.heard()
        stop = state.stop_at
        assert stop is not None
        paused = reported(state, pause_at(2, T0 + timedelta(seconds=40), position_s=0.0))
        assert paused.paused_since == T0 + timedelta(seconds=40)
        waiting_again = reported(
            paused,
            Playhead(seq=2, position_s=0.0, reported_at=T0 + timedelta(seconds=100), playing=False),
        )
        assert waiting_again.paused_since is None
        assert waiting_again.stop_at == stop + timedelta(seconds=60)

    def test_the_grid_reads_the_frozen_timer(self) -> None:
        state = reported(self.heard(), pause_at(1, T0 + timedelta(seconds=10)))
        now = T0 + timedelta(minutes=5)
        inputs = grid_inputs(
            state,
            now=now,
            first_delay_s=15,
            timezone=UTC,
            frequencies={},
            available=frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW},
            public_mode=False,
            voices_by_format=voices_by_format(2),
        )
        assert inputs.stop_at == effective_stop_at(state, now)

    def test_a_session_without_a_timer_has_no_stop_to_move(self) -> None:
        state = start(T0, None)
        paused = reported(state, pause_at(1, T0))
        assert effective_stop_at(paused, T0 + timedelta(minutes=5)) is None
        assert reported(paused, play_at(1, T0 + timedelta(minutes=5))).stop_at is None


class TestFarewell:
    """A farewell is planned on projections and CONFIRMED on the real running order."""

    def running(self, stop_in_s: float) -> SessionState:
        state = start(T0, T0 + timedelta(seconds=stop_in_s))
        state = plan(state, decision(RadioFormat.OPENING), T0)
        state = plan(state, decision(RadioFormat.COLUMN), state.slots[-1].ends_at)
        state = plan(state, decision(RadioFormat.SIGN_OFF), state.slots[-1].ends_at)
        return state

    def test_a_farewell_that_would_come_early_is_withdrawn(self) -> None:
        column_target = FORMAT_SPECS[RadioFormat.COLUMN].target_seconds
        # Planned: the opening (25 s) then a column projected at its target —
        # the farewell looked due inside the window.
        state = self.running(stop_in_s=25 + column_target + 60)
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        state = reported(state, play_at(1, T0, position_s=0.0))
        # The column came out at a third of its target: the farewell is early.
        state = production_succeeded(production_started(state, 2), 2, column_target / 3)
        action = decide(
            state, now=T0 + timedelta(seconds=5), timings=TIMINGS, language="fr", rules=RULES
        )
        assert action.kind is ActionKind.WITHDRAW
        assert action.slot is not None and action.slot.format is RadioFormat.SIGN_OFF
        withdrawn_state = withdrawn(state, action.slot.seq)
        assert [slot.format for slot in withdrawn_state.slots] == [
            RadioFormat.OPENING,
            RadioFormat.COLUMN,
        ]
        assert withdrawn_state.failures == state.failures
        assert needs_planning(withdrawn_state)

    def test_a_farewell_inside_its_window_is_produced(self) -> None:
        column_target = FORMAT_SPECS[RadioFormat.COLUMN].target_seconds
        state = self.running(stop_in_s=25 + column_target + 60)
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        state = reported(state, play_at(1, T0, position_s=0.0))
        state = production_succeeded(production_started(state, 2), 2, float(column_target))
        # The farewell airs 60 s before the stop: produced once the column nears its end.
        late = T0 + timedelta(seconds=25 + column_target - 20)
        state = reported(state, play_at(2, late, position_s=column_target - 20))
        assert act(state, late) is ActionKind.PRODUCE

    def test_a_pause_moves_the_planned_farewell_with_the_stop(self) -> None:
        """The farewell was due, then the listener paused for ten minutes: the stop
        AND the running order moved by the pause, so the farewell still closes it."""
        state = start(T0, T0 + timedelta(seconds=100))
        state = plan(state, decision(RadioFormat.OPENING), T0)
        state = plan(state, decision(RadioFormat.SIGN_OFF), T0 + timedelta(seconds=25))
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        state = reported(state, play_at(1, T0, position_s=0.0))
        state = reported(state, pause_at(1, T0 + timedelta(seconds=10), position_s=10.0))
        resumed_at = T0 + timedelta(minutes=10, seconds=10)
        state = reported(state, play_at(1, resumed_at, position_s=10.0))
        assert state.stop_at == T0 + timedelta(minutes=10, seconds=100)
        assert state.slots[-1].air_at == T0 + timedelta(minutes=10, seconds=25)
        action = decide(state, now=resumed_at, timings=TIMINGS, language="fr", rules=RULES)
        assert action.kind is ActionKind.PRODUCE

    def test_a_farewell_whose_projection_lags_is_judged_from_now(self) -> None:
        """The music has been filling a wait: the farewell airs NOW, not at its stale
        projection — and now is inside the window."""
        state = start(T0, T0 + timedelta(seconds=200))
        state = plan(state, decision(RadioFormat.OPENING), T0)
        state = plan(state, decision(RadioFormat.SIGN_OFF), T0 + timedelta(seconds=25))
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        state = reported(state, play_at(1, T0, position_s=0.0))  # the listener hears it
        now = T0 + timedelta(seconds=150)
        state = reported(state, Playhead(seq=2, position_s=0.0, reported_at=now, playing=False))
        assert act(state, now) is ActionKind.PRODUCE

    def test_nothing_hands_over_to_a_farewell_that_may_still_move(self) -> None:
        state = self.running(stop_in_s=3600)
        assert hand_over_to(state.slots, 2, ready={state.slots[2].seq}) is None
        assert hand_over_to(state.slots, 1, ready=set()) is None
        assert hand_over_to(state.slots, 1, ready={state.slots[1].seq}) is RadioFormat.COLUMN


class TestThePlannedListening:
    def test_a_timed_session_knows_how_long_it_is_meant_to_be_heard(self) -> None:
        assert start(T0, T0 + timedelta(minutes=30)).planned_s == 1800.0
        assert start(T0, None).planned_s is None

    def test_a_pause_moves_the_stop_never_the_listening_planned(self) -> None:
        state = start(T0, T0 + timedelta(minutes=30))
        paused = reported(
            state,
            Playhead(seq=1, position_s=0.0, reported_at=T0, playing=False, paused=True),
        )
        resumed = reported(
            paused,
            Playhead(
                seq=1,
                position_s=0.0,
                reported_at=T0 + timedelta(minutes=5),
                playing=True,
                paused=False,
            ),
        )
        assert resumed.stop_at == T0 + timedelta(minutes=35)
        assert resumed.planned_s == 1800.0


class TestFailures:
    def test_a_failed_production_is_remembered_for_the_grid(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.ANALYSIS, RadioFormat.BRIEF)
        failed_at = T0 + timedelta(minutes=3)
        state = production_failed(production_started(state, 2), 2, at=failed_at)
        assert [(seg.format, seg.air_at) for seg in state.failed] == [
            (RadioFormat.ANALYSIS, failed_at)
        ]
        inputs = grid_inputs(
            state,
            now=failed_at,
            first_delay_s=15,
            timezone=UTC,
            frequencies={},
            available=frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW},
            public_mode=False,
            voices_by_format=voices_by_format(2),
        )
        assert inputs.failed == state.failed

    def test_a_format_keeps_only_its_latest_failure(self) -> None:
        state = planned(RadioFormat.OPENING, RadioFormat.ANALYSIS)
        state = production_failed(production_started(state, 2), 2, at=T0)
        later = T0 + timedelta(minutes=30)
        state = plan(state, decision(RadioFormat.ANALYSIS), later)
        again = state.slots[-1].seq
        state = production_failed(production_started(state, again), again, at=later)
        assert [(seg.format, seg.air_at) for seg in state.failed] == [(RadioFormat.ANALYSIS, later)]

    def test_a_failed_format_takes_its_waiting_slots_with_it(self) -> None:
        """A format rests from its failure, whatever was planned for it BEFORE it.

        Measured 2026-09-27 on dev: a second column planned while the first was
        in production was produced after the first one's refusal, failed the
        same way, and the third failure in a row ended the session 25 s in. A
        slot already in production is paid for and finishes.
        """
        state = planned(
            RadioFormat.OPENING,
            RadioFormat.COLUMN,
            RadioFormat.COLUMN,
            RadioFormat.COLUMN,
            RadioFormat.BRIEF,
        )
        state = production_started(production_started(state, 2), 3)
        state = production_failed(state, 2, at=T0)
        assert [slot.seq for slot in state.slots] == [1, 3, 5]
        assert state.failures == 1

    def test_nothing_aired_rests_its_format_and_never_stops_the_station(self) -> None:
        """A station that chose not to air is no station in trouble.

        Measured 2026-09-27 on dev: an analysis its editor refused, a corner with
        nothing to say and a refused column ended a default account's session
        30 s in — and cut the news flash it was voicing.
        """
        state = planned(
            RadioFormat.OPENING, RadioFormat.ANALYSIS, RadioFormat.JOURNAL, RadioFormat.COLUMN
        )
        for seq in (2, 3, 4):
            state = production_failed(production_started(state, seq), seq, at=T0, counted=False)
        assert state.failures == 0
        assert {seg.format for seg in state.failed} == {
            RadioFormat.ANALYSIS,
            RadioFormat.JOURNAL,
            RadioFormat.COLUMN,
        }
        assert act(state) is not ActionKind.END

    def test_a_spending_ceiling_stops_it_and_says_so(self) -> None:
        state = budget_reached(planned(RadioFormat.OPENING))
        assert act(state) is ActionKind.END
        assert state.ended is EndReason.BUDGET
        assert budget_reached(stopped(state)).ended is EndReason.BUDGET

    def test_the_listener_stops_it(self) -> None:
        state = stopped(planned(RadioFormat.OPENING))
        assert state.ended is EndReason.LISTENER
        assert stopped(production_succeeded(state, 1, 25.0)).ended is EndReason.LISTENER

    def test_the_first_reason_to_end_it_stands(self) -> None:
        """The farewell aired and the player is playing its queue out: a stop pressed
        then, a ceiling or a loop defect must not rename the end — « the listener
        stopped » would send the audio still being heard to the bin."""
        state = planned(RadioFormat.OPENING, RadioFormat.SIGN_OFF)
        state = production_succeeded(production_started(state, 1), 1, 25.0)
        signed_off = production_succeeded(production_started(state, 2), 2, 12.0)
        assert signed_off.ended is EndReason.TIMER
        assert stopped(signed_off).ended is EndReason.TIMER
        assert budget_reached(signed_off).ended is EndReason.TIMER
        assert ended_for(signed_off, EndReason.FAILURES).ended is EndReason.TIMER
        assert ended_for(planned(RadioFormat.OPENING), EndReason.IDLE).ended is EndReason.IDLE


@dataclass
class Listener:
    """A player that plays every ready segment in order and reports every 5 s."""

    durations: dict[int, float] = field(default_factory=dict)
    current: int | None = None
    position: float = 0.0
    last_played: int = 0
    heard: list[int] = field(default_factory=list)
    heard_at: dict[int, datetime] = field(default_factory=dict)
    first_sound_at: datetime | None = None
    silent_ticks: int = 0
    farewell_wait_ticks: int = 0

    def tick(self, now: datetime, ready: set[int], planned: list[tuple[int, RadioFormat]]) -> None:
        if self.current is not None:
            self.position += 1.0
            if self.position >= self.durations[self.current]:
                self.last_played = self.current
                self.current = None
        if self.current is None:
            upcoming = sorted(seq for seq in ready if seq > self.last_played)
            if upcoming:
                self.current, self.position = upcoming[0], 0.0
                self.heard.append(upcoming[0])
                self.heard_at[upcoming[0]] = now
                self.first_sound_at = self.first_sound_at or now
            elif self.first_sound_at is not None:
                ahead = [fmt for seq, fmt in planned if seq > self.last_played]
                # Silence while a programme is still to come is a gap. The music
                # that plays until the farewell's window is the station keeping
                # its promise of the timer, counted apart; after the last
                # segment it is the end of the session.
                if ahead and ahead[0] is RadioFormat.SIGN_OFF:
                    self.farewell_wait_ticks += 1
                elif ahead:
                    self.silent_ticks += 1

    def playhead(self, now: datetime) -> Playhead:
        seq = self.current if self.current is not None else self.last_played + 1
        return Playhead(
            seq=seq, position_s=self.position, reported_at=now, playing=bool(self.current)
        )


@dataclass
class HalfHour:
    """One half-hour driven second by second: the grid plans, the loop decides, a player listens."""

    rng: random.Random
    #: Distinct voices the cast holds: with four, the debate airs too.
    voices: int = 2
    state: SessionState = field(default_factory=lambda: start(T0, T0 + timedelta(minutes=30)))
    listener: Listener = field(default_factory=Listener)
    finishing: dict[int, datetime] = field(default_factory=dict)
    max_in_flight_listening: int = 0

    def plan_next(self, now: datetime) -> None:
        if not needs_planning(self.state):
            return
        inputs = grid_inputs(
            self.state,
            now=now,
            first_delay_s=production_s(RadioFormat.OPENING, TIMINGS, "fr"),
            timezone=UTC,
            frequencies={},
            available=frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW},
            public_mode=False,
            voices_by_format=voices_by_format(self.voices),
        )
        choice = next_segment(inputs, self.rng)
        if choice is not None:
            self.state = plan(self.state, choice, inputs.air_at)

    def finish_productions(self, now: datetime) -> None:
        for seq, done_at in sorted(self.finishing.items()):
            if done_at > now:
                continue
            slot = next(s for s in self.state.slots if s.seq == seq)
            duration = float(FORMAT_SPECS[slot.format].target_seconds)
            self.listener.durations[seq] = duration
            self.state = production_succeeded(self.state, seq, duration)
            del self.finishing[seq]

    def act(self, now: datetime) -> ActionKind:
        action = decide(self.state, now=now, timings=TIMINGS, language="fr", rules=RULES)
        if action.kind is ActionKind.PRODUCE and action.slot is not None:
            self.state = production_started(self.state, action.slot.seq)
            self.finishing[action.slot.seq] = now + timedelta(
                seconds=production_s(action.slot.format, TIMINGS, "fr")
            )
        return action.kind

    def listen(self, now: datetime) -> None:
        if any(slot.reported for slot in self.state.slots):  # the listener hears the antenna
            in_flight = len(self.state.in_production)
            self.max_in_flight_listening = max(self.max_in_flight_listening, in_flight)
        self.listener.tick(
            now, set(self.state.produced), [(slot.seq, slot.format) for slot in self.state.slots]
        )
        if int((now - T0).total_seconds()) % 5 == 0:
            self.state = reported(self.state, self.listener.playhead(now))

    def run(self) -> None:
        now = T0
        for _ in range(3 * 3600):
            self.plan_next(now)
            self.finish_productions(now)
            kind = self.act(now)
            self.listen(now)
            if kind is ActionKind.END and self.listener.current is None:
                return
            now += timedelta(seconds=1)


@pytest.mark.parametrize("voices", [2, 4])
@pytest.mark.parametrize("seed", range(12))
def test_a_half_hour_is_heard_without_a_gap_and_ends_on_its_farewell(
    seed: int, voices: int
) -> None:
    half_hour = HalfHour(random.Random(seed), voices=voices)
    half_hour.run()
    state, listener = half_hour.state, half_hour.listener
    max_in_flight_listening = half_hour.max_in_flight_listening

    formats = [slot.format for slot in state.slots]
    assert formats[0] is RadioFormat.OPENING and formats[-1] is RadioFormat.SIGN_OFF
    assert state.ended is EndReason.TIMER
    assert listener.heard == [slot.seq for slot in state.slots]
    assert listener.silent_ticks == 0, "a gap between two segments after the start"
    assert listener.first_sound_at is not None
    assert (listener.first_sound_at - T0).total_seconds() <= 20
    assert max_in_flight_listening <= 1
    assert state.stop_at is not None
    farewell_heard = listener.heard_at[state.slots[-1].seq]
    window_opens = state.stop_at - timedelta(seconds=SIGN_OFF_WINDOW_SECONDS)
    assert farewell_heard >= window_opens, "the farewell never comes early"
    assert farewell_heard <= state.stop_at, "and it is heard before the stop"


class TestTheMusicBetweenProgrammes:
    """ADR-324 decision 36: five seconds of the station's music between two programmes —
    fewer programmes produced over a long listening, and a breath between them."""

    def test_a_session_keeps_the_pause_it_started_with_in_every_projection(self) -> None:
        state = start(T0, T0 + timedelta(minutes=30), gap_s=5.0)
        for fmt in (RadioFormat.OPENING, RadioFormat.BRIEF, RadioFormat.HEADLINES):
            air_at = grid_inputs(
                state,
                now=T0,
                first_delay_s=15,
                timezone=UTC,
                frequencies={},
                available=frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW},
                public_mode=False,
                voices_by_format=voices_by_format(2),
            ).air_at
            state = plan(state, decision(fmt), air_at)
        opening, brief, headlines = state.slots
        assert state.gap_s == 5.0
        assert brief.air_at == opening.ends_at + timedelta(seconds=5)

        state = production_succeeded(production_started(state, 1), 1, 40.0)
        assert state.slots[1].air_at == state.slots[0].ends_at + timedelta(seconds=5)
        playing = Playhead(
            seq=1, position_s=10.0, reported_at=T0 + timedelta(seconds=30), playing=True
        )
        state = reported(state, playing)
        assert state.slots[1].air_at == state.slots[0].ends_at + timedelta(seconds=5)
        assert state.slots[2].air_at == state.slots[1].ends_at + timedelta(seconds=5)

    def test_a_session_started_without_one_chains_its_programmes(self) -> None:
        opening, brief = planned(RadioFormat.OPENING, RadioFormat.BRIEF).slots
        assert brief.air_at == opening.ends_at
