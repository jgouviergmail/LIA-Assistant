"""Importing a meeting from a file (owner request 2026-10-24): WAV, MP3 or M4A.

A file is untrusted input handed to ffmpeg. Its first bytes must be the format
it claims; ffmpeg reads it through the demuxer of that format and nothing else
(never a guess, never a reference to another file); its length is judged before
any engine is paid; and it ends where its audio does.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.meetings.audio_stage import (
    AcquiredAudio,
    acquire_audio,
    audio_checkpoint,
    stopped_at_of,
)
from src.domains.meetings.audio_store import (
    AudioRefusedError,
    MeetingAudioStore,
    import_input_args,
)
from src.domains.meetings.error_codes import ERROR_AUDIO_UNREADABLE, ERROR_IMPORT_TOO_LONG
from src.domains.meetings.import_service import MeetingImportService, import_signature_matches
from src.domains.meetings.models import MeetingAudioFormat, MeetingStatus, is_import
from src.domains.meetings.schemas import (
    MeetingImportComplete,
    MeetingImportRequest,
    MeetingStartRequest,
)

pytestmark = pytest.mark.unit

AT = datetime(2026, 10, 20, 9, 30, tzinfo=UTC)
WAV_HEAD = b"RIFF\x24\x08\x00\x00WAVEfmt "
MP3_ID3_HEAD = b"ID3\x04\x00\x00\x00\x00\x00\x23TSSE"
MP3_SYNC_HEAD = b"\xff\xfb\x90\x64\x00\x00\x00\x00\x00\x00\x00\x00"
M4A_HEAD = b"\x00\x00\x00\x1cftypM4A \x00\x00"


# ------------------------------------------------------------- first bytes


@pytest.mark.parametrize(
    ("audio_format", "head"),
    [
        (MeetingAudioFormat.IMPORT_WAV, WAV_HEAD),
        (MeetingAudioFormat.IMPORT_MP3, MP3_ID3_HEAD),
        (MeetingAudioFormat.IMPORT_MP3, MP3_SYNC_HEAD),
        (MeetingAudioFormat.IMPORT_M4A, M4A_HEAD),
    ],
    ids=["wav", "mp3-id3", "mp3-frame-sync", "m4a"],
)
def test_a_file_that_starts_as_its_format_is_accepted(
    audio_format: MeetingAudioFormat, head: bytes
) -> None:
    assert import_signature_matches(audio_format, head)


@pytest.mark.parametrize(
    ("audio_format", "head"),
    [
        (MeetingAudioFormat.IMPORT_MP3, WAV_HEAD),
        (MeetingAudioFormat.IMPORT_WAV, M4A_HEAD),
        (MeetingAudioFormat.IMPORT_MP3, b"ffconcat version 1.0\nfile 'other.wav'\n"),
        (MeetingAudioFormat.IMPORT_M4A, b"#EXTM3U\n#EXT-X-VERSION:3\n"),
        (MeetingAudioFormat.IMPORT_WAV, b"RIFF"),
        (MeetingAudioFormat.IMPORT_MP3, b""),
        (MeetingAudioFormat.WEBM_OPUS, WAV_HEAD),
    ],
    ids=[
        "wav-renamed-mp3",
        "m4a-renamed-wav",
        "concat-script",
        "hls-playlist",
        "too-short",
        "empty",
        "not-an-import",
    ],
)
def test_anything_else_is_refused(audio_format: MeetingAudioFormat, head: bytes) -> None:
    assert not import_signature_matches(audio_format, head)


# ----------------------------------------------------------------- ffmpeg


@pytest.mark.parametrize(
    ("audio_format", "demuxer"),
    [
        (MeetingAudioFormat.IMPORT_WAV, "wav"),
        (MeetingAudioFormat.IMPORT_MP3, "mp3"),
        (MeetingAudioFormat.IMPORT_M4A, "mov"),
    ],
)
def test_ffmpeg_reads_an_import_through_its_own_demuxer_and_local_files_only(
    audio_format: MeetingAudioFormat, demuxer: str
) -> None:
    args = import_input_args(audio_format, Path("assembled.bin"))
    # The demuxer is imposed BEFORE the input: ffmpeg never guesses a format.
    assert args.index("-f") < args.index("-i")
    assert args[args.index("-f") + 1] == demuxer
    assert args[args.index("-protocol_whitelist") + 1] == "file"
    assert args[-1] == "assembled.bin"
    # A QuickTime file may point at other files: never follow them.
    assert ("-enable_drefs" in args) is (demuxer == "mov")
    if demuxer == "mov":
        assert args[args.index("-enable_drefs") + 1] == "0"


def test_only_the_three_import_formats_are_imports() -> None:
    assert {fmt for fmt in MeetingAudioFormat if is_import(fmt)} == {
        MeetingAudioFormat.IMPORT_WAV,
        MeetingAudioFormat.IMPORT_MP3,
        MeetingAudioFormat.IMPORT_M4A,
    }


async def test_an_import_too_long_is_refused_before_it_is_transcoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MeetingAudioStore(tmp_path)
    user_id, meeting_id = uuid.uuid4(), uuid.uuid4()
    await store.write_segment(user_id, meeting_id, 0, WAV_HEAD)
    monkeypatch.setattr(store, "_probe_import", AsyncMock(return_value=3601.0))
    transcode = AsyncMock()
    monkeypatch.setattr(store, "_run_ffmpeg", transcode)

    with pytest.raises(AudioRefusedError) as refused:
        await store.normalize(
            user_id,
            meeting_id,
            audio_format=MeetingAudioFormat.IMPORT_WAV,
            duration_hint_seconds=None,
            max_duration_seconds=3600,
        )
    assert refused.value.code == ERROR_IMPORT_TOO_LONG
    transcode.assert_not_awaited()
    # The full copy assembled for the probe does not outlive the refusal.
    assert not (store.meeting_dir(user_id, meeting_id) / "assembled.bin").exists()


async def test_a_refused_import_leaves_none_of_its_chunks_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No retry can save a file too long or unreadable: what was uploaded goes at once."""
    meeting = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        audio_format=MeetingAudioFormat.IMPORT_MP3,
        audio_path=None,
        segment_count=1,
        started_at=AT,
        stopped_at=AT,
    )
    store = MeetingAudioStore(tmp_path)
    await store.write_segment(meeting.user_id, meeting.id, 0, MP3_ID3_HEAD)
    monkeypatch.setattr(
        store, "normalize", AsyncMock(side_effect=AudioRefusedError(ERROR_IMPORT_TOO_LONG))
    )

    with pytest.raises(AudioRefusedError):
        await acquire_audio(store, meeting, checkpoint=AsyncMock())

    assert await store.list_sequences(meeting.user_id, meeting.id) == []


async def test_an_import_ffmpeg_cannot_read_is_refused_for_good(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = MeetingAudioStore(tmp_path)
    user_id, meeting_id = uuid.uuid4(), uuid.uuid4()
    await store.write_segment(user_id, meeting_id, 0, b"\xff\xfb" + b"\x00" * 64)

    async def unreadable(*_args: Any, **_kwargs: Any) -> Any:
        process = MagicMock()
        process.returncode = 1
        process.communicate = AsyncMock(return_value=(b"{}", b"Invalid data"))
        return process

    monkeypatch.setattr("asyncio.create_subprocess_exec", unreadable)
    with pytest.raises(AudioRefusedError) as refused:
        await store.normalize(
            user_id,
            meeting_id,
            audio_format=MeetingAudioFormat.IMPORT_MP3,
            duration_hint_seconds=None,
            max_duration_seconds=3600,
        )
    assert refused.value.code == ERROR_AUDIO_UNREADABLE


def test_an_import_ends_where_its_audio_does() -> None:
    meeting = SimpleNamespace(
        audio_format=MeetingAudioFormat.IMPORT_MP3, started_at=AT, stopped_at=AT
    )
    assert stopped_at_of(meeting, 90.5) == AT + timedelta(seconds=90.5)


def test_the_checkpoint_dates_an_import_by_its_audio_and_leaves_a_recording_alone() -> None:
    acquired = AcquiredAudio("u/m/audio.webm", 90.5, 0)
    imported = SimpleNamespace(audio_format=MeetingAudioFormat.IMPORT_WAV, started_at=AT)
    recorded = SimpleNamespace(audio_format=MeetingAudioFormat.WEBM_OPUS, started_at=AT)
    assert audio_checkpoint(imported, acquired)["stopped_at"] == AT + timedelta(seconds=90.5)
    assert "stopped_at" not in audio_checkpoint(recorded, acquired)


def test_a_recording_ends_when_it_was_stopped() -> None:
    stopped = AT + timedelta(minutes=40)
    meeting = SimpleNamespace(
        audio_format=MeetingAudioFormat.WEBM_OPUS, started_at=AT, stopped_at=stopped
    )
    assert stopped_at_of(meeting, 90.5) == stopped


# ---------------------------------------------------------------- schemas


def test_a_live_recording_cannot_start_in_an_import_format() -> None:
    with pytest.raises(ValidationError):
        MeetingStartRequest(audio_format=MeetingAudioFormat.IMPORT_WAV, timezone="UTC")


def _import_request(**overrides: Any) -> MeetingImportRequest:
    values: dict[str, Any] = {
        "audio_format": MeetingAudioFormat.IMPORT_M4A,
        "size_bytes": 1024,
        "recorded_at": AT,
        "timezone": "Europe/Rome",
    }
    return MeetingImportRequest(**{**values, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"audio_format": MeetingAudioFormat.WEBM_OPUS},
        {"recorded_at": datetime.now(UTC) + timedelta(days=1)},
        {"recorded_at": datetime(2026, 10, 20, 9, 30)},  # naive: no zone at all
        {"size_bytes": 0},
        {"timezone": "Mars/Olympus"},
    ],
    ids=["live-format", "future", "naive", "empty", "unknown-zone"],
)
def test_an_import_request_states_a_real_file_recorded_in_the_past(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        _import_request(**overrides)


# ---------------------------------------------------------------- service


def _meeting(status: MeetingStatus = MeetingStatus.UPLOADING, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "status": status,
        "audio_format": MeetingAudioFormat.IMPORT_WAV,
        "segment_count": 0,
        "audio_bytes": 0,
        "started_at": AT,
    }
    return SimpleNamespace(**{**values, **overrides})


@pytest.fixture
def imports() -> MeetingImportService:
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    svc = MeetingImportService(db)
    svc.meetings.repo = AsyncMock()
    svc.meetings.store = MagicMock()
    svc.meetings.store.write_segment = AsyncMock(return_value=(10, False))
    svc.meetings.store.segment_size = AsyncMock(return_value=0)
    svc.meetings.store.list_sequences = AsyncMock(return_value=[0, 1])
    svc.meetings.store.missing_sequences = MeetingAudioStore.missing_sequences
    return svc


def _code(exc: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = exc.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


async def test_an_import_is_refused_while_the_instance_does_not_offer_it(
    imports: MeetingImportService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "meetings_import_enabled", False)
    with pytest.raises(BaseAPIException) as exc:
        await imports.create(SimpleNamespace(id=uuid.uuid4(), language="en"), _import_request())
    assert exc.value.status_code == 409 and _code(exc) == "import_disabled"
    imports.meetings.repo.create.assert_not_awaited()


async def test_a_file_over_the_published_size_is_refused_before_any_row(
    imports: MeetingImportService,
) -> None:
    request = _import_request(size_bytes=settings.meetings_import_max_bytes + 1)
    with pytest.raises(BaseAPIException) as exc:
        await imports.create(SimpleNamespace(id=uuid.uuid4(), language="en"), request)
    assert exc.value.status_code == 413 and _code(exc) == "import_too_large"
    imports.meetings.repo.create.assert_not_awaited()


async def test_a_second_import_of_the_same_account_is_a_conflict(
    imports: MeetingImportService, monkeypatch: pytest.MonkeyPatch
) -> None:
    admission = SimpleNamespace(
        engine=SimpleNamespace(provider=MagicMock(), model=None, diarized=False),
        language="auto",
        template=None,
    )
    monkeypatch.setattr(imports.meetings, "admit", AsyncMock(return_value=admission))
    imports.meetings.repo.create.side_effect = IntegrityError("insert", {}, Exception("unique"))
    with pytest.raises(BaseAPIException) as exc:
        await imports.create(SimpleNamespace(id=uuid.uuid4(), language="en"), _import_request())
    assert exc.value.status_code == 409 and _code(exc) == "import_already_running"
    imports.meetings.db.rollback.assert_awaited()


async def test_a_chunk_is_refused_once_the_import_is_no_longer_uploading(
    imports: MeetingImportService,
) -> None:
    meeting = _meeting(MeetingStatus.STOPPED)
    imports.meetings.repo.get_for_user.return_value = meeting
    with pytest.raises(BaseAPIException) as exc:
        await imports.accept_chunk(meeting.user_id, meeting.id, sequence=1, body=b"x")
    assert exc.value.status_code == 409 and _code(exc) == "meeting_not_uploading"
    imports.meetings.store.write_segment.assert_not_awaited()


async def test_a_live_recording_is_not_an_import(imports: MeetingImportService) -> None:
    meeting = _meeting(MeetingStatus.RECORDING, audio_format=MeetingAudioFormat.WEBM_OPUS)
    imports.meetings.repo.get_for_user.return_value = meeting
    with pytest.raises(BaseAPIException) as exc:
        await imports.accept_chunk(meeting.user_id, meeting.id, sequence=0, body=WAV_HEAD)
    assert _code(exc) == "meeting_not_uploading"


async def test_a_chunk_over_the_published_size_never_touches_the_disk(
    imports: MeetingImportService,
) -> None:
    meeting = _meeting()
    imports.meetings.repo.get_for_user.return_value = meeting
    body = b"\x00" * (settings.meetings_import_chunk_max_bytes + 1)
    with pytest.raises(BaseAPIException) as exc:
        await imports.accept_chunk(meeting.user_id, meeting.id, sequence=1, body=body)
    assert exc.value.status_code == 413 and _code(exc) == "chunk_too_large"
    imports.meetings.store.write_segment.assert_not_awaited()


async def test_a_first_chunk_that_is_not_its_format_is_refused(
    imports: MeetingImportService,
) -> None:
    meeting = _meeting(audio_format=MeetingAudioFormat.IMPORT_MP3)
    imports.meetings.repo.get_for_user.return_value = meeting
    with pytest.raises(BaseAPIException) as exc:
        await imports.accept_chunk(meeting.user_id, meeting.id, sequence=0, body=WAV_HEAD)
    assert exc.value.status_code == 415 and _code(exc) == "import_format_mismatch"
    imports.meetings.store.write_segment.assert_not_awaited()


async def test_chunks_adding_up_past_the_size_are_refused(
    imports: MeetingImportService,
) -> None:
    meeting = _meeting(audio_bytes=settings.meetings_import_max_bytes - 4)
    imports.meetings.repo.get_for_user.return_value = meeting
    with pytest.raises(BaseAPIException) as exc:
        await imports.accept_chunk(meeting.user_id, meeting.id, sequence=7, body=b"\x00" * 8)
    assert exc.value.status_code == 413 and _code(exc) == "import_too_large"
    imports.meetings.store.write_segment.assert_not_awaited()


async def test_a_resent_chunk_replaces_its_own_bytes_in_the_total(
    imports: MeetingImportService,
) -> None:
    # The total already counts this chunk's first upload: a retry is not growth.
    meeting = _meeting(audio_bytes=settings.meetings_import_max_bytes - 4)
    imports.meetings.repo.get_for_user.return_value = meeting
    imports.meetings.store.segment_size = AsyncMock(return_value=8)
    imports.meetings.repo.record_segment.return_value = (MeetingStatus.UPLOADING, 8, 100)
    ack = await imports.accept_chunk(meeting.user_id, meeting.id, sequence=7, body=b"\x00" * 8)
    assert ack.status is MeetingStatus.UPLOADING
    imports.meetings.store.write_segment.assert_awaited_once()


def _max_chunks() -> int:
    return -(-settings.meetings_import_max_bytes // settings.meetings_import_chunk_max_bytes)


async def test_a_chunk_numbered_past_what_the_size_allows_never_touches_the_disk(
    imports: MeetingImportService,
) -> None:
    # Without this bound, chunk 10^9 then a completion would make the server
    # list a billion missing chunks.
    meeting = _meeting()
    imports.meetings.repo.get_for_user.return_value = meeting
    with pytest.raises(BaseAPIException) as exc:
        await imports.accept_chunk(meeting.user_id, meeting.id, sequence=_max_chunks(), body=b"x")
    assert exc.value.status_code == 413 and _code(exc) == "import_too_large"
    imports.meetings.store.write_segment.assert_not_awaited()


async def test_a_completion_declaring_more_chunks_than_the_size_allows_is_refused(
    imports: MeetingImportService,
) -> None:
    meeting = _meeting(segment_count=2)
    imports.meetings.repo.get_for_user.return_value = meeting
    imports.meetings.store.list_sequences = AsyncMock(side_effect=AssertionError("not read"))
    with pytest.raises(BaseAPIException) as exc:
        await imports.complete(
            meeting.user_id, meeting.id, MeetingImportComplete(chunk_count=_max_chunks() + 1)
        )
    assert exc.value.status_code == 413 and _code(exc) == "import_too_large"
    imports.meetings.repo.stop.assert_not_awaited()


async def test_an_import_is_complete_only_without_a_missing_chunk(
    imports: MeetingImportService,
) -> None:
    meeting = _meeting(segment_count=3)
    imports.meetings.repo.get_for_user.return_value = meeting
    with pytest.raises(BaseAPIException) as exc:
        await imports.complete(meeting.user_id, meeting.id, MeetingImportComplete(chunk_count=3))
    assert exc.value.status_code == 409 and _code(exc) == "segments_missing"
    imports.meetings.repo.stop.assert_not_awaited()


async def test_a_complete_import_is_handed_to_processing(
    imports: MeetingImportService,
) -> None:
    meeting = _meeting(segment_count=2)
    imports.meetings.repo.get_for_user.return_value = meeting
    imports.meetings.repo.stop.return_value = True
    await imports.complete(meeting.user_id, meeting.id, MeetingImportComplete(chunk_count=2))
    call = imports.meetings.repo.stop.await_args
    assert call.kwargs["segment_count"] == 2
    assert call.kwargs["accepting"] == (MeetingStatus.UPLOADING,)
    # Provisional: the audio stage writes the end once the length is measured.
    assert call.kwargs["stopped_at"] == AT
