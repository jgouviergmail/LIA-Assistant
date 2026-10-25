"""Imported meeting files through the REAL ffmpeg (owner request 2026-10-24).

The unit tests pin the arguments; this proves what the binary does with them.
Each format the person may import — a WAV, a variable-bitrate MP3, an AAC M4A
like a phone's voice memo — arrives in several chunks and comes out as ONE
mono Opus/WebM file whose length ffprobe measured; a file longer than the cap
is refused before it is transcoded; and the disguises ffmpeg would follow when
left to guess — a playlist, a concat script — are read through the imposed
demuxer, which cannot read them: refused, nothing fetched, nothing written.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from src.domains.meetings.audio_store import AudioRefusedError, MeetingAudioStore
from src.domains.meetings.error_codes import ERROR_AUDIO_UNREADABLE, ERROR_IMPORT_TOO_LONG
from src.domains.meetings.models import MeetingAudioFormat

REQUIRES_ASYNC_SUBPROCESSES = True

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
        reason="real imports require ffmpeg and ffprobe",
    ),
]

SECONDS = 3
#: How each sample is encoded, as a person's device would have recorded it.
ENCODINGS: dict[MeetingAudioFormat, tuple[str, list[str]]] = {
    MeetingAudioFormat.IMPORT_WAV: ("sample.wav", ["-ac", "2", "-ar", "44100"]),
    MeetingAudioFormat.IMPORT_MP3: ("sample.mp3", ["-c:a", "libmp3lame", "-q:a", "4"]),
    MeetingAudioFormat.IMPORT_M4A: ("sample.m4a", ["-c:a", "aac", "-b:a", "64k"]),
}


@pytest.fixture(scope="module")
def samples(tmp_path_factory: pytest.TempPathFactory) -> dict[MeetingAudioFormat, bytes]:
    directory = tmp_path_factory.mktemp("import-samples")
    produced: dict[MeetingAudioFormat, bytes] = {}
    for audio_format, (name, encoding) in ENCODINGS.items():
        target = directory / name
        subprocess.run(
            [
                *("ffmpeg", "-v", "error", "-f", "lavfi"),
                *("-i", f"sine=frequency=440:duration={SECONDS}", *encoding, str(target)),
            ],
            check=True,
        )
        produced[audio_format] = target.read_bytes()
    return produced


async def _upload(
    store: MeetingAudioStore, data: bytes, parts: int = 3
) -> tuple[uuid.UUID, uuid.UUID]:
    """Write ``data`` as the import's chunks, the way the routes store them."""
    user_id, meeting_id = uuid.uuid4(), uuid.uuid4()
    size = -(-len(data) // parts)
    for sequence in range(parts):
        await store.write_segment(
            user_id, meeting_id, sequence, data[sequence * size : (sequence + 1) * size]
        )
    return user_id, meeting_id


def _probe(path: Path) -> dict[str, object]:
    output = subprocess.run(
        [
            *("ffprobe", "-v", "error", "-show_entries"),
            *("format=format_name,duration:stream=codec_name,channels", "-of", "json", str(path)),
        ],
        check=True,
        capture_output=True,
    ).stdout
    return dict(json.loads(output))


@pytest.mark.parametrize("audio_format", list(ENCODINGS))
async def test_each_format_becomes_one_mono_opus_file_of_its_length(
    tmp_path: Path, samples: dict[MeetingAudioFormat, bytes], audio_format: MeetingAudioFormat
) -> None:
    store = MeetingAudioStore(tmp_path)
    user_id, meeting_id = await _upload(store, samples[audio_format])

    path, duration = await store.normalize(
        user_id,
        meeting_id,
        audio_format=audio_format,
        duration_hint_seconds=None,
        max_duration_seconds=3600,
    )

    assert path.name == "audio.webm"
    assert abs(duration - SECONDS) < 0.25
    probe = _probe(path)
    container, streams = probe["format"], probe["streams"]
    assert isinstance(container, dict) and "webm" in str(container["format_name"])
    assert isinstance(streams, list) and len(streams) == 1
    assert streams[0]["codec_name"] == "opus" and streams[0]["channels"] == 1


async def test_a_file_longer_than_the_cap_is_refused_before_any_transcoding(
    tmp_path: Path, samples: dict[MeetingAudioFormat, bytes]
) -> None:
    store = MeetingAudioStore(tmp_path)
    user_id, meeting_id = await _upload(store, samples[MeetingAudioFormat.IMPORT_MP3])

    with pytest.raises(AudioRefusedError) as refused:
        await store.normalize(
            user_id,
            meeting_id,
            audio_format=MeetingAudioFormat.IMPORT_MP3,
            duration_hint_seconds=None,
            max_duration_seconds=SECONDS - 1,
        )

    assert refused.value.code == ERROR_IMPORT_TOO_LONG
    assert not store.normalized_path(user_id, meeting_id, MeetingAudioFormat.IMPORT_MP3).exists()


@pytest.mark.parametrize(
    ("audio_format", "content"),
    [
        (
            MeetingAudioFormat.IMPORT_M4A,
            b"#EXTM3U\n#EXT-X-TARGETDURATION:3\n#EXTINF:3,\nhttp://203.0.113.1/a.ts\n#EXT-X-ENDLIST\n",
        ),
        (MeetingAudioFormat.IMPORT_MP3, b"ffconcat version 1.0\nfile 'other.wav'\n"),
    ],
    ids=["playlist-as-m4a", "concat-script-as-mp3"],
)
async def test_a_disguised_file_is_unreadable_through_its_imposed_demuxer(
    tmp_path: Path, audio_format: MeetingAudioFormat, content: bytes
) -> None:
    store = MeetingAudioStore(tmp_path)
    user_id, meeting_id = await _upload(store, content, parts=1)

    with pytest.raises(AudioRefusedError) as refused:
        await store.normalize(
            user_id,
            meeting_id,
            audio_format=audio_format,
            duration_hint_seconds=None,
            max_duration_seconds=3600,
        )

    assert refused.value.code == ERROR_AUDIO_UNREADABLE
    assert not store.normalized_path(user_id, meeting_id, audio_format).exists()
