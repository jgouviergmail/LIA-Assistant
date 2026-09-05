"""The job resumes from what it already acquired (ADR-258, amended 2026-09-05).

Measured in production on 2026-09-05: a transcription had been paid and the
minutes failed; the next attempt found the segments purged, nothing persisted,
and re-ran ffmpeg on nothing. A stage now writes a CHECKPOINT on the claimed
row as soon as it is acquired, and a claim reads the checkpoints before
spending anything again: the normalized audio is reused when it exists, the
transcript is reused when it exists, and a meeting with no audio at all is
dead-lettered as ``audio_unavailable`` instead of burning its retry budget.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.security.utils import encrypt_data
from src.domains.meetings import processing
from src.domains.meetings.error_codes import ERROR_AUDIO_UNAVAILABLE
from src.domains.meetings.models import MeetingAudioFormat, MeetingStage, MeetingSttProvider
from src.domains.meetings.processing import (
    LeaseLostError,
    _acquire_audio,
    _acquire_transcript,
    _completion_values,
    _Job,
)
from src.domains.meetings.schemas import TranscriptTurn
from src.domains.meetings.transcription import TranscriptionOutcome, outcome_from_row
from src.infrastructure.observability.metrics_meetings import meeting_stt_audio_seconds_total

pytestmark = pytest.mark.unit

TURNS = [
    TranscriptTurn(speaker="speaker_0", start=0.0, end=9.0, text="Bonjour."),
    TranscriptTurn(speaker="speaker_1", start=9.5, end=19.0, text="Bonjour à vous."),
]


def _row(**overrides: Any) -> SimpleNamespace:
    row = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        audio_format=MeetingAudioFormat.PCM_S16LE_16,
        segment_count=2,
        audio_path=None,
        audio_duration_seconds=None,
        audio_gaps=0,
        transcript_encrypted=None,
        transcript_deleted_at=None,
        stt_provider=None,
        stt_model=None,
        stt_detected_language=None,
        stt_diarized=False,
        stt_audio_seconds=None,
        stt_cost_eur=None,
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def _outcome(**overrides: Any) -> TranscriptionOutcome:
    values: dict[str, Any] = {
        "turns": TURNS,
        "language_code": "fr",
        "audio_duration_seconds": 33.0,
        "provider": MeetingSttProvider.ELEVENLABS,
        "model": "scribe_v2",
        "diarized": True,
        "cost_usd": 0.002,
        "cost_eur": 0.0017,
    }
    values.update(overrides)
    return TranscriptionOutcome(**values)


def _job(tmp_path: Path, *, normalized_exists: bool) -> _Job:
    job = _Job(uuid.uuid4())
    store = MagicMock()
    normalized = tmp_path / "audio.webm"
    if normalized_exists:
        normalized.write_bytes(b"opus")
    store.absolute = MagicMock(return_value=normalized)
    store.relative = MagicMock(return_value="user/meeting/audio.webm")
    store.list_sequences = AsyncMock(return_value=[0, 1])
    store.missing_sequences = MagicMock(return_value=[])
    store.total_segment_bytes = AsyncMock(return_value=1_056_768)
    store.normalize = AsyncMock(return_value=(normalized, 33.0))
    store.purge_segments = AsyncMock(return_value=2)
    job.store = store
    return job


# ------------------------------------------------------------ outcome_from_row


def test_outcome_from_row_rebuilds_the_transcription_from_the_checkpoint() -> None:
    row = _row(
        transcript_encrypted=encrypt_data(json.dumps([t.model_dump() for t in TURNS])),
        stt_provider=MeetingSttProvider.ELEVENLABS,
        stt_model="scribe_v2",
        stt_detected_language="fr",
        stt_diarized=True,
        stt_audio_seconds=33.0,
        stt_cost_eur=0.0017,
    )
    outcome = outcome_from_row(row)
    assert outcome is not None
    assert outcome.turns == TURNS
    assert outcome.provider is MeetingSttProvider.ELEVENLABS
    assert outcome.model == "scribe_v2"
    assert outcome.language_code == "fr"
    assert outcome.diarized is True
    assert outcome.audio_duration_seconds == 33.0
    assert outcome.cost_eur == 0.0017
    # The USD figure is not stored: an absent price is not a zero one.
    assert outcome.cost_usd is None


def test_outcome_from_row_is_none_without_a_transcript_or_after_its_deletion() -> None:
    assert outcome_from_row(_row()) is None
    deleted = _row(transcript_encrypted="cipher", transcript_deleted_at=object())
    assert outcome_from_row(deleted) is None


# --------------------------------------------------------------- acquire audio


async def test_a_normalized_file_on_the_row_is_reused_without_ffmpeg(tmp_path: Path) -> None:
    job = _job(tmp_path, normalized_exists=True)
    repo = AsyncMock()
    repo.heartbeat.return_value = True
    row = _row(audio_path="user/meeting/audio.webm", audio_duration_seconds=33.0, audio_gaps=1)

    acquired = await _acquire_audio(job, repo, row)

    assert acquired == ("user/meeting/audio.webm", 33.0, 1)
    job.store.normalize.assert_not_awaited()
    repo.fail_permanently.assert_not_awaited()


async def test_a_fresh_normalization_is_checkpointed_on_the_claimed_row(tmp_path: Path) -> None:
    job = _job(tmp_path, normalized_exists=False)
    repo = AsyncMock()
    repo.heartbeat.return_value = True
    row = _row()

    acquired = await _acquire_audio(job, repo, row)

    assert acquired == ("user/meeting/audio.webm", 33.0, 0)
    job.store.normalize.assert_awaited_once()
    job.store.purge_segments.assert_awaited_once()
    values = repo.heartbeat.await_args.kwargs["values"]
    assert values == {
        "audio_path": "user/meeting/audio.webm",
        "audio_duration_seconds": 33.0,
        "audio_gaps": 0,
    }
    assert repo.heartbeat.await_args.kwargs["worker_id"] == job.worker_id


async def test_a_checkpoint_whose_file_is_gone_falls_back_to_the_segments(
    tmp_path: Path,
) -> None:
    job = _job(tmp_path, normalized_exists=False)
    repo = AsyncMock()
    repo.heartbeat.return_value = True
    row = _row(audio_path="user/meeting/audio.webm", audio_duration_seconds=33.0)

    acquired = await _acquire_audio(job, repo, row)

    assert acquired is not None
    job.store.normalize.assert_awaited_once()


async def test_no_audio_anywhere_is_dead_lettered_as_audio_unavailable(tmp_path: Path) -> None:
    job = _job(tmp_path, normalized_exists=False)
    job.store.list_sequences = AsyncMock(return_value=[])
    repo = AsyncMock()
    row = _row()

    acquired = await _acquire_audio(job, repo, row)

    assert acquired is None
    job.store.normalize.assert_not_awaited()
    repo.fail_permanently.assert_awaited_once()
    assert repo.fail_permanently.await_args.kwargs["code"] == ERROR_AUDIO_UNAVAILABLE


async def test_a_lost_lease_at_the_audio_checkpoint_aborts(tmp_path: Path) -> None:
    job = _job(tmp_path, normalized_exists=False)
    repo = AsyncMock()
    repo.heartbeat.return_value = False
    with pytest.raises(LeaseLostError):
        await _acquire_audio(job, repo, _row())


# ---------------------------------------------------------- acquire transcript


async def test_a_transcript_on_the_row_is_reused_and_not_billed_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job(tmp_path, normalized_exists=True)
    job.stage = MeetingStage.TRANSCRIBING
    repo = AsyncMock()
    repo.heartbeat.return_value = True
    transcribe = AsyncMock()
    monkeypatch.setattr(processing, "transcribe_with_fallback", transcribe)
    row = _row(
        transcript_encrypted=encrypt_data(json.dumps([t.model_dump() for t in TURNS])),
        stt_provider=MeetingSttProvider.OPENAI,
        stt_model="gpt-4o-transcribe-diarize",
        stt_audio_seconds=33.0,
    )
    counter = meeting_stt_audio_seconds_total.labels(provider="openai")
    before = counter._value.get()

    outcome = await _acquire_transcript(
        job,
        repo,
        row,
        engine_preference=MagicMock(),
        audio_path="user/meeting/audio.webm",
        duration=33.0,
        language_hint=None,
    )

    assert outcome.turns == TURNS
    assert outcome.provider is MeetingSttProvider.OPENAI
    transcribe.assert_not_awaited()
    assert counter._value.get() == before


async def test_a_fresh_transcription_is_checkpointed_encrypted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job(tmp_path, normalized_exists=True)
    job.stage = MeetingStage.TRANSCRIBING
    repo = AsyncMock()
    repo.heartbeat.return_value = True
    fresh = _outcome()
    monkeypatch.setattr(processing, "transcribe_with_fallback", AsyncMock(return_value=fresh))
    monkeypatch.setattr(processing, "encrypt_data", lambda text: f"enc:{text}")
    counter = meeting_stt_audio_seconds_total.labels(provider="elevenlabs")
    before = counter._value.get()

    outcome = await _acquire_transcript(
        job,
        repo,
        _row(),
        engine_preference=MagicMock(),
        audio_path="user/meeting/audio.webm",
        duration=33.0,
        language_hint="fr",
    )

    assert outcome is fresh
    assert counter._value.get() == before + 33.0
    values = repo.heartbeat.await_args.kwargs["values"]
    assert values["transcript_encrypted"].startswith("enc:")
    assert json.loads(values["transcript_encrypted"][4:]) == [t.model_dump() for t in TURNS]
    assert values["transcript_deleted_at"] is None
    assert values["stt_provider"] is MeetingSttProvider.ELEVENLABS
    assert values["stt_model"] == "scribe_v2"
    assert values["stt_detected_language"] == "fr"
    assert values["stt_diarized"] is True
    assert values["stt_audio_seconds"] == 33.0
    assert values["stt_cost_eur"] == 0.0017


def test_completion_values_carry_the_same_checkpoint_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One builder per checkpoint, reused by completion: a column cannot drift between them."""
    monkeypatch.setattr(processing, "encrypt_data", lambda text: f"enc:{text}")
    outcome = _outcome()
    values = _completion_values(
        meeting=_row(calendar_event_id=None, calendar_provider=None),
        audio_path="user/meeting/audio.webm",
        duration=33.0,
        outcome=outcome,
        synthesis=MagicMock(
            report=MagicMock(model_dump=MagicMock(return_value={"title": "t"})),
            usage=SimpleNamespace(
                model_name="m", tokens_in=1, tokens_out=1, tokens_cache=0, cost_usd=None
            ),
        ),
        decision=SimpleNamespace(
            sections=[],
            ref="builtin:default_minutes",
            name="Minutes",
            selection=MagicMock(value="user"),
            reason=None,
        ),
        calendar=None,
        location_label=None,
        keep_audio_until=None,
        gaps=0,
    )
    assert values["audio_path"] == "user/meeting/audio.webm"
    assert values["stt_provider"] is MeetingSttProvider.ELEVENLABS
    assert values["transcript_encrypted"].startswith("enc:")
