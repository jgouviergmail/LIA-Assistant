"""The session's shapes survive Redis: every field back, through real JSON."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.domains.radio.aired import HeardLine
from src.domains.radio.codec import (
    playhead_to_dict,
    segment_from_dict,
    segment_to_dict,
    slot_from_dict,
    slot_to_dict,
    state_from_dict,
    state_to_dict,
)
from src.domains.radio.facts import SourceRef
from src.domains.radio.flash import Flash
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.grid import AiredSegment
from src.domains.radio.pacing import Playhead
from src.domains.radio.production import ProducedSegment, TranscriptLine
from src.domains.radio.programme import Slot
from src.domains.radio.session import EndReason, SessionState

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 26, 8, 50, 12, 345_000, tzinfo=UTC)


def through_json[T](payload: T) -> T:
    loaded: T = json.loads(json.dumps(payload))
    return loaded


def full_state() -> SessionState:
    """A state where no field holds its default."""
    return SessionState(
        started_at=T0,
        stop_at=T0 + timedelta(minutes=30),
        slots=(
            Slot(
                seq=1,
                format=RadioFormat.OPENING,
                station_id=True,
                air_at=T0 + timedelta(seconds=14.5),
                duration_s=24.8,
                reported=True,
            ),
            Slot(
                seq=2,
                format=RadioFormat.BULLETIN,
                station_id=False,
                air_at=T0 + timedelta(seconds=40),
                duration_s=180.0,
                clock_mark=T0 + timedelta(minutes=10),
            ),
        ),
        produced=frozenset({1}),
        in_production=frozenset({2}),
        playhead=Playhead(
            seq=1, position_s=3.25, reported_at=T0, playing=False, paused=True, flash_heard=100_001
        ),
        paused_since=T0 + timedelta(seconds=20),
        failures=2,
        ended=EndReason.LISTENER,
        failed=(
            AiredSegment(RadioFormat.ANALYSIS, T0 + timedelta(minutes=5)),
            AiredSegment(RadioFormat.BRIEF, T0 + timedelta(minutes=7)),
        ),
        planned_s=1800.0,
        flashes=(
            Flash(seq=100_002, notes=("m2", "m3"), produced=True),
            Flash(seq=100_003, notes=("m4",)),
        ),
        flash_since=T0 + timedelta(minutes=12),
        flashes_made=3,
        flash_audio_s=41.5,
        gap_s=5.0,
    )


def test_a_state_comes_back_whole() -> None:
    state = full_state()
    assert state_from_dict(through_json(state_to_dict(state))) == state


def test_a_new_state_comes_back_whole() -> None:
    state = SessionState(started_at=T0, stop_at=None)
    assert state_from_dict(through_json(state_to_dict(state))) == state


def test_a_state_stored_before_the_rest_and_the_pause_flag_is_still_read() -> None:
    """A session live across a deploy is picked up by a worker running the new code."""
    stored = through_json(state_to_dict(full_state()))
    del stored["failed"]
    del stored["planned_s"]
    for flash_field in ("flashes", "flash_since", "flashes_made", "flash_audio_s"):
        del stored[flash_field]
    playhead = stored["playhead"]
    assert isinstance(playhead, dict)
    del playhead["paused"]
    del playhead["flash_heard"]
    read = state_from_dict(stored)
    assert read.failed == ()
    assert read.playhead is not None and read.playhead.paused is False
    assert read.playhead.flash_heard == 0
    assert (read.flashes, read.flash_since, read.flashes_made, read.flash_audio_s) == (
        (),
        None,
        0,
        0.0,
    )
    # A timer with no plan recorded: `view.cost_estimate` prices nothing for it.
    assert read.planned_s is None and read.stop_at is not None


def test_a_programme_of_the_former_menu_reads_as_the_journal_in_a_live_session() -> None:
    """A session live across the deploy of ADR-324 decision 41 goes on: a slot or a failure
    of « your day », « for you » or the recap is read as the journal — the grid then knows
    the edition's journal aired, or rests — and a format nobody knows is still refused."""
    stored = through_json(state_to_dict(full_state()))
    stored["slots"][1]["format"] = "my_day"
    stored["failed"] = [{"format": "recap", "at": T0.isoformat()}]
    read = state_from_dict(stored)
    assert read.slots[1].format is RadioFormat.JOURNAL
    assert read.failed == (AiredSegment(RadioFormat.JOURNAL, T0),)
    stored["slots"][1]["format"] = "weather_forecast"
    with pytest.raises(ValueError):
        state_from_dict(stored)


def test_a_zone_that_is_not_utc_comes_back_as_the_same_instant() -> None:
    paris = datetime(2026, 9, 26, 10, 50, tzinfo=UTC).astimezone()
    slot = Slot(seq=1, format=RadioFormat.OPENING, station_id=True, air_at=paris, duration_s=1.0)
    assert slot_from_dict(through_json(slot_to_dict(slot))).air_at == paris


def full_state_to_dict_flash() -> dict[str, object]:
    flashes = state_to_dict(full_state())["flashes"]
    assert isinstance(flashes, list)
    first: dict[str, object] = flashes[0]
    return first


@pytest.mark.parametrize(
    ("shape", "encoded", "exempt"),
    [
        (SessionState, state_to_dict(full_state()), set()),
        (Slot, slot_to_dict(full_state().slots[1]), set()),
        (Playhead, playhead_to_dict(Playhead(seq=1, position_s=0.0, reported_at=T0)), set()),
        (Flash, full_state_to_dict_flash(), set()),
    ],
)
def test_every_field_is_written(shape: type, encoded: dict[str, object], exempt: set[str]) -> None:
    """A field added to a shape and forgotten here would be lost at the next restart."""
    assert set(encoded) == {field.name for field in fields(shape)} - exempt


def produced_segment(audio: Path) -> ProducedSegment:
    return ProducedSegment(
        title="The nine o'clock news",
        audio_path=audio,
        duration_s=182.4,
        transcript=(
            TranscriptLine(
                role=RadioRole.ANCHOR,
                text="Good morning.",
                offset_s=4.2,
                sources=(),
            ),
            TranscriptLine(
                role=RadioRole.ANCHOR,
                text="Rain is expected over the capital.",
                offset_s=7.9,
                sources=(
                    SourceRef(
                        label="Example Outlet",
                        url="https://news.example/rain",
                        published_at=T0 - timedelta(hours=2),
                        story_key="example-rain-capital",
                    ),
                    SourceRef(label="Agenda", record_kind="event", record_id="evt-17"),
                ),
            ),
        ),
        dropped_lines=1,
        unrendered=("whisper",),
        memory=(
            HeardLine(offset_s=4.2),
            HeardLine(
                offset_s=7.9,
                personal=frozenset({"event:evt-17"}),
                news=frozenset({"7c0b6a9e", "7c0b6a9e#a1"}),
                stories=frozenset({"rain over the capital"}),
                headlines=("Rain expected over the capital", "The capital braces"),
                angle=RadioFormat.DEBATE,
            ),
        ),
    )


def test_a_segment_comes_back_whole_with_its_audio_where_the_caller_puts_it(
    tmp_path: Path,
) -> None:
    segment = produced_segment(Path("/elsewhere/0002.mp3"))
    encoded = through_json(segment_to_dict(segment))
    assert "audio_path" not in json.dumps(encoded)
    assert "elsewhere" not in json.dumps(encoded)
    here = tmp_path / "0002.mp3"
    assert segment_from_dict(encoded, audio_path=here) == produced_segment(here)


def test_every_segment_field_but_its_path_is_written() -> None:
    encoded = segment_to_dict(produced_segment(Path("0001.mp3")))
    assert set(encoded) == {field.name for field in fields(ProducedSegment)} - {"audio_path"}
    line = encoded["transcript"][0]
    assert isinstance(line, dict)
    assert set(line) == {field.name for field in fields(TranscriptLine)}
    heard = encoded["memory"][1]
    assert isinstance(heard, dict)
    assert set(heard) == {field.name for field in fields(HeardLine)}


def test_a_line_filed_under_an_angle_this_release_does_not_know_is_filed_under_none() -> None:
    """Read forgivingly: a programme retired since, or a line written before angles."""
    encoded = through_json(segment_to_dict(produced_segment(Path("0001.mp3"))))
    encoded["memory"][1]["angle"] = "retired_programme"
    del encoded["memory"][0]["angle"]
    memory = segment_from_dict(encoded, audio_path=Path("0001.mp3")).memory
    assert [line.angle for line in memory] == [None, None]


def test_a_segment_published_before_it_remembered_its_lines_reads_as_remembering_none() -> None:
    """A segment published by the previous release, read by a restarted loop."""
    encoded = through_json(segment_to_dict(produced_segment(Path("0001.mp3"))))
    del encoded["memory"]
    assert segment_from_dict(encoded, audio_path=Path("0001.mp3")).memory == ()


def test_a_state_published_before_the_pause_existed_chains_its_programmes() -> None:
    """A state a previous release published reads with no pause between programmes."""
    encoded = through_json(state_to_dict(full_state()))
    del encoded["gap_s"]
    assert state_from_dict(encoded).gap_s == 0.0
