"""Disk storage of meeting audio (ADR-258).

Layout under ``meetings_storage_path``::

    {user_id}/{meeting_id}/segments/{sequence:06d}.bin   while recording (or importing)
    {user_id}/{meeting_id}/audio.{webm|ogg}              after normalization

Why per-segment files: production runs four uvicorn workers, and a segment may
land on any of them — appending to one shared file would interleave. A file
per sequence, written to a temp name then ``os.replace``d, is atomic, makes a
duplicate upload a harmless overwrite and turns gap detection into a directory
listing. Assembly and normalization happen once, under the processing lease.

Why ffmpeg as a subprocess: a whole meeting is up to 115 MB of PCM; decoding
it in memory (pydub) on the event loop is exactly what the async rules forbid.

An imported file (WAV, MP3, M4A — owner request 2026-10-24) is untrusted input:
ffmpeg reads it through the demuxer of its declared format and nothing else —
never a guess, which could pick a playlist or a concat script reading other
files — over the local-file protocol only, and a QuickTime file never follows
its references to other files. Its length is measured before it is transcoded.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

import structlog

from src.core.constants import (
    MEETINGS_OPUS_BITRATE_MAX_KBPS,
    MEETINGS_OPUS_BITRATE_MIN_KBPS,
    MEETINGS_REMOTE_FILE_MAX_BYTES,
    STT_BYTES_PER_SECOND_AT_16KHZ_INT16,
)
from src.domains.meetings.error_codes import ERROR_AUDIO_UNREADABLE, ERROR_IMPORT_TOO_LONG
from src.domains.meetings.models import MeetingAudioFormat, is_import

logger = structlog.get_logger(__name__)

SEGMENTS_DIR = "segments"
SEGMENT_SUFFIX = ".bin"
#: Sample rate of PCM segments — the frontend worklet's fixed rate.
PCM_SAMPLE_RATE = 16000


class AudioStorageError(RuntimeError):
    """A disk or ffmpeg operation failed; the caller decides retry vs fail."""


class AudioRefusedError(RuntimeError):
    """An imported file can never be processed as it is: refused for good, with a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


#: The ONE demuxer each imported format is read through (M4A is QuickTime/MP4).
IMPORT_DEMUXERS: dict[MeetingAudioFormat, str] = {
    MeetingAudioFormat.IMPORT_WAV: "wav",
    MeetingAudioFormat.IMPORT_MP3: "mp3",
    MeetingAudioFormat.IMPORT_M4A: "mov",
}


def import_input_args(audio_format: MeetingAudioFormat, path: Path) -> list[str]:
    """How ffmpeg and ffprobe open an imported file: its own demuxer, local files only."""
    demuxer = IMPORT_DEMUXERS[audio_format]
    references = ["-enable_drefs", "0"] if demuxer == "mov" else []
    return ["-protocol_whitelist", "file", "-f", demuxer, *references, "-i", str(path)]


TStorageResult = TypeVar("TStorageResult")


async def _complete_storage_work(write: Callable[[], TStorageResult]) -> TStorageResult:
    """Keep the caller's row lock until the uninterruptible disk effect ends."""
    task = asyncio.create_task(asyncio.to_thread(write))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except OSError:
            if cancelled:
                raise asyncio.CancelledError() from None
            raise
    if cancelled:
        task.exception()
        raise asyncio.CancelledError()
    return task.result()


def opus_bitrate_kbps(
    duration_seconds: float, *, max_bytes: int = MEETINGS_REMOTE_FILE_MAX_BYTES
) -> int:
    """Pick the Opus bitrate that keeps the whole meeting under ``max_bytes``.

    32 kbps is transparent for speech; the value only drops (never below the
    floor) when the recording is long enough to threaten the remote file cap.

    Args:
        duration_seconds: Recording length.
        max_bytes: Provider request cap (OpenAI: 25 MB).

    Returns:
        Bitrate in kbps within [floor, ceiling].
    """
    if duration_seconds <= 0:
        return MEETINGS_OPUS_BITRATE_MAX_KBPS
    # 5 % headroom for container framing; kbps = kilobits, hence the 1000.
    affordable = math.floor((max_bytes * 8 * 0.95) / duration_seconds / 1000)
    return max(MEETINGS_OPUS_BITRATE_MIN_KBPS, min(MEETINGS_OPUS_BITRATE_MAX_KBPS, affordable))


def _opus_webm_args(bitrate_kbps: int, target: Path) -> list[str]:
    """The ONE speech encoding a transcoded meeting gets: Opus in WebM, VBR, voice-tuned."""
    return [
        *("-c:a", "libopus", "-b:a", f"{bitrate_kbps}k", "-vbr", "on"),
        *("-application", "voip", "-f", "webm", str(target)),
    ]


def pcm_duration_seconds(byte_count: int) -> float:
    """Duration of raw 16 kHz int16 mono PCM."""
    return byte_count / STT_BYTES_PER_SECOND_AT_16KHZ_INT16


def normalized_filename(audio_format: MeetingAudioFormat) -> str:
    """Name of the normalized artifact for a client format."""
    return "audio.ogg" if audio_format is MeetingAudioFormat.OGG_OPUS else "audio.webm"


def normalized_mime_type(audio_format: MeetingAudioFormat) -> str:
    """MIME type of the normalized artifact."""
    return "audio/ogg" if audio_format is MeetingAudioFormat.OGG_OPUS else "audio/webm"


class MeetingAudioStore:
    """Per-meeting audio files with path containment and atomic writes."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------- paths

    def meeting_dir(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> Path:
        """``{root}/{user}/{meeting}``, guaranteed inside the root."""
        path = (self._root / str(user_id) / str(meeting_id)).resolve()
        if not path.is_relative_to(self._root):
            raise AudioStorageError("meeting directory escapes the storage root")
        return path

    def segment_path(self, user_id: uuid.UUID, meeting_id: uuid.UUID, sequence: int) -> Path:
        if sequence < 0:
            raise AudioStorageError("segment sequence must be non-negative")
        return (
            self.meeting_dir(user_id, meeting_id) / SEGMENTS_DIR / f"{sequence:06d}{SEGMENT_SUFFIX}"
        )

    def normalized_path(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID, audio_format: MeetingAudioFormat
    ) -> Path:
        return self.meeting_dir(user_id, meeting_id) / normalized_filename(audio_format)

    def relative(self, path: Path) -> str:
        """Path relative to the root, as stored in the database."""
        return path.resolve().relative_to(self._root).as_posix()

    def absolute(self, relative_path: str) -> Path:
        """Resolve a stored relative path, refusing anything outside the root."""
        path = (self._root / relative_path).resolve()
        if not path.is_relative_to(self._root):
            raise AudioStorageError("stored audio path escapes the storage root")
        return path

    # ---------------------------------------------------------- segments

    async def write_segment(
        self, user_id: uuid.UUID, meeting_id: uuid.UUID, sequence: int, data: bytes
    ) -> tuple[int, bool]:
        """Write one segment atomically (temp file + rename).

        Returns:
            ``(bytes_added, replaced)`` — ``bytes_added`` is the size difference
            the meeting's byte total must absorb (0 for an identical re-upload),
            ``replaced`` tells whether a file already existed for this sequence.
        """
        target = self.segment_path(user_id, meeting_id, sequence)

        def _write() -> tuple[int, bool]:
            target.parent.mkdir(parents=True, exist_ok=True)
            previous = target.stat().st_size if target.exists() else None
            tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            try:
                tmp.write_bytes(data)
                os.replace(tmp, target)
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
            return len(data) - (previous or 0), previous is not None

        try:
            return await _complete_storage_work(_write)
        except OSError as exc:
            raise AudioStorageError(f"segment write failed: {exc.__class__.__name__}") from exc

    async def segment_size(self, user_id: uuid.UUID, meeting_id: uuid.UUID, sequence: int) -> int:
        """Bytes already stored under ``sequence`` (0 when none): what a resend replaces."""
        target = self.segment_path(user_id, meeting_id, sequence)

        def _size() -> int:
            return target.stat().st_size if target.exists() else 0

        return await asyncio.to_thread(_size)

    async def list_sequences(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> list[int]:
        """Sequences present on disk, ascending."""
        directory = self.meeting_dir(user_id, meeting_id) / SEGMENTS_DIR

        def _list() -> list[int]:
            if not directory.is_dir():
                return []
            sequences: list[int] = []
            for entry in directory.iterdir():
                if entry.suffix == SEGMENT_SUFFIX and entry.stem.isdigit():
                    sequences.append(int(entry.stem))
            return sorted(sequences)

        return await asyncio.to_thread(_list)

    @staticmethod
    def missing_sequences(present: Sequence[int], expected_count: int) -> list[int]:
        """Sequences in ``0..expected_count-1`` that are not on disk."""
        have = set(present)
        return [seq for seq in range(expected_count) if seq not in have]

    async def total_segment_bytes(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> int:
        """Sum of the segment files on disk (the audited truth for PCM duration)."""
        directory = self.meeting_dir(user_id, meeting_id) / SEGMENTS_DIR

        def _sum() -> int:
            if not directory.is_dir():
                return 0
            return sum(
                entry.stat().st_size
                for entry in directory.iterdir()
                if entry.suffix == SEGMENT_SUFFIX and entry.stem.isdigit()
            )

        return await asyncio.to_thread(_sum)

    # ---------------------------------------------------- normalization

    async def assemble(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> Path:
        """Concatenate the segments in sequence order into ``assembled.bin``.

        PCM segments concatenate byte for byte; Opus timeslice chunks form one
        continuous stream (the first chunk carries the container header). Gaps
        are simply absent: nothing is invented in their place.
        """
        directory = self.meeting_dir(user_id, meeting_id)
        sequences = await self.list_sequences(user_id, meeting_id)
        if not sequences:
            raise AudioStorageError("no segment on disk")
        target = directory / "assembled.bin"

        def _concat() -> None:
            with target.open("wb") as out:
                for seq in sequences:
                    with (directory / SEGMENTS_DIR / f"{seq:06d}{SEGMENT_SUFFIX}").open(
                        "rb"
                    ) as part:
                        while chunk := part.read(1024 * 1024):
                            out.write(chunk)

        try:
            await asyncio.to_thread(_concat)
        except OSError as exc:
            raise AudioStorageError(f"assembly failed: {exc.__class__.__name__}") from exc
        return target

    async def normalize(
        self,
        user_id: uuid.UUID,
        meeting_id: uuid.UUID,
        *,
        audio_format: MeetingAudioFormat,
        duration_hint_seconds: float | None,
        max_duration_seconds: float | None = None,
    ) -> tuple[Path, float]:
        """Turn the assembled segments into ONE clean Opus file.

        PCM is encoded at a bitrate keeping the file under the remote cap; Opus
        streams are remuxed with ``-c copy``, which drops a truncated tail (the
        crash case) without re-encoding. An imported file is measured first and
        refused past ``max_duration_seconds``, then transcoded to mono Opus. The
        result's duration is measured with ffprobe — the authority for what the
        engines will bill.

        Returns:
            ``(normalized_path, duration_seconds)``.

        Raises:
            AudioRefusedError: An import ffmpeg cannot read, or longer than the cap.
        """
        assembled = await self.assemble(user_id, meeting_id)
        target = self.normalized_path(user_id, meeting_id, audio_format)
        if is_import(audio_format):
            try:
                duration = await self._probe_import(assembled, audio_format)
                if max_duration_seconds is not None and duration > max_duration_seconds:
                    raise AudioRefusedError(ERROR_IMPORT_TOO_LONG)
            except AudioRefusedError:
                # The full copy assembled for the probe must not outlive a refusal.
                await asyncio.to_thread(assembled.unlink, missing_ok=True)
                raise
            # The first audio stream only (an M4A may carry cover art), mono speech.
            args = [
                *import_input_args(audio_format, assembled),
                *("-map", "0:a:0", "-ac", "1", "-ar", str(PCM_SAMPLE_RATE)),
                *_opus_webm_args(opus_bitrate_kbps(duration), target),
            ]
        elif audio_format is MeetingAudioFormat.PCM_S16LE_16:
            duration = duration_hint_seconds or pcm_duration_seconds(assembled.stat().st_size)
            args = [
                *("-f", "s16le", "-ar", str(PCM_SAMPLE_RATE), "-ac", "1", "-i", str(assembled)),
                *_opus_webm_args(opus_bitrate_kbps(duration), target),
            ]
        else:
            container = "ogg" if audio_format is MeetingAudioFormat.OGG_OPUS else "webm"
            args = ["-i", str(assembled), "-c", "copy", "-f", container, str(target)]
        await self._run_ffmpeg(args)
        try:
            assembled.unlink(missing_ok=True)
        except OSError:
            logger.debug("meeting_assembled_cleanup_failed", meeting_id=str(meeting_id))
        duration_seconds = await self.probe_duration(target)
        return target, duration_seconds

    async def _probe_import(self, path: Path, audio_format: MeetingAudioFormat) -> float:
        """An imported file's length, read through its own demuxer — refused when unreadable."""
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index:format=duration",
            "-of",
            "json",
            *import_input_args(audio_format, path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            probe = json.loads(stdout.decode() or "{}") if proc.returncode == 0 else {}
            duration = float(probe["format"]["duration"]) if probe.get("streams") else 0.0
        except KeyError, TypeError, ValueError:
            duration = 0.0
        if duration <= 0:
            raise AudioRefusedError(ERROR_AUDIO_UNREADABLE)
        return duration

    async def probe_duration(self, path: Path) -> float:
        """Container duration in seconds via ffprobe."""
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise AudioStorageError(f"ffprobe failed: {stderr.decode(errors='replace')[:200]}")
        try:
            return float(stdout.decode().strip())
        except ValueError as exc:
            raise AudioStorageError("ffprobe returned no duration") from exc

    @staticmethod
    async def _run_ffmpeg(args: list[str]) -> None:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-v",
            "error",
            "-y",
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise AudioStorageError(f"ffmpeg failed: {stderr.decode(errors='replace')[:200]}")

    # ------------------------------------------------------------- purge

    async def purge_segments(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> int:
        """Delete the segment files (after a successful normalization)."""
        directory = self.meeting_dir(user_id, meeting_id) / SEGMENTS_DIR

        def _purge() -> int:
            if not directory.is_dir():
                return 0
            count = 0
            for entry in directory.iterdir():
                entry.unlink(missing_ok=True)
                count += 1
            directory.rmdir()
            return count

        try:
            return await asyncio.to_thread(_purge)
        except OSError as exc:
            raise AudioStorageError(f"segment purge failed: {exc.__class__.__name__}") from exc

    async def purge_meeting(self, user_id: uuid.UUID, meeting_id: uuid.UUID) -> bool:
        """Remove only the exact owned directory after its database commit."""
        expected = self.root / str(user_id) / str(meeting_id)

        def purge() -> bool:
            directory = expected.resolve()
            if directory != expected or expected.is_symlink():
                return False
            if directory.exists():
                shutil.rmtree(directory)
            return not directory.exists()

        try:
            return await _complete_storage_work(purge)
        except OSError:
            logger.warning("meeting_audio_purge_failed", meeting_id=str(meeting_id))
            return False
