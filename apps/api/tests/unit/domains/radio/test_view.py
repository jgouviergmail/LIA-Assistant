"""What a report is answered: status, what is left to play, and only public sources."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from src.domains.radio.aired import HeardLine
from src.domains.radio.facts import SourceRef
from src.domains.radio.flash import Flash
from src.domains.radio.formats import MusicMood, RadioFormat, RadioRole
from src.domains.radio.pacing import Playhead
from src.domains.radio.production import ProducedSegment, TranscriptLine
from src.domains.radio.programme import Slot
from src.domains.radio.schemas import RadioSessionResponse
from src.domains.radio.session import EndReason, SessionState
from src.domains.radio.view import (
    CostEstimate,
    cost_estimate,
    pending_seqs,
    session_response,
    session_status,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 26, 8, 50, tzinfo=UTC)
#: A listener ten hours ahead of UTC: 08:50 UTC is 18:50 on their clock — evening.
AHEAD = timezone(timedelta(hours=10))
FORMATS = (RadioFormat.OPENING, RadioFormat.JOURNAL, RadioFormat.BULLETIN, RadioFormat.SIGN_OFF)
SLOTS = tuple(
    Slot(
        seq=seq,
        format=fmt,
        station_id=seq == 1,
        air_at=T0 + timedelta(minutes=seq),
        duration_s=30.0,
    )
    for seq, fmt in enumerate(FORMATS, start=1)
)
STATE = SessionState(started_at=T0, stop_at=T0 + timedelta(minutes=30), slots=SLOTS[:3])


def segment(title: str, *sources: SourceRef) -> ProducedSegment:
    return ProducedSegment(
        title=title,
        audio_path=Path("x.mp3"),
        duration_s=30.0,
        transcript=(
            TranscriptLine(role=RadioRole.HOST, text="Hello.", offset_s=1.0, sources=sources),
        ),
        dropped_lines=0,
        unrendered=(),
    )


READY = {
    1: segment("Opening"),
    2: segment("Your day", SourceRef(label="Agenda", record_kind="event", record_id="evt-7")),
    3: segment(
        "News",
        SourceRef(label="Example News", url="https://news.example/1", story_key="story-1"),
    ),
}


@pytest.mark.parametrize(
    ("state", "status"),
    [
        (STATE, "starting"),
        (replace(STATE, produced=frozenset({1})), "on_air"),
        (replace(STATE, produced=frozenset({1}), slots=SLOTS), "ending"),
        (replace(STATE, produced=frozenset({1}), ended=EndReason.TIMER), "ended"),
    ],
)
def test_the_status_follows_the_running_order(state: SessionState, status: str) -> None:
    assert session_status(state) == status


def test_only_what_is_left_to_play_is_listed_and_an_ended_session_keeps_it() -> None:
    state = replace(
        STATE,
        produced=frozenset({1, 2, 3}),
        playhead=Playhead(seq=2, position_s=4.0, reported_at=T0),
        ended=EndReason.BUDGET,
    )
    answer = session_response(
        uuid4(), state, READY, cost_eur=0.0123, startup_estimate_s=14.0, now=T0, zone=UTC
    )
    assert [s.seq for s in answer.segments] == [2, 3]
    assert [s.format for s in answer.segments] == [RadioFormat.JOURNAL, RadioFormat.BULLETIN]
    assert (answer.status, answer.end_reason, answer.cost_eur) == ("ended", "budget", 0.0123)


def test_a_record_of_the_person_is_named_by_its_family_alone() -> None:
    state = replace(STATE, produced=frozenset({2, 3}))
    wire = json.dumps(
        session_response(
            uuid4(), state, READY, cost_eur=None, startup_estimate_s=None, now=T0, zone=UTC
        ).model_dump(mode="json")
    )
    assert "Agenda" in wire and "evt-7" not in wire and "record_" not in wire
    assert "https://news.example/1" in wire


def test_what_a_segment_remembers_never_reaches_the_player() -> None:
    """What each line tells is the server's own: the keys of the listener's records."""
    remembering = replace(
        READY[2],
        memory=(HeardLine(offset_s=1.0, personal=frozenset({"event:evt-7"}), headlines=("H",)),),
    )
    state = replace(STATE, produced=frozenset({2}))
    wire = json.dumps(
        session_response(
            uuid4(),
            state,
            {2: remembering},
            cost_eur=None,
            startup_estimate_s=None,
            now=T0,
            zone=UTC,
        ).model_dump(mode="json")
    )
    assert "evt-7" not in wire and "memory" not in wire


def test_a_segment_not_published_yet_is_not_listed() -> None:
    state = replace(STATE, produced=frozenset({1, 2}))
    answer = session_response(
        uuid4(), state, {1: READY[1]}, cost_eur=None, startup_estimate_s=None, now=T0, zone=UTC
    )
    assert [s.seq for s in answer.segments] == [1]


def test_every_segment_carries_the_music_of_its_programme_on_the_listeners_clock() -> None:
    state = replace(STATE, produced=frozenset({1, 2, 3}))
    answer = session_response(
        uuid4(), state, READY, cost_eur=None, startup_estimate_s=None, now=T0, zone=AHEAD
    )
    assert [s.mood for s in answer.segments] == [
        MusicMood.EVENING,
        MusicMood.EVENING,
        MusicMood.NEWS,
    ]
    # UTC 08:50 is the morning; the listener's evening is what the music follows.
    assert (
        session_response(
            uuid4(), state, READY, cost_eur=None, startup_estimate_s=None, now=T0, zone=UTC
        )
        .segments[0]
        .mood
        is MusicMood.MORNING
    )


def test_the_session_plays_the_music_of_what_airs_next() -> None:
    first = replace(STATE, produced=frozenset({1, 2, 3}))
    news = replace(first, playhead=Playhead(seq=3, position_s=0.0, reported_at=T0))
    assert (
        session_response(
            uuid4(), first, READY, cost_eur=None, startup_estimate_s=None, now=T0, zone=AHEAD
        ).mood
        is MusicMood.EVENING
    )
    assert (
        session_response(
            uuid4(), news, READY, cost_eur=None, startup_estimate_s=None, now=T0, zone=AHEAD
        ).mood
        is MusicMood.NEWS
    )


def test_before_anything_is_planned_the_music_follows_the_listeners_hour() -> None:
    fresh = SessionState(started_at=T0, stop_at=None)
    answer = session_response(
        uuid4(), fresh, {}, cost_eur=None, startup_estimate_s=12.0, now=T0, zone=AHEAD
    )
    assert answer.mood is MusicMood.EVENING
    assert answer.segments == []


def test_a_clock_nobody_knows_publishes_no_music() -> None:
    state = replace(STATE, produced=frozenset({1, 2, 3}))
    answer = session_response(
        uuid4(), state, READY, cost_eur=None, startup_estimate_s=None, now=T0, zone=None
    )
    assert answer.mood is None
    assert all(s.mood is None for s in answer.segments)


def test_the_stop_shown_does_not_run_while_the_listener_has_paused() -> None:
    paused = replace(STATE, paused_since=T0 + timedelta(seconds=60))
    answer = session_response(
        uuid4(),
        paused,
        {},
        cost_eur=None,
        startup_estimate_s=None,
        now=T0 + timedelta(seconds=160),
        zone=UTC,
    )
    assert answer.stop_at == T0 + timedelta(minutes=30, seconds=100)
    running = session_response(
        uuid4(), STATE, {}, cost_eur=None, startup_estimate_s=None, now=T0, zone=UTC
    )
    assert running.stop_at == T0 + timedelta(minutes=30)


class TestTheCostEstimate:
    """What the planned listening will cost, from what a second of radio has cost."""

    def produced(self, *seconds: float, planned_s: float | None = 1800.0) -> SessionState:
        slots = tuple(
            replace(slot, duration_s=duration)
            for slot, duration in zip(SLOTS, seconds, strict=False)
        )
        return replace(
            STATE,
            slots=slots,
            produced=frozenset(slot.seq for slot in slots),
            planned_s=planned_s,
        )

    def test_the_planned_listening_is_priced_at_what_a_second_of_radio_cost(self) -> None:
        estimate = cost_estimate(self.produced(60.0, 60.0, 60.0), 0.03, min_audio_s=120.0)
        assert estimate is not None
        assert (estimate.eur, estimate.seconds) == (pytest.approx(0.3), 1800.0)

    def test_nothing_is_estimated_before_enough_radio_was_produced(self) -> None:
        assert cost_estimate(self.produced(30.0, 60.0), 0.01, min_audio_s=120.0) is None

    def test_a_programme_still_in_production_is_no_radio_yet(self) -> None:
        state = replace(self.produced(60.0, 60.0, 60.0), produced=frozenset({1, 2}))
        estimate = cost_estimate(state, 0.03, min_audio_s=120.0)
        assert estimate is not None
        assert (estimate.eur, estimate.seconds) == (pytest.approx(0.45), 1800.0)

    def test_without_a_timer_the_estimate_is_for_an_hour(self) -> None:
        untimed = replace(self.produced(60.0, 60.0, 60.0, planned_s=None), stop_at=None)
        estimate = cost_estimate(untimed, 0.03, min_audio_s=120.0)
        assert estimate is not None
        assert (estimate.eur, estimate.seconds) == (pytest.approx(0.6), 3600.0)

    def test_an_unknown_cost_estimates_nothing(self) -> None:
        assert cost_estimate(self.produced(60.0, 60.0, 60.0), None, min_audio_s=120.0) is None

    def test_a_session_over_prices_no_listening_left(self) -> None:
        # Its end is decided (the timer, a ceiling, the listener): the planned
        # listening will not happen, while the player drains what is queued.
        over = replace(self.produced(60.0, 60.0, 60.0), ended=EndReason.BUDGET)
        assert cost_estimate(over, 0.03, min_audio_s=120.0) is None

    def test_a_timer_nobody_recorded_is_not_priced_as_an_hour(self) -> None:
        # A session stored before ``planned_s`` existed has a stop and no plan:
        # pricing it as an hour would say « for 60 min » on a 30-minute timer.
        legacy = replace(
            self.produced(60.0, 60.0, 60.0, planned_s=None), stop_at=T0 + timedelta(minutes=30)
        )
        assert cost_estimate(legacy, 0.03, min_audio_s=120.0) is None

    def test_no_rate_is_drawn_from_no_radio_whatever_the_minimum(self) -> None:
        # The minimum is a setting; nothing produced divides by nothing at any.
        assert cost_estimate(self.produced(), 0.01, min_audio_s=0.0) is None

    def test_a_report_publishes_the_estimate_and_the_station_s_name(self) -> None:
        answer = session_response(
            uuid4(),
            STATE,
            READY,
            cost_eur=0.03,
            startup_estimate_s=None,
            now=T0,
            zone=UTC,
            station_name="Radio Alex",
            estimate=CostEstimate(eur=0.3, seconds=1800.0),
        )
        assert (answer.station_name, answer.cost_estimate_eur, answer.cost_estimate_s) == (
            "Radio Alex",
            0.3,
            1800.0,
        )


def test_a_news_source_names_its_article_and_a_record_names_nothing() -> None:
    """The page opens a story's article from its source; the person's own record
    stays a family name — never an id the page could follow."""
    state = replace(STATE, produced=frozenset({1, 2, 3}))
    answer = session_response(
        uuid4(), state, READY, cost_eur=None, startup_estimate_s=None, now=T0, zone=UTC
    )
    [agenda] = answer.segments[1].transcript[0].sources
    [news] = answer.segments[2].transcript[0].sources
    assert news.article_id == "story-1"
    assert agenda.article_id is None


class TestTheFlash:
    """ADR-324 decision 32: a flash waiting to be heard is published apart from the order."""

    SEQ = 100_001

    def state(self, *, produced: bool = True) -> SessionState:
        return replace(
            STATE,
            produced=frozenset({1, 2}),
            playhead=Playhead(seq=1, position_s=4.0, reported_at=T0),
            flashes=(Flash(seq=self.SEQ, notes=("m1",), produced=produced),),
        )

    def answer(self, state: SessionState) -> RadioSessionResponse:
        ready = {**READY, self.SEQ: segment("From the chat")}
        return session_response(
            uuid4(), state, ready, cost_eur=None, startup_estimate_s=None, now=T0, zone=UTC
        )

    def test_a_produced_flash_is_published_to_cut_the_programme_never_queued(self) -> None:
        answer = self.answer(self.state())
        assert answer.flash is not None
        assert (answer.flash.seq, answer.flash.format, answer.flash.title) == (
            self.SEQ,
            RadioFormat.FLASH,
            "From the chat",
        )
        assert answer.flash.mood is None  # the programme's music carries on under it
        assert self.SEQ not in [s.seq for s in answer.segments]
        assert [s.seq for s in answer.segments] == [1, 2]

    def test_the_audio_read_for_an_answer_includes_the_waiting_flash(self) -> None:
        """The answer is built from what the store hands back for these places:
        a flash left out would never be published."""
        assert pending_seqs(self.state()) == [1, 2, self.SEQ]
        assert pending_seqs(self.state(produced=False)) == [1, 2]

    def test_a_flash_still_in_production_or_heard_is_not_published(self) -> None:
        assert self.answer(self.state(produced=False)).flash is None
        assert self.answer(replace(self.state(), flashes=())).flash is None

    def test_what_a_flash_produced_counts_as_radio_in_the_estimate(self) -> None:
        slots = tuple(replace(slot, duration_s=60.0) for slot in SLOTS[:2])
        state = replace(
            STATE, slots=slots, produced=frozenset({1, 2}), planned_s=1800.0, flash_audio_s=30.0
        )
        estimate = cost_estimate(state, 0.03, min_audio_s=120.0)
        assert estimate is not None
        assert (estimate.eur, estimate.seconds) == (pytest.approx(0.36), 1800.0)


def test_the_player_is_told_the_music_between_two_programmes() -> None:
    """ADR-324 decision 36: the player waits as long as every projection leaves."""
    answer = session_response(
        uuid4(),
        replace(STATE, gap_s=5.0),
        READY,
        cost_eur=None,
        startup_estimate_s=None,
        now=T0,
        zone=UTC,
    )
    assert answer.segment_gap_s == 5.0
