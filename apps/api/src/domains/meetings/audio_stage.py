"""The normalizing stage of a meeting's processing (ADR-258): its audio, once.

Extracted from ``processing.py`` when imported files joined the recordings
(owner request 2026-10-24). A recording's segments and an imported file's
chunks both become ONE Opus file here — the import measured against the
instance's duration cap BEFORE any engine is paid — and the result is
checkpointed on the row, so a retry reuses it instead of running ffmpeg again.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

import structlog

from src.core.config import settings
from src.domains.meetings.audio_store import (
    AudioRefusedError,
    AudioStorageError,
    MeetingAudioStore,
    pcm_duration_seconds,
)
from src.domains.meetings.models import Meeting, MeetingAudioFormat, is_import

logger = structlog.get_logger(__name__)

#: Writes the stage's columns on the row, under the job's lease.
Checkpoint = Callable[[dict[str, Any]], Awaitable[None]]


class AcquiredAudio(NamedTuple):
    """The normalized audio of a meeting, as the stage checkpoints it."""

    path: str
    duration: float
    gaps: int


def stopped_at_of(meeting: Meeting, duration: float) -> datetime:
    """When the meeting ended: an import where its audio does, a recording when stopped."""
    if is_import(meeting.audio_format):
        return meeting.started_at + timedelta(seconds=duration)
    return meeting.stopped_at or datetime.now(UTC)


def audio_checkpoint(meeting: Meeting, acquired: AcquiredAudio) -> dict[str, Any]:
    """The columns the stage acquires — checkpointed, then part of the completion."""
    values: dict[str, Any] = {
        "audio_path": acquired.path,
        "audio_duration_seconds": acquired.duration,
        "audio_gaps": acquired.gaps,
    }
    if is_import(meeting.audio_format):
        # Dated by the person, measured by ffprobe: the file says when it ended.
        values["stopped_at"] = stopped_at_of(meeting, acquired.duration)
    return values


async def _normalize(store: MeetingAudioStore, meeting: Meeting) -> tuple[str, float, int]:
    """Segments → one Opus file. Returns ``(relative_path, duration, gaps)``.

    Raises:
        AudioRefusedError: An import ffmpeg cannot read, or longer than the cap.
    """
    present = await store.list_sequences(meeting.user_id, meeting.id)
    gaps = len(store.missing_sequences(present, meeting.segment_count))
    hint = (
        pcm_duration_seconds(await store.total_segment_bytes(meeting.user_id, meeting.id))
        if meeting.audio_format is MeetingAudioFormat.PCM_S16LE_16
        else None
    )
    try:
        path, duration = await store.normalize(
            meeting.user_id,
            meeting.id,
            audio_format=meeting.audio_format,
            duration_hint_seconds=hint,
            max_duration_seconds=settings.meetings_max_duration_minutes * 60,
        )
    except AudioRefusedError:
        # Refused for good: no retry can turn this file into a meeting, so what
        # was uploaded goes now. A purge that fails must not hide the refusal.
        with suppress(AudioStorageError):
            await store.purge_segments(meeting.user_id, meeting.id)
        raise
    try:
        await store.purge_segments(meeting.user_id, meeting.id)
    except AudioStorageError as exc:
        logger.warning("meeting_segments_purge_failed", meeting_id=str(meeting.id), error=str(exc))
    return store.relative(path), duration, gaps


async def acquire_audio(
    store: MeetingAudioStore, meeting: Meeting, *, checkpoint: Checkpoint
) -> AcquiredAudio | None:
    """The normalized audio: the checkpoint when its file is still there, else ffmpeg.

    A previous attempt purged the segments after normalizing and checkpointed
    the result; this attempt reuses it. With no checkpointed file AND no
    segment on disk there is nothing to process and never will be: the caller
    dead-letters the meeting as ``audio_unavailable`` rather than spending its
    retry budget on ffmpeg over nothing. Returns ``None`` in that case.

    Raises:
        AudioRefusedError: An import ffmpeg cannot read, or longer than the cap.
    """
    if meeting.audio_path:
        normalized = store.absolute(meeting.audio_path)
        if await asyncio.to_thread(os.path.exists, normalized):
            return AcquiredAudio(
                meeting.audio_path,
                float(meeting.audio_duration_seconds or 0.0),
                int(meeting.audio_gaps or 0),
            )
    if not await store.list_sequences(meeting.user_id, meeting.id):
        return None
    acquired = AcquiredAudio(*await _normalize(store, meeting))
    await checkpoint(audio_checkpoint(meeting, acquired))
    return acquired


__all__ = ["AcquiredAudio", "acquire_audio", "audio_checkpoint", "stopped_at_of"]
