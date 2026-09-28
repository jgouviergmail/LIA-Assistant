"""What a report is answered: the session as the player shows it.

Pure: the state the loop published, the segments it published, the cost the
ledger holds — in; the wire shape — out.

- The status: ``ended`` once the loop ended it; ``ending`` once the sign-off is
  in the running order (the timer's farewell is on its way); ``starting`` while
  nothing is ready; ``on_air`` otherwise.
- The segments: every ready one from the segment the player is playing (or
  expects) on — the rest it has already heard. An ended session keeps listing
  what is left, so a player finishes the farewell it was promised.
- A line's sources: an outlet's name, an article's link and date; a record of
  the person's is named by its family, and its id never leaves the server.
- The music: every segment names the mood the player plays under it (its
  programme and the listener's hour), and the session the mood of what airs
  next — the listener's hour alone before anything is planned. A clock nobody
  knows (the session is no longer the account's) names none.
- The station's name, frozen in the session's setup, and what the planned
  listening will cost at the session's own rate — once enough radio was
  produced, while the session still has listening ahead.
- A news flash waiting to be heard, apart from the segments: the player cuts
  the programme for it (ADR-324 decision 32). It names no music: the
  programme's carries on under it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, tzinfo
from uuid import UUID

from src.domains.radio.constants import ESTIMATE_OPEN_ENDED_SECONDS
from src.domains.radio.flash import pending_flash
from src.domains.radio.formats import MusicMood, RadioFormat, daypart_mood, music_mood
from src.domains.radio.production import ProducedSegment
from src.domains.radio.programme import Slot
from src.domains.radio.schemas import (
    RadioSegmentResponse,
    RadioSessionResponse,
    RadioSessionStatus,
    RadioSourceResponse,
    RadioTranscriptLineResponse,
)
from src.domains.radio.session import SessionState, effective_stop_at


def session_status(state: SessionState) -> RadioSessionStatus:
    """Where a session stands, for the player."""
    if state.ended is not None:
        return "ended"
    if any(slot.format is RadioFormat.SIGN_OFF for slot in state.slots):
        return "ending"
    return "on_air" if state.produced else "starting"


def pending_seqs(state: SessionState) -> list[int]:
    """The ready segments the player has not finished, ascending — a flash waiting last."""
    floor = state.playhead.seq if state.playhead is not None else 1
    waiting = pending_flash(state)
    flashes = [waiting.seq] if waiting is not None else []
    return [*sorted(seq for seq in state.produced if seq >= floor), *flashes]


def _mood(slot: Slot, zone: tzinfo | None) -> MusicMood | None:
    return None if zone is None else music_mood(slot.format, slot.air_at.astimezone(zone))


def _session_mood(state: SessionState, zone: tzinfo | None) -> MusicMood | None:
    """The music of what airs next — the listener's hour alone before anything is planned."""
    if zone is None:
        return None
    floor = state.playhead.seq if state.playhead is not None else 1
    upcoming = next((slot for slot in state.slots if slot.seq >= floor), None)
    if upcoming is not None:
        return _mood(upcoming, zone)
    moment = state.playhead.reported_at if state.playhead is not None else state.started_at
    return daypart_mood(moment.astimezone(zone))


def _segment(slot: Slot, segment: ProducedSegment, zone: tzinfo | None) -> RadioSegmentResponse:
    return _wire(slot.seq, slot.format, _mood(slot, zone), segment)


def _flash(
    state: SessionState, segments: Mapping[int, ProducedSegment]
) -> RadioSegmentResponse | None:
    """The flash the player must air now, if one is ready and published."""
    waiting = pending_flash(state)
    if waiting is None or waiting.seq not in segments:
        return None
    return _wire(waiting.seq, RadioFormat.FLASH, None, segments[waiting.seq])


def _wire(
    seq: int, fmt: RadioFormat, mood: MusicMood | None, segment: ProducedSegment
) -> RadioSegmentResponse:
    return RadioSegmentResponse(
        seq=seq,
        format=fmt,
        mood=mood,
        title=segment.title,
        duration_s=segment.duration_s,
        transcript=[
            RadioTranscriptLineResponse(
                role=line.role,
                text=line.text,
                offset_s=line.offset_s,
                sources=[
                    RadioSourceResponse(
                        label=source.label,
                        url=source.url,
                        published_at=source.published_at,
                        article_id=source.story_key,
                    )
                    for source in line.sources
                ],
            )
            for line in segment.transcript
        ],
    )


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """What a session's planned listening will cost, estimated.

    Attributes:
        eur: The estimate, in euros.
        seconds: The listening it covers: the timer's, else an hour.
    """

    eur: float
    seconds: float


def cost_estimate(
    state: SessionState, cost_eur: float | None, *, min_audio_s: float
) -> CostEstimate | None:
    """The planned listening, priced at what a second of radio has cost so far.

    The spend follows what is produced — writing, checking and voicing a
    programme — and production follows the listening, so the session's own
    rate prices the rest of it in whatever models and voices it runs on.

    Args:
        state: The session.
        cost_eur: What it has cost so far; None when unknown.
        min_audio_s: The radio produced before a rate is worth extrapolating.

    Returns:
        The estimate; None before enough radio was produced, with no cost, once
        the session's end is decided (the listening it planned will not
        happen), or for a timer no plan was recorded for (a session stored
        before the plan was: an hour would misprice it).
    """
    if cost_eur is None or state.ended is not None:
        return None
    if state.planned_s is None and state.stop_at is not None:
        return None
    produced_s = state.flash_audio_s + sum(
        slot.duration_s for slot in state.slots if slot.seq in state.produced
    )
    if produced_s <= 0 or produced_s < min_audio_s:
        return None
    seconds = state.planned_s if state.planned_s is not None else ESTIMATE_OPEN_ENDED_SECONDS
    return CostEstimate(eur=cost_eur / produced_s * seconds, seconds=seconds)


def session_response(
    session_id: UUID,
    state: SessionState,
    segments: Mapping[int, ProducedSegment],
    *,
    cost_eur: float | None,
    startup_estimate_s: float | None,
    now: datetime,
    zone: tzinfo | None,
    station_name: str | None = None,
    estimate: CostEstimate | None = None,
) -> RadioSessionResponse:
    """The session as a report is answered.

    Args:
        session_id: The session.
        state: The state the loop published.
        segments: The published segments (a missing one is not listed).
        cost_eur: What the session has cost so far, or None when unknown.
        startup_estimate_s: The start's estimate of the first voice.
        now: The instant of the answer — a pause in progress moves the stop.
        zone: The listener's timezone (the music follows their day), or None
            when the session is no longer the account's.
        station_name: The station's name, as its host says it; None when unknown.
        estimate: What its planned listening will cost; None when not estimated yet.

    Returns:
        The wire shape.
    """
    slots = {slot.seq: slot for slot in state.slots}
    return RadioSessionResponse(
        session_id=session_id,
        status=session_status(state),
        segments=[
            _segment(slots[seq], segments[seq], zone)
            for seq in pending_seqs(state)
            if seq in segments and seq in slots
        ],
        cost_eur=cost_eur,
        stop_at=effective_stop_at(state, now),
        startup_estimate_s=startup_estimate_s,
        end_reason=state.ended.value if state.ended else None,
        mood=_session_mood(state, zone),
        station_name=station_name,
        cost_estimate_eur=estimate.eur if estimate is not None else None,
        cost_estimate_s=estimate.seconds if estimate is not None else None,
        segment_gap_s=state.gap_s,
        flash=_flash(state, segments),
    )


__all__ = [
    "CostEstimate",
    "cost_estimate",
    "pending_seqs",
    "session_response",
    "session_status",
]
