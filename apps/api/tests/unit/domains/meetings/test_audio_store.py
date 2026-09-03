"""Audio store (ADR-258): atomic per-segment files, containment, assembly, bitrate."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from src.core.constants import (
    MEETINGS_OPUS_BITRATE_MAX_KBPS,
    MEETINGS_OPUS_BITRATE_MIN_KBPS,
    MEETINGS_REMOTE_FILE_MAX_BYTES,
)
from src.domains.meetings.audio_store import (
    AudioStorageError,
    MeetingAudioStore,
    opus_bitrate_kbps,
    pcm_duration_seconds,
)

pytestmark = pytest.mark.unit


def test_bitrate_is_transparent_for_short_meetings_and_floors_for_long_ones() -> None:
    assert opus_bitrate_kbps(0) == MEETINGS_OPUS_BITRATE_MAX_KBPS
    assert opus_bitrate_kbps(3600) == MEETINGS_OPUS_BITRATE_MAX_KBPS  # 1 h at 32 kbps ≈ 14 MB
    three_hours = opus_bitrate_kbps(3 * 3600)
    assert MEETINGS_OPUS_BITRATE_MIN_KBPS <= three_hours < MEETINGS_OPUS_BITRATE_MAX_KBPS
    # The chosen bitrate really keeps the file under the cap (5 % framing headroom).
    assert three_hours * 1000 / 8 * 3 * 3600 <= MEETINGS_REMOTE_FILE_MAX_BYTES * 0.95
    assert opus_bitrate_kbps(24 * 3600) == MEETINGS_OPUS_BITRATE_MIN_KBPS


def test_pcm_duration_is_bytes_over_32000() -> None:
    assert pcm_duration_seconds(32000 * 30) == 30.0


async def test_segments_are_written_atomically_listed_and_assembled_in_order(
    tmp_path: Path,
) -> None:
    store = MeetingAudioStore(tmp_path)
    user_id, meeting_id = uuid.uuid4(), uuid.uuid4()

    added, replaced = await store.write_segment(user_id, meeting_id, 1, b"BB")
    assert (added, replaced) == (2, False)
    added, replaced = await store.write_segment(user_id, meeting_id, 0, b"AAA")
    assert (added, replaced) == (3, False)
    # Re-uploading sequence 1 with a different body reports the size delta and the overwrite.
    added, replaced = await store.write_segment(user_id, meeting_id, 1, b"BBBB")
    assert (added, replaced) == (2, True)

    assert await store.list_sequences(user_id, meeting_id) == [0, 1]
    assert store.missing_sequences([0, 1], 4) == [2, 3]
    assert await store.total_segment_bytes(user_id, meeting_id) == 7
    # No temp file survives a write.
    assert not list((store.meeting_dir(user_id, meeting_id) / "segments").glob(".*.tmp"))

    assembled = await store.assemble(user_id, meeting_id)
    assert assembled.read_bytes() == b"AAABBBB"

    assert await store.purge_segments(user_id, meeting_id) == 2
    assert await store.list_sequences(user_id, meeting_id) == []
    await store.purge_meeting(user_id, meeting_id)
    assert not store.meeting_dir(user_id, meeting_id).exists()


async def test_assemble_refuses_an_empty_meeting(tmp_path: Path) -> None:
    store = MeetingAudioStore(tmp_path)
    with pytest.raises(AudioStorageError, match="no segment"):
        await store.assemble(uuid.uuid4(), uuid.uuid4())


def test_paths_never_escape_the_root(tmp_path: Path) -> None:
    store = MeetingAudioStore(tmp_path)
    with pytest.raises(AudioStorageError):
        store.absolute("../../etc/passwd")
    with pytest.raises(AudioStorageError):
        store.segment_path(uuid.uuid4(), uuid.uuid4(), -1)
    relative = store.relative(store.meeting_dir(uuid.uuid4(), uuid.uuid4()) / "audio.webm")
    assert relative.endswith("/audio.webm") and ".." not in relative
