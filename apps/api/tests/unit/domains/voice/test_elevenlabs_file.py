"""ElevenLabs Scribe whole-file transcription (meetings, ADR-258).

The request carries the diarization and word-timestamp flags, the payload is
folded into speaker words, and a key ID stored in place of a key is classified
as a configuration fault — the exact answer measured on 2026-09-02.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from src.domains.voice.stt.elevenlabs_stt import ElevenLabsSttService
from src.domains.voice.stt.exceptions import STTProviderError

pytestmark = pytest.mark.unit


def _service() -> ElevenLabsSttService:
    return ElevenLabsSttService(
        api_key="sk_test",
        model="scribe_v2",
        base_url="https://api.elevenlabs.io/v1",
        timeout_seconds=5.0,
    )


def test_file_request_data_flags_diarization_and_word_timestamps() -> None:
    data = _service()._file_request_data(diarize=True, language="fr")
    assert data == {
        "model_id": "scribe_v2",
        "diarize": "true",
        "timestamps_granularity": "word",
        "tag_audio_events": "false",
        "language_code": "fr",
    }
    assert "language_code" not in _service()._file_request_data(diarize=False, language=None)


def test_parse_file_payload_keeps_words_only_and_maps_speaker_ids() -> None:
    payload = {
        "text": "Bonjour Merci",
        "audio_duration_secs": 12.5,
        "language_code": "fra",
        "words": [
            {
                "text": "Bonjour",
                "start": 0.0,
                "end": 0.8,
                "type": "word",
                "speaker_id": "speaker_0",
            },
            {"text": " ", "start": 0.8, "end": 0.9, "type": "spacing", "speaker_id": "speaker_0"},
            {"text": "Merci", "start": 0.9, "end": 1.4, "type": "word", "speaker_id": "speaker_1"},
            {"text": "(rire)", "start": 1.4, "end": 1.6, "type": "audio_event"},
        ],
    }
    result = _service()._parse_file_payload(payload, diarize=True)
    assert [(w.text, w.speaker) for w in result.words] == [
        ("Bonjour", "speaker_0"),
        ("Merci", "speaker_1"),
    ]
    assert result.audio_duration_seconds == 12.5 and result.language_code == "fra"
    assert result.diarized is True


def test_parse_file_payload_without_duration_is_invalid() -> None:
    with pytest.raises(STTProviderError) as exc:
        _service()._parse_file_payload({"text": "x"}, diarize=False)
    assert exc.value.code == "provider_invalid_response"


def _response(status: int, payload: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=payload,
        headers=headers,
        request=httpx.Request("POST", "https://api.elevenlabs.io/v1/speech-to-text"),
    )


def test_a_key_id_used_as_a_key_is_a_configuration_fault_not_a_retry() -> None:
    body = {"detail": {"status": "api_key_id_used_as_api_key", "message": "An API key ID was used"}}
    with pytest.raises(STTProviderError) as exc:
        ElevenLabsSttService._raise_for_status(_response(400, body))
    assert exc.value.code == "invalid_api_key"


def test_rate_limit_carries_retry_after() -> None:
    with pytest.raises(STTProviderError) as exc:
        ElevenLabsSttService._raise_for_status(
            _response(429, {"detail": "slow"}, {"Retry-After": "3"})
        )
    assert exc.value.code == "provider_rate_limited" and exc.value.retry_after_seconds == 3.0


async def test_transcribe_file_posts_the_file_once_and_folds_the_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("xi-api-key")
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "text": "Bonjour",
                "audio_duration_secs": 2.0,
                "language_code": "fra",
                "words": [
                    {
                        "text": "Bonjour",
                        "start": 0,
                        "end": 1,
                        "type": "word",
                        "speaker_id": "speaker_0",
                    }
                ],
            },
        )

    real_client = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(*args, **kwargs)

    monkeypatch.setattr("src.domains.voice.stt.elevenlabs_stt.httpx.AsyncClient", _factory)
    audio = tmp_path / "meeting.ogg"
    audio.write_bytes(b"OggS-fake")
    result = await _service().transcribe_file_async(
        str(audio), "audio/ogg", diarize=True, language="fr", timeout_seconds=5.0
    )
    assert seen["key"] == "sk_test" and b"OggS-fake" in seen["body"] and b"diarize" in seen["body"]
    assert result.words[0].speaker == "speaker_0" and result.audio_duration_seconds == 2.0


async def test_an_unreadable_file_is_a_classified_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(STTProviderError) as exc:
        await _service().transcribe_file_async(
            str(tmp_path / "missing.webm"),
            "audio/webm",
            diarize=False,
            language=None,
            timeout_seconds=1.0,
        )
    assert exc.value.code == "provider_http_error"
