"""Fish Audio dialogue: several voices in one request, timed word by word (ADR-345).

One request voices a whole exchange: the text opens every turn with
``<|speaker:N|>`` and ``reference_id`` lists one voice per speaker, the first
named ``speaker:0`` (vendor documentation, measured on ``s2.1-pro-free``
2026-10-14). ``POST /v1/tts/stream/with-timestamp`` answers Server-Sent Events,
each with a base64 audio chunk and the LATEST timing snapshot of one text chunk
(``chunk_seq``): a snapshot replaces the previous one for its chunk, and its
segment times add to ``chunk_audio_offset_sec``.

Where each turn starts is read from that timing. Measured on French and Chinese
dialogues: a segment is a word (a character in Chinese), digits stay digits,
punctuation and cues are absent, an apostrophe stays inside its word and a
hyphen splits two — so the LETTERS AND DIGITS of the turns, in order, are
exactly those of the segments. A turn starts at the segment holding its first
letter. When the two sequences differ, nothing is guessed: the dialogue is
reported unplaced and its caller voices the lines one by one.
"""

from __future__ import annotations

import base64
import binascii
import itertools
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.protocol import DialogueTurn

#: Where a timed dialogue is streamed.
DIALOGUE_PATH: Final[str] = "/v1/tts/stream/with-timestamp"
_DATA_PREFIX: Final[str] = "data:"


def compose_dialogue(turns: Sequence[DialogueTurn]) -> tuple[str, list[str]]:
    """The request text and its voices: each distinct voice once, in order of entry.

    Args:
        turns: The turns, in order.

    Returns:
        The text (every turn opened by its speaker marker) and the voice ids,
        the n-th one speaking ``<|speaker:n|>``.
    """
    voices: list[str] = []
    parts: list[str] = []
    for turn in turns:
        if turn.voice not in voices:
            voices.append(turn.voice)
        spoken = f"{turn.cue} {turn.words}" if turn.cue else turn.words
        parts.append(f"<|speaker:{voices.index(turn.voice)}|>{spoken}")
    return "".join(parts), voices


@dataclass(frozen=True, slots=True)
class TimedWord:
    """One timed segment of the dialogue's audio.

    Attributes:
        text: The segment as the vendor spells it (a word, a character).
        start_s: Its start on the whole dialogue's timeline.
    """

    text: str
    start_s: float


def _invalid(reason: str) -> TTSProviderError:
    return TTSProviderError(
        code="provider_invalid_response",
        message="Fish Audio dialogue stream is malformed",
        details={"reason": reason},
    )


class TimestampedStream:
    """The audio and the latest timing of every text chunk of one SSE answer."""

    def __init__(self) -> None:
        self._audio = bytearray()
        self._snapshots: dict[int, tuple[float, list[TimedWord]]] = {}

    def feed(self, line: str) -> None:
        """Read one line of the stream; anything but a ``data:`` line is framing.

        Raises:
            TTSProviderError: When an event is not the documented JSON.
        """
        if not line.startswith(_DATA_PREFIX):
            return
        try:
            event = json.loads(line[len(_DATA_PREFIX) :])
            chunk = base64.b64decode(event.get("audio_base64") or "", validate=True)
        except ValueError, TypeError, AttributeError, binascii.Error:
            raise _invalid("event") from None
        self._audio.extend(chunk)
        alignment = event.get("alignment")
        if alignment is not None:
            self._snapshots[_int(event.get("chunk_seq"))] = (
                _seconds(event.get("chunk_audio_offset_sec")),
                _segments(alignment),
            )

    @property
    def audio(self) -> bytes:
        """Every audio chunk, in arrival order."""
        return bytes(self._audio)

    def timeline(self) -> list[TimedWord]:
        """Every timed segment on the whole dialogue's timeline, in order."""
        return [
            TimedWord(word.text, offset + word.start_s)
            for _, (offset, words) in sorted(self._snapshots.items())
            for word in words
        ]


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid("chunk_seq")
    return value


def _seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise _invalid("time")
    return float(value)


def _segments(alignment: object) -> list[TimedWord]:
    segments = alignment.get("segments") if isinstance(alignment, dict) else None
    if not isinstance(segments, list):
        raise _invalid("alignment")
    words: list[TimedWord] = []
    for segment in segments:
        text = segment.get("text") if isinstance(segment, dict) else None
        if not isinstance(text, str):
            raise _invalid("segment")
        words.append(TimedWord(text, _seconds(segment.get("start"))))
    return words


def _letters(text: str) -> str:
    """The letters and digits of ``text``, case folded — what the timing spells."""
    return "".join(character for character in text.casefold() if character.isalnum())


def turn_starts(
    turn_words: Sequence[str], timeline: Sequence[TimedWord]
) -> tuple[float, ...] | None:
    """When each turn starts, read exactly from the timing — or ``None``.

    Args:
        turn_words: What each turn says, in order (no marker, no cue).
        timeline: The timed segments of the whole dialogue.

    Returns:
        Each turn's start in seconds, strictly increasing; ``None`` when a turn
        has nothing to time or the timing does not spell the turns' words.
    """
    expected = [_letters(words) for words in turn_words]
    if not expected or not all(expected):
        return None
    spelled = [_letters(word.text) for word in timeline]
    if "".join(expected) != "".join(spelled):
        return None
    owner = [index for index, letters in enumerate(spelled) for _ in letters]
    boundaries = itertools.accumulate((len(letters) for letters in expected[:-1]), initial=0)
    starts = tuple(timeline[owner[position]].start_s for position in boundaries)
    if any(later <= earlier for earlier, later in itertools.pairwise(starts)):
        return None
    return starts


__all__ = [
    "DIALOGUE_PATH",
    "TimedWord",
    "TimestampedStream",
    "compose_dialogue",
    "turn_starts",
]
