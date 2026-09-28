"""A segment's audio: the voiced lines alone, joined and loudness-normalised.

The station's music is the PLAYER's (ADR-324, decision 28): it plays under the
whole session from the click to the farewell and is lowered under the voices, so
a segment carries no music of its own — it would play twice. A segment opens on
a short breath (the time the player takes to lower the music before the first
word), pauses after every line, a little longer where one part gives way to the
next (intro, body, outro), and ends on a short tail.

Two halves, so the first can be tested without ffmpeg (absent on the CI
runners, measured 2026-09-26): :func:`plan_segment` is PURE — it computes the
filter graph, the output's duration and where each line starts in it (the
transcript follows the voice with those offsets); and :func:`assemble_segment`
probes the inputs, runs the plan through the bounded subprocess runner and
moves the result into place atomically.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from src.domains.radio.script import ScriptPart
from src.infrastructure.media.ffmpeg import FfmpegError, probe_duration, run_ffmpeg

#: How many ffprobe processes one assembly runs at once (a Pi has four cores).
_PROBE_CONCURRENCY: Final[int] = 4
#: The loudness every segment is normalised to (a streaming-radio target).
_LOUDNESS: Final[str] = "loudnorm=I=-16:TP=-1.5:LRA=11"


class AudioAssemblyError(RuntimeError):
    """A segment could not be assembled (a probe or the mix failed)."""


@dataclass(frozen=True, slots=True)
class MixParams:
    """The segment's pauses and encoding.

    Attributes:
        lead_in_s: Silence before the first word — the player lowers the
            station's music over it (its attack must stay shorter).
        line_gap_s: Silence after each line.
        part_gap_s: Extra silence where one part gives way to the next.
        tail_s: Silence after the last word.
        bitrate_kbps: MP3 bitrate of the output (mono).
        sample_rate: Output sample rate.
    """

    lead_in_s: float = 0.5
    line_gap_s: float = 0.35
    part_gap_s: float = 0.4
    tail_s: float = 0.4
    bitrate_kbps: int = 64
    sample_rate: int = 44100

    def __post_init__(self) -> None:
        if self.lead_in_s <= 0:
            raise ValueError("the music needs a pause to lower before the first word")
        if min(self.line_gap_s, self.part_gap_s, self.tail_s) < 0:
            raise ValueError("a pause cannot be negative")


@dataclass(frozen=True, slots=True)
class VoicedLine:
    """One synthesised line, ready to mix."""

    part: ScriptPart
    path: Path
    duration_s: float


@dataclass(frozen=True, slots=True)
class AssemblyPlan:
    """What ffmpeg is asked, and what the result will look like.

    Attributes:
        args: The ffmpeg arguments (after the runner's quiet flags).
        duration_s: The output's expected duration.
        line_offsets_s: When each line starts in the output, in the order given.
    """

    args: tuple[str, ...]
    duration_s: float
    line_offsets_s: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class AssembledAudio:
    """The finished segment's measured duration and its lines' start times."""

    duration_s: float
    line_offsets_s: tuple[float, ...]


def _n(value: float) -> str:
    return f"{value:.3f}"


def _pause_after(lines: Sequence[VoicedLine], index: int, params: MixParams) -> float:
    """The silence after line ``index``: the tail, a line gap, or a breath between parts."""
    if index + 1 == len(lines):
        return params.tail_s
    if lines[index + 1].part is lines[index].part:
        return params.line_gap_s
    return params.line_gap_s + params.part_gap_s


def plan_segment(
    lines: Sequence[VoicedLine],
    out: Path,
    params: MixParams | None = None,
) -> AssemblyPlan:
    """Compute the mix of one segment — pure, no file is touched.

    Args:
        lines: The voiced lines, intro first, body, outro last (the verifier's order).
        out: Where the MP3 is written.
        params: Pauses and encoding.

    Returns:
        The ffmpeg arguments, the expected duration and each line's start.

    Raises:
        ValueError: When no line is in the body (a segment is its body).
    """
    p = params or MixParams()
    if not any(line.part is ScriptPart.BODY for line in lines):
        raise ValueError("a segment without a body has nothing to carry")
    fmt = f"aresample={p.sample_rate},aformat=sample_fmts=fltp:channel_layouts=mono"
    filters: list[str] = []
    offsets: list[float] = []
    clock = p.lead_in_s
    for index, line in enumerate(lines):
        pause = _pause_after(lines, index, p)
        filters.append(f"[{index}:a]{fmt},apad=pad_dur={_n(pause)}[l{index}]")
        offsets.append(round(clock, 3))
        clock += line.duration_s + pause
    labels = "".join(f"[l{index}]" for index in range(len(lines)))
    filters.append(
        f"{labels}concat=n={len(lines)}:v=0:a=1,"
        f"adelay=delays={round(p.lead_in_s * 1000)}:all=1,{_LOUDNESS},aresample={p.sample_rate}[out]"
    )
    args: list[str] = []
    for line in lines:
        args += ["-i", str(line.path)]
    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-ac",
        "1",
        "-ar",
        str(p.sample_rate),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{p.bitrate_kbps}k",
        "-f",
        "mp3",
        str(out),
    ]
    return AssemblyPlan(args=tuple(args), duration_s=round(clock, 3), line_offsets_s=tuple(offsets))


async def _durations(paths: Sequence[Path], timeout_s: float) -> list[float]:
    """Probe every file; the first failure cancels and reaps the others.

    A ``TaskGroup``, never ``gather``: gather would leave the sibling probes
    running when one fails, with no owner to await them.
    """
    gate = asyncio.Semaphore(_PROBE_CONCURRENCY)

    async def one(path: Path) -> float:
        async with gate:
            return await probe_duration(path, timeout_s=timeout_s)

    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(path)) for path in paths]
    except* FfmpegError as failures:
        raise failures.exceptions[0] from None
    return [task.result() for task in tasks]


async def assemble_segment(
    lines: Sequence[tuple[ScriptPart, Path]],
    out: Path,
    *,
    timeout_s: float,
    params: MixParams | None = None,
) -> AssembledAudio:
    """Join a segment's voiced lines into ``out`` (atomically).

    Args:
        lines: ``(part, audio file)`` per verified line, in script order.
        out: The MP3 to produce; written to a sibling temporary file first and
            moved into place only when complete, so a reader never sees half.
        timeout_s: Ceiling for each probe and for the mix.
        params: Pauses and encoding.

    Returns:
        The measured duration and each line's start in the output.

    Raises:
        AudioAssemblyError: When a probe or the mix fails.
    """
    partial = out.with_name(f"{out.stem}.part.mp3")
    try:
        durations = await _durations([path for _, path in lines], timeout_s)
        voiced = [
            VoicedLine(part, path, duration)
            for (part, path), duration in zip(lines, durations, strict=True)
        ]
        plan = plan_segment(voiced, partial, params)
        await run_ffmpeg(plan.args, timeout_s=timeout_s)
        os.replace(partial, out)
        measured = await probe_duration(out, timeout_s=timeout_s)
    except (FfmpegError, ValueError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise AudioAssemblyError(f"segment assembly failed: {type(exc).__name__}") from exc
    return AssembledAudio(duration_s=measured, line_offsets_s=plan.line_offsets_s)


__all__ = [
    "AssembledAudio",
    "AssemblyPlan",
    "AudioAssemblyError",
    "MixParams",
    "VoicedLine",
    "assemble_segment",
    "plan_segment",
]
