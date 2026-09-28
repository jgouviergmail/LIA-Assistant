"""A session's shapes as they travel through Redis: JSON both ways, nothing lost.

A session outlives the worker that started it — the loop is picked up by
whichever worker next hears the player — so what it remembers is written as
plain JSON and read back to the SAME values (the round-trip test holds every
field). A segment's audio is never named in the store: its path is rebuilt from
the media root, the session and the segment's place, so a value read back from
Redis can never point the file route anywhere else.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from src.domains.radio.aired import HeardLine
from src.domains.radio.facts import SourceRef
from src.domains.radio.flash import Flash
from src.domains.radio.formats import RadioFormat, RadioRole, read_format
from src.domains.radio.grid import AiredSegment
from src.domains.radio.pacing import Playhead
from src.domains.radio.production import ProducedSegment, TranscriptLine
from src.domains.radio.programme import Slot
from src.domains.radio.session import EndReason, SessionState


def _instant(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _read_instant(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _stored_format(value: Any) -> RadioFormat:
    """A slot's or a failure's format as stored.

    A programme the journal replaced reads as the journal (ADR-324 decision 41): the
    grid then knows the edition had its journal, or that it rests. A format nobody
    knows is a snapshot this release cannot read.

    Raises:
        ValueError: On a format neither current nor replaced.
    """
    fmt = read_format(value)
    if fmt is None:
        raise ValueError(f"a stored session names a radio format nobody knows: {value!r}")
    return fmt


def slot_to_dict(slot: Slot) -> dict[str, Any]:
    """One slot as stored."""
    return {
        "seq": slot.seq,
        "format": slot.format.value,
        "station_id": slot.station_id,
        "air_at": slot.air_at.isoformat(),
        "duration_s": slot.duration_s,
        "reported": slot.reported,
        "clock_mark": _instant(slot.clock_mark),
    }


def slot_from_dict(payload: Mapping[str, Any]) -> Slot:
    """One slot as read."""
    return Slot(
        seq=int(payload["seq"]),
        format=_stored_format(payload["format"]),
        station_id=bool(payload["station_id"]),
        air_at=datetime.fromisoformat(str(payload["air_at"])),
        duration_s=float(payload["duration_s"]),
        reported=bool(payload["reported"]),
        clock_mark=_read_instant(payload.get("clock_mark")),
    )


def playhead_to_dict(playhead: Playhead) -> dict[str, Any]:
    """The player's report as stored."""
    return {
        "seq": playhead.seq,
        "position_s": playhead.position_s,
        "reported_at": playhead.reported_at.isoformat(),
        "playing": playhead.playing,
        "paused": playhead.paused,
        "flash_heard": playhead.flash_heard,
    }


def playhead_from_dict(payload: Mapping[str, Any]) -> Playhead:
    """The player's report as read (one stored before ``paused`` or ``flash_heard``
    existed reads unpaused, no flash heard)."""
    return Playhead(
        seq=int(payload["seq"]),
        position_s=float(payload["position_s"]),
        reported_at=datetime.fromisoformat(str(payload["reported_at"])),
        playing=bool(payload["playing"]),
        paused=bool(payload.get("paused", False)),
        flash_heard=int(payload.get("flash_heard", 0)),
    )


def _flash_to_dict(flash: Flash) -> dict[str, Any]:
    return {"seq": flash.seq, "notes": list(flash.notes), "produced": flash.produced}


def _flash_from_dict(payload: Mapping[str, Any]) -> Flash:
    return Flash(
        seq=int(payload["seq"]),
        notes=tuple(str(note) for note in payload["notes"]),
        produced=bool(payload["produced"]),
    )


def _failure_to_dict(failure: AiredSegment) -> dict[str, Any]:
    return {"format": failure.format.value, "at": failure.air_at.isoformat()}


def _failure_from_dict(payload: Mapping[str, Any]) -> AiredSegment:
    return AiredSegment(
        _stored_format(payload["format"]), datetime.fromisoformat(str(payload["at"]))
    )


def state_to_dict(state: SessionState) -> dict[str, Any]:
    """A session's state as stored (sets as sorted lists, instants as ISO strings)."""
    return {
        "started_at": state.started_at.isoformat(),
        "stop_at": _instant(state.stop_at),
        "slots": [slot_to_dict(slot) for slot in state.slots],
        "produced": sorted(state.produced),
        "in_production": sorted(state.in_production),
        "playhead": playhead_to_dict(state.playhead) if state.playhead else None,
        "paused_since": _instant(state.paused_since),
        "failures": state.failures,
        "ended": state.ended.value if state.ended else None,
        "failed": [_failure_to_dict(failure) for failure in state.failed],
        "planned_s": state.planned_s,
        "flashes": [_flash_to_dict(flash) for flash in state.flashes],
        "flash_since": _instant(state.flash_since),
        "flashes_made": state.flashes_made,
        "flash_audio_s": state.flash_audio_s,
        "gap_s": state.gap_s,
    }


def state_from_dict(payload: Mapping[str, Any]) -> SessionState:
    """A session's state as read (one stored before ``failed``, ``planned_s`` or the
    flashes existed reads none)."""
    playhead = payload.get("playhead")
    ended = payload.get("ended")
    planned = payload.get("planned_s")
    return SessionState(
        started_at=datetime.fromisoformat(str(payload["started_at"])),
        stop_at=_read_instant(payload.get("stop_at")),
        slots=tuple(slot_from_dict(slot) for slot in payload["slots"]),
        produced=frozenset(int(seq) for seq in payload["produced"]),
        in_production=frozenset(int(seq) for seq in payload["in_production"]),
        playhead=playhead_from_dict(playhead) if playhead else None,
        paused_since=_read_instant(payload.get("paused_since")),
        failures=int(payload["failures"]),
        ended=EndReason(ended) if ended else None,
        failed=tuple(_failure_from_dict(failure) for failure in payload.get("failed", ())),
        planned_s=float(planned) if isinstance(planned, int | float) else None,
        flashes=tuple(_flash_from_dict(flash) for flash in payload.get("flashes", ())),
        flash_since=_read_instant(payload.get("flash_since")),
        flashes_made=int(payload.get("flashes_made", 0)),
        flash_audio_s=float(payload.get("flash_audio_s", 0.0)),
        # A state a release without the pause published chains its programmes.
        gap_s=float(payload.get("gap_s", 0.0)),
    )


def segment_to_dict(segment: ProducedSegment) -> dict[str, Any]:
    """A ready segment as stored — everything but where its audio lies."""
    return {
        "title": segment.title,
        "duration_s": segment.duration_s,
        "transcript": [
            {
                "role": line.role.value,
                "text": line.text,
                "offset_s": line.offset_s,
                "sources": [source.model_dump(mode="json") for source in line.sources],
            }
            for line in segment.transcript
        ],
        "dropped_lines": segment.dropped_lines,
        "unrendered": list(segment.unrendered),
        "memory": [
            {
                "offset_s": line.offset_s,
                "personal": sorted(line.personal),
                "news": sorted(line.news),
                "stories": sorted(line.stories),
                "headlines": list(line.headlines),
                "angle": line.angle.value if line.angle is not None else None,
            }
            for line in segment.memory
        ],
    }


def _angle(value: object) -> RadioFormat | None:
    """The angle a line was filed under, read forgivingly: a programme this release does
    not know (retired since), or none written, files it under none."""
    try:
        return RadioFormat(str(value)) if value is not None else None
    except ValueError:
        return None


def segment_from_dict(payload: Mapping[str, Any], *, audio_path: Path) -> ProducedSegment:
    """A ready segment as read, its audio where the caller's media root puts it."""
    return ProducedSegment(
        title=str(payload["title"]),
        audio_path=audio_path,
        duration_s=float(payload["duration_s"]),
        transcript=tuple(
            TranscriptLine(
                role=RadioRole(line["role"]),
                text=str(line["text"]),
                offset_s=float(line["offset_s"]),
                sources=tuple(SourceRef.model_validate(source) for source in line["sources"]),
            )
            for line in payload["transcript"]
        ),
        dropped_lines=int(payload["dropped_lines"]),
        unrendered=tuple(str(quality) for quality in payload["unrendered"]),
        # A segment published by a release that kept no memory remembers nothing.
        memory=tuple(
            HeardLine(
                offset_s=float(line["offset_s"]),
                personal=frozenset(str(key) for key in line["personal"]),
                news=frozenset(str(key) for key in line["news"]),
                stories=frozenset(str(story) for story in line["stories"]),
                headlines=tuple(str(title) for title in line["headlines"]),
                angle=_angle(line.get("angle")),
            )
            for line in payload.get("memory", ())
        ),
    )


__all__ = [
    "playhead_from_dict",
    "playhead_to_dict",
    "segment_from_dict",
    "segment_to_dict",
    "slot_from_dict",
    "slot_to_dict",
    "state_from_dict",
    "state_to_dict",
]
