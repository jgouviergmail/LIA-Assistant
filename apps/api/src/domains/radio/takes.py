"""Which lines of a segment are voiced together, as one dialogue take (ADR-345).

An engine that voices several speakers in one request
(:func:`~src.domains.voice.families.voices_dialogue`) speaks a multi-voice
segment by TAKES: consecutive lines of one part that share their per-call
controls (one request carries one speaking rate), up to
``RADIO_DIALOGUE_MAX_BYTES`` of text — so the voices answer each other as in
one recording, a failure costs one take and never a whole debate, and the takes
are voiced in parallel like lines. A line too long for any take, or with
nothing to say, is voiced alone; so is every line of a segment one voice reads,
which holds no dialogue to keep.

Pure: no client, no file — the production voices what this plans.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.domains.radio.script import ScriptPart
from src.domains.voice.sentence_streamer import is_speakable


@dataclass(frozen=True, slots=True)
class TakeLine:
    """What the planner reads of one line.

    Attributes:
        part: The script part the line belongs to.
        voice: The voice that speaks it.
        spoken: What a take carries for it (its cue and its words).
        controls: Its per-call delivery controls.
    """

    part: ScriptPart
    voice: str
    spoken: str
    controls: Mapping[str, object]


def plan_takes(lines: Sequence[TakeLine], *, max_bytes: int) -> list[tuple[int, ...]]:
    """Group a segment's lines into takes, in script order.

    Args:
        lines: The segment's lines, in script order.
        max_bytes: The most UTF-8 bytes one take carries; ``0`` voices every
            line alone.

    Returns:
        The takes, each the indices of its lines — every line in exactly one,
        in order.
    """
    if max_bytes <= 0 or len({line.voice for line in lines}) < 2:
        return [(index,) for index in range(len(lines))]
    takes: list[list[int]] = []
    size = 0
    for index, line in enumerate(lines):
        cost = len(line.spoken.encode("utf-8"))
        if takes and size + cost <= max_bytes and _joins(lines[takes[-1][0]], line):
            takes[-1].append(index)
            size += cost
        else:
            takes.append([index])
            size = cost
    return [tuple(take) for take in takes]


def _joins(opening: TakeLine, line: TakeLine) -> bool:
    """Whether ``line`` may follow in the take ``opening`` started."""
    return (
        opening.part is line.part
        and opening.controls == line.controls
        and is_speakable(opening.spoken)
        and is_speakable(line.spoken)
    )


__all__ = ["TakeLine", "plan_takes"]
