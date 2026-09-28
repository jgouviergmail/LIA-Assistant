"""ffmpeg and ffprobe as bounded subprocesses — one runner for every audio path.

Audio work never runs on the event loop: decoding a few minutes of speech in
memory (pydub) would freeze every SSE stream of the worker, which is exactly
what the async rules forbid. A subprocess keeps the loop free, and a TIMEOUT
keeps a wedged codec from holding a worker slot for ever — on expiry (or when
the caller is cancelled) the process is killed and both its pipes are drained
to their end, so neither a zombie nor an open pipe outlives the call.

What the caller gets back on failure is the tool's own first lines of stderr,
bounded: a codec's complaint is a fact about a file, never the person's words.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Final

#: How much of the tool's stderr a failure carries.
_STDERR_EXCERPT_CHARS: Final[int] = 300
#: How long a killed process's pipes may take to reach their end.
_REAP_TIMEOUT_S: Final[float] = 5.0


class FfmpegError(RuntimeError):
    """ffmpeg or ffprobe failed, timed out, or is not installed."""


async def _run(
    program: str,
    args: Sequence[str],
    *,
    timeout_s: float,
    input_bytes: bytes | None = None,
) -> bytes:
    try:
        proc = await asyncio.create_subprocess_exec(
            program,
            *args,
            stdin=(
                asyncio.subprocess.PIPE if input_bytes is not None else asyncio.subprocess.DEVNULL
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise FfmpegError(f"{program} is not installed") from exc
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(input_bytes), timeout=timeout_s)
    except BaseException as exc:
        # A timeout AND a cancellation (the caller's task stopped) must leave
        # neither the process running nor its pipes open.
        await _reap(proc)
        if isinstance(exc, TimeoutError):
            raise FfmpegError(f"{program} timed out after {timeout_s:.0f}s") from exc
        raise
    if proc.returncode != 0:
        excerpt = stderr.decode(errors="replace").strip()[:_STDERR_EXCERPT_CHARS]
        raise FfmpegError(f"{program} failed (exit {proc.returncode}): {excerpt}")
    return stdout


async def _reap(proc: asyncio.subprocess.Process) -> None:
    """Kill the process and drain both pipes to their end.

    ``communicate`` closes each pipe's transport once it has read it to the end;
    a bare ``wait`` does not, and returns as soon as the process exits. Measured
    on the Windows proactor: after ``kill`` then ``wait``, a pipe was still open
    when the call returned in 3 runs of 10 after a cancellation and 6 of 10
    after a timeout — every time when the child was still writing — and it was
    reported unclosed once the loop that owned it had gone.
    """
    if proc.returncode is None:
        with suppress(ProcessLookupError):
            proc.kill()
    with suppress(TimeoutError):
        await asyncio.wait_for(proc.communicate(), timeout=_REAP_TIMEOUT_S)


async def run_ffmpeg(
    args: Sequence[str], *, timeout_s: float, input_bytes: bytes | None = None
) -> bytes:
    """Run ffmpeg quietly (``-v error -y``) and return its stdout.

    Args:
        args: Everything after the quiet flags: inputs, filters, outputs.
        timeout_s: Hard ceiling; the process is killed past it.
        input_bytes: Bytes to feed on stdin (``-i pipe:0``), if any.

    Returns:
        stdout (empty unless the command writes to ``pipe:1``).

    Raises:
        FfmpegError: On a non-zero exit, a timeout, or a missing binary.
    """
    return await _run(
        "ffmpeg", ["-v", "error", "-y", *args], timeout_s=timeout_s, input_bytes=input_bytes
    )


async def probe_duration(path: Path, *, timeout_s: float) -> float:
    """Container duration of an audio file, in seconds.

    Args:
        path: The file.
        timeout_s: Hard ceiling for ffprobe.

    Returns:
        The duration.

    Raises:
        FfmpegError: When ffprobe fails or reports no duration.
    """
    out = await _run(
        "ffprobe",
        [
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout_s=timeout_s,
    )
    try:
        return float(out.decode().strip())
    except ValueError as exc:
        raise FfmpegError("ffprobe reported no duration") from exc


async def transcode(
    audio: bytes, *, output_format: str, args: Sequence[str], timeout_s: float
) -> bytes:
    """Transcode an in-memory audio buffer through pipes (no temporary file).

    Args:
        audio: Any container ffmpeg can sniff (WAV, MP3…).
        output_format: The muxer (``mp3``, ``wav``…).
        args: Encoder arguments (codec, bitrate, channels…).
        timeout_s: Hard ceiling.

    Returns:
        The encoded bytes.

    Raises:
        FfmpegError: On failure or timeout.
    """
    return await run_ffmpeg(
        ["-i", "pipe:0", *args, "-f", output_format, "pipe:1"],
        timeout_s=timeout_s,
        input_bytes=audio,
    )


__all__ = ["FfmpegError", "probe_duration", "run_ffmpeg", "transcode"]
