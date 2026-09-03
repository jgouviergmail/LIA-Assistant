"""OpenAI transcription client (meetings fallback engine, ADR-258).

Request shaping, payload parsing and the structural classification of HTTP
failures — plus the whole-file call through ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.openai_stt import OpenAISttService

pytestmark = pytest.mark.unit


def _response(
    status: int, payload: Any = None, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=payload,
        headers=headers,
        request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
    )


def test_a_missing_key_is_refused_at_construction() -> None:
    with pytest.raises(STTProviderError) as exc:
        OpenAISttService(api_key="")
    assert exc.value.code == "openai_api_key_missing"


def test_request_data_asks_for_diarized_json_with_auto_chunking_only_when_diarizing() -> None:
    service = OpenAISttService(api_key="k", model="gpt-4o-transcribe-diarize")
    diarized = service._request_data(diarize=True, language="FR")
    assert diarized == {
        "model": "gpt-4o-transcribe-diarize",
        "response_format": "diarized_json",
        "chunking_strategy": "auto",
        "language": "fr",
    }
    plain = service._request_data(diarize=False, language="xx")  # not ISO-639-1 → dropped
    assert plain == {"model": "gpt-4o-transcribe-diarize", "response_format": "json"}


def test_parse_payload_turns_segments_into_speaker_words_and_derives_the_duration() -> None:
    service = OpenAISttService(api_key="k")
    payload = {
        "text": "Bonjour Merci",
        "segments": [
            {"text": " Bonjour ", "start": 0.0, "end": 1.0, "speaker": "A"},
            {"text": "Merci", "start": 1.5, "end": 2.5, "speaker": "B"},
            "garbage",
        ],
    }
    result = service._parse_payload(payload, language="fr")
    assert [(w.text, w.speaker) for w in result.words] == [("Bonjour", "A"), ("Merci", "B")]
    assert result.audio_duration_seconds == 2.5  # no `duration` → last word end
    assert result.diarized is True and result.language_code == "fr"


def test_parse_payload_without_text_is_an_invalid_response() -> None:
    service = OpenAISttService(api_key="k")
    with pytest.raises(STTProviderError) as exc:
        service._parse_payload({"segments": []}, language=None)
    assert exc.value.code == "provider_invalid_response"


@pytest.mark.parametrize(
    ("status", "body", "headers", "code"),
    [
        (429, {"error": {"message": "slow down"}}, {"Retry-After": "7"}, "provider_rate_limited"),
        (401, {"error": {"message": "Incorrect API key provided"}}, None, "invalid_api_key"),
        (
            413,
            {"error": {"message": "Maximum content size limit exceeded"}},
            None,
            "provider_file_too_large",
        ),
        (500, {"error": {"message": "boom"}}, None, "provider_http_error"),
    ],
)
def test_http_failures_are_classified_by_status_never_by_wording(
    status: int, body: Any, headers: dict[str, str] | None, code: str
) -> None:
    with pytest.raises(STTProviderError) as exc:
        OpenAISttService._raise_for_status(_response(status, body, headers))
    assert exc.value.code == code
    if status == 429:
        assert exc.value.retry_after_seconds == 7.0


async def test_transcribe_file_streams_the_file_and_parses_the_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["content_type"] = request.headers.get("content-type", "")
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "text": "Bonjour",
                "duration": 3.0,
                "segments": [{"text": "Bonjour", "start": 0, "end": 1, "speaker": "A"}],
            },
        )

    real_client = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(*args, **kwargs)

    monkeypatch.setattr("src.domains.voice.stt.openai_stt.httpx.AsyncClient", _factory)
    audio = tmp_path / "meeting.webm"
    audio.write_bytes(b"\x1aE\xdf\xa3fake-webm")
    service = OpenAISttService(api_key="sk-test", model="gpt-4o-transcribe-diarize")
    result = await service.transcribe_file_async(
        str(audio), "audio/webm", diarize=True, language="fr", timeout_seconds=5.0
    )
    assert seen["auth"] == "Bearer sk-test"
    assert seen["content_type"].startswith("multipart/form-data")
    assert b"fake-webm" in seen["body"] and b"diarized_json" in seen["body"]
    assert result.text == "Bonjour" and result.audio_duration_seconds == 3.0
    assert result.words[0].speaker == "A" and result.diarized is True


def test_json_payload_rejects_a_non_object_body() -> None:
    with pytest.raises(STTProviderError) as exc:
        OpenAISttService._json_payload(_response(200, ["not", "an", "object"]))
    assert exc.value.code == "provider_invalid_response"
    assert json.loads(_response(200, {"a": 1}).text) == {"a": 1}
