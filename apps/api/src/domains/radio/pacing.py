"""Keeping the antenna fed: when to produce the next segment, how long a start takes.

A segment is produced ahead of the listener — written, voiced, mixed — and
aired when the one before it ends. Producing too early spends on segments a
listener who stops will never hear (every segment is billed to them); producing
too late leaves dead air. The rule sits between the two and is a pure function
of what the player last reported:

- the audio still AHEAD of the listener is the ready audio from the playing
  segment onwards, contiguous (audio after a segment still in production is not
  continuous, so it does not count), minus how far the player has gone since it
  last spoke;
- the next segment is started once that no longer covers its expected
  production time, with a safety factor and a margin (both settings).

The production time is estimated per format from stage timings (a writer call,
an analyst call for the formats that need one, the voice engine's real-time
factor with the lines voiced in parallel, the mix). The timings are measured by
the instance; this module only computes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from src.domains.radio.constants import LINE_MAX_CHARS, SPEECH_CHARS_PER_MINUTE
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat


@dataclass(frozen=True, slots=True)
class QueuedSegment:
    """A segment of the session that has not finished airing.

    Attributes:
        seq: Its place in the session.
        duration_s: Its real duration once ready, its format's target before.
        ready: Whether its audio exists.
    """

    seq: int
    duration_s: float
    ready: bool


@dataclass(frozen=True, slots=True)
class Playhead:
    """Where the listener is, as the player last reported it.

    Attributes:
        seq: The segment playing (or about to play).
        position_s: Seconds into it.
        reported_at: When the player said so (timezone-aware).
        playing: Whether a segment is being heard — False while paused, and
            while the station's music fills a wait; only then does it advance.
        paused: Whether the LISTENER paused, over a segment or over the
            music: the timer does not run meanwhile, and a pause too long
            ends the session.
        flash_heard: The highest news flash the player played to its end (0
            for none) — a flash airs outside the running order, and this is how
            the loop learns it aired. While a flash plays, ``seq`` and
            ``position_s`` stay those of the programme it cut.
    """

    seq: int
    position_s: float
    reported_at: datetime
    playing: bool = True
    paused: bool = False
    flash_heard: int = 0

    def __post_init__(self) -> None:
        if self.reported_at.tzinfo is None:
            raise ValueError("reported_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class StageTimings:
    """How long each production stage takes on this instance.

    Attributes:
        writer_s: One writer call.
        analysis_s: One analyst call (the formats that need an analysis).
        tts_realtime_factor: Seconds of synthesis per second of audio, one
            line at a time.
        tts_concurrency: Lines voiced at once.
        mix_s: One mix.
        lateness_s: The most the session's own productions ran past this
            estimate (:func:`ran_late`): the settings are the instance's guess,
            the slots it runs are the administrator's choice, and a writer that
            thinks takes several times what one that does not takes.
    """

    writer_s: float
    analysis_s: float
    tts_realtime_factor: float
    tts_concurrency: int
    mix_s: float
    lateness_s: float = 0.0


def audio_ahead_s(queue: Sequence[QueuedSegment], playhead: Playhead, now: datetime) -> float:
    """Seconds of ready audio still ahead of the listener.

    Args:
        queue: The segments not yet finished airing, any order — the playing
            one included until the player reports the next (its position is
            counted against it).
        playhead: The player's last report.
        now: The current instant (timezone-aware).

    Returns:
        The contiguous ready audio from the playing segment, minus what the
        player has consumed since its report; never negative.
    """
    elapsed = 0.0
    if playhead.playing:
        elapsed = (now.astimezone(UTC) - playhead.reported_at.astimezone(UTC)).total_seconds()
    ready = 0.0
    for segment in sorted(queue, key=lambda s: s.seq):
        if segment.seq < playhead.seq:
            continue
        if not segment.ready:
            break
        ready += segment.duration_s
    return max(0.0, ready - playhead.position_s - max(0.0, elapsed))


def production_s(fmt: RadioFormat, timings: StageTimings, language: str) -> float:
    """The expected time to produce one segment of a format.

    Args:
        fmt: The format.
        timings: The instance's stage timings.
        language: The listener's language (sizes the longest line).

    Returns:
        Seconds from the grid's decision to a mixed segment.
    """
    spec = FORMAT_SPECS[fmt]
    audio_s = float(spec.target_seconds)
    chars_per_second = SPEECH_CHARS_PER_MINUTE.get(language, SPEECH_CHARS_PER_MINUTE["en"]) / 60
    longest_line_s = min(audio_s, LINE_MAX_CHARS / chars_per_second)
    voicing = max(
        audio_s * timings.tts_realtime_factor / max(1, timings.tts_concurrency),
        longest_line_s * timings.tts_realtime_factor,
    )
    thinking = timings.writer_s + (timings.analysis_s if spec.needs_analysis else 0.0)
    return thinking + voicing + timings.mix_s + timings.lateness_s


def ran_late(lateness_s: float, *, observed_s: float, expected_s: float) -> float:
    """What a session expects its productions to overrun, once one more has finished.

    The most a production ran past the instance's estimate so far: one late is
    evidence the next may be, and an early one proves nothing about the others.
    Measured 2026-09-27 on dev, a writer slot that thinks takes 15 to 65 s where
    the settings expect 12; replayed on the half-hour simulation, a session that
    learns the most it saw heard 10 s of music alone waiting for a programme per
    half-hour instead of 59, and one whose writer does not think produced exactly
    as before.

    Args:
        lateness_s: What the session expected its productions to overrun so far.
        observed_s: How long one production took, start to finish.
        expected_s: The instance's estimate of it (the settings alone, no lateness).

    Returns:
        The new expectation, never below the old one.
    """
    return max(lateness_s, observed_s - expected_s)


def must_produce_next(
    ahead_s: float, next_production_s: float, *, safety: float, margin_s: float
) -> bool:
    """Whether the next segment must be started now to avoid dead air.

    Args:
        ahead_s: Ready audio ahead of the listener.
        next_production_s: The next segment's expected production time.
        safety: Factor on the expectation (a slow call must not open a gap).
        margin_s: Seconds added on top.

    Returns:
        True once the audio ahead no longer covers the production.
    """
    return ahead_s <= next_production_s * safety + margin_s


__all__ = [
    "Playhead",
    "QueuedSegment",
    "StageTimings",
    "audio_ahead_s",
    "must_produce_next",
    "production_s",
    "ran_late",
]
