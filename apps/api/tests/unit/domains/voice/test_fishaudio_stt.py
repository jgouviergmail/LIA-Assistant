"""Fish Audio speech-to-text (``POST /v1/asr``): the request, the answer, the refusals (ADR-345).

Every shape is the vendor's documentation (read 2026-10-14); no paid
transcription was run (owner decision). No test here reaches the network.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.domains.voice.stt import fishaudio_stt as module
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.fishaudio_stt import FishAudioSttService
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit

Respond = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    yield from fresh_module_logger(module)


@pytest.fixture(autouse=True)
def free_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def slot(provider: str, api_key: str, *, timeout_seconds: float) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(module, "provider_slot", slot)


def service(respond: Respond, model: str = "transcribe-1-pro") -> FishAudioSttService:
    return FishAudioSttService(
        "fish-key", model, timeout_seconds=5.0, http_transport=httpx.MockTransport(respond)
    )


def answering(payload: dict[str, Any], sent: list[httpx.Request]) -> Respond:
    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=payload)

    return respond


def fields(request: httpx.Request) -> dict[str, str]:
    """The text fields of a multipart request (the audio part left out)."""
    body = request.content.decode("latin-1")
    out: dict[str, str] = {}
    for part in body.split("--")[1:]:
        header, _, value = part.partition("\r\n\r\n")
        if 'name="' in header and "filename=" not in header:
            name = header.split('name="', 1)[1].split('"', 1)[0]
            out[name] = value.rstrip("\r\n-")
    return out


class TestTheVoiceModeClip:
    async def test_it_names_its_model_sends_wav_and_keeps_the_words_alone(self) -> None:
        sent: list[httpx.Request] = []
        stt = service(
            answering(
                {"text": "<|speaker:0|> Bonjour,  à demain.", "duration": 2.2, "segments": []},
                sent,
            )
        )

        result = await stt.transcribe_pcm_int16_async(b"\x00\x01" * 16000, language="fr")

        (request,) = sent
        assert request.url.path == "/v1/asr"
        assert request.headers["model"] == "transcribe-1-pro"
        assert request.headers["Authorization"] == "Bearer fish-key"
        assert b'filename="audio.wav"' in request.content and b"RIFF" in request.content
        assert fields(request) == {
            "ignore_timestamps": "true",
            "language": "fr",
            "tag_audio_events": "false",
            "diarize": "false",
        }
        assert result.text == "Bonjour, à demain."
        # The vendor bills the duration rounded UP to the second.
        assert result.audio_duration_seconds == 3.0

    async def test_the_pro_fields_are_sent_to_the_pro_model_alone(self) -> None:
        sent: list[httpx.Request] = []
        stt = service(
            answering({"text": "Oui.", "duration": 1.0, "segments": []}, sent), "transcribe-1"
        )

        await stt.transcribe_pcm_int16_async(b"\x00\x01" * 800, language="en-US")

        assert fields(sent[0]) == {"ignore_timestamps": "true"}

    async def test_nothing_to_transcribe_calls_nobody(self) -> None:
        sent: list[httpx.Request] = []

        result = await service(answering({}, sent)).transcribe_pcm_int16_async(b"")

        assert sent == [] and result.text == "" and result.audio_duration_seconds == 0.0


class TestTheMeetingFile:
    async def test_the_pro_model_answers_its_speaker_turns(self, tmp_path: Path) -> None:
        audio = tmp_path / "meeting.ogg"
        audio.write_bytes(b"OggS-recording")
        sent: list[httpx.Request] = []
        payload = {
            "text": "<|speaker:0|> Bonjour. <|speaker:1|> Salut.",
            "duration": 6.4,
            "segments": [{"text": "Bonjour", "start": 0.2, "end": 0.8}],
            "speaker_turns": [
                {"speaker": "speaker:0", "text": "Bonjour.", "start": 0.2, "end": 0.8},
                {"speaker": "speaker:1", "text": "Salut.", "start": 1.6, "end": 2.1},
            ],
            "language_code": "fr",
        }

        result = await service(answering(payload, sent)).transcribe_file_async(
            str(audio), "audio/ogg", diarize=True, language=None, timeout_seconds=30.0
        )

        assert fields(sent[0])["ignore_timestamps"] == "false"
        assert fields(sent[0])["diarize"] == "true"
        assert [(w.speaker, w.text, w.start) for w in result.words] == [
            ("speaker:0", "Bonjour.", 0.2),
            ("speaker:1", "Salut.", 1.6),
        ]
        assert result.diarized and result.language_code == "fr"
        assert result.text == "Bonjour. Salut."
        assert result.audio_duration_seconds == 7.0

    async def test_a_model_that_marks_no_speaker_answers_timed_words(self, tmp_path: Path) -> None:
        audio = tmp_path / "meeting.ogg"
        audio.write_bytes(b"OggS")
        payload = {
            "text": "Bonjour à tous",
            "duration": 2.0,
            "segments": [
                {"text": "Bonjour", "start": 0.0, "end": 0.5},
                {"text": "à", "start": 0.5, "end": 0.6},
            ],
        }

        result = await service(answering(payload, []), "transcribe-1").transcribe_file_async(
            str(audio), "audio/ogg", diarize=True, language="fr", timeout_seconds=30.0
        )

        assert [w.text for w in result.words] == ["Bonjour", "à"]
        assert not result.diarized

    async def test_a_timed_entry_keeps_its_words_alone(self, tmp_path: Path) -> None:
        # The pro model writes its speaker markers inside the text it times too:
        # an entry holding nothing else is no word at all.
        audio = tmp_path / "meeting.ogg"
        audio.write_bytes(b"OggS")
        payload = {
            "text": "<|speaker:0|> Bonjour",
            "duration": 1.0,
            "segments": [
                {"text": "<|speaker:0|>", "start": 0.0, "end": 0.1},
                {"text": "<|speaker:0|> Bonjour", "start": 0.1, "end": 0.6},
            ],
        }

        result = await service(answering(payload, [])).transcribe_file_async(
            str(audio), "audio/ogg", diarize=False, language=None, timeout_seconds=30.0
        )

        assert [(w.text, w.start) for w in result.words] == [("Bonjour", 0.1)]

    async def test_a_refused_file_is_classified_and_released(self, tmp_path: Path) -> None:
        audio = tmp_path / "meeting.ogg"
        audio.write_bytes(b"OggS")

        with pytest.raises(STTProviderError) as raised:
            await service(refusing(402, {"status": 402})).transcribe_file_async(
                str(audio), "audio/ogg", diarize=True, language=None, timeout_seconds=30.0
            )

        assert raised.value.code == "provider_payment_required"
        audio.unlink()  # the handle is closed: the meeting's file can go

    async def test_an_unreadable_file_is_its_own_failure(self, tmp_path: Path) -> None:
        sent: list[httpx.Request] = []

        with pytest.raises(STTProviderError) as raised:
            await service(answering({}, sent)).transcribe_file_async(
                str(tmp_path / "gone.ogg"),
                "audio/ogg",
                diarize=False,
                language=None,
                timeout_seconds=30.0,
            )

        assert raised.value.code == "provider_http_error" and sent == []


def refusing(status: int, body: object = None, headers: dict[str, str] | None = None) -> Respond:
    def respond(request: httpx.Request) -> httpx.Response:
        content = json.dumps(body).encode() if body is not None else b"edge says no"
        return httpx.Response(status, content=content, headers=headers or {})

    return respond


class TestTheRefusals:
    @pytest.mark.parametrize(
        ("status", "body", "code"),
        [
            (429, {"status": 429, "message": "slow down"}, "provider_rate_limited"),
            (401, {"status": 401, "message": "bad key"}, "invalid_api_key"),
            (402, {"status": 402, "message": "no credit"}, "provider_payment_required"),
            (413, None, "provider_file_too_large"),
            (
                400,
                {"status": 400, "code": "audio_too_long", "message": "the words « secret »"},
                "provider_file_too_large",
            ),
            (503, None, "provider_http_error"),
        ],
    )
    async def test_a_refusal_is_classified_by_its_facts_never_its_body(
        self, status: int, body: object, code: str
    ) -> None:
        with pytest.raises(STTProviderError) as raised:
            await service(refusing(status, body)).transcribe_pcm_int16_async(b"\x00\x01" * 800)

        assert raised.value.code == code
        assert "secret" not in repr((raised.value.message, raised.value.details))

    @pytest.mark.parametrize(
        "body",
        [b"not json", json.dumps({"duration": 1.0}).encode(), json.dumps({"text": "x"}).encode()],
    )
    async def test_an_answer_without_its_text_or_duration_is_invalid(self, body: bytes) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)

        with pytest.raises(STTProviderError) as raised:
            await service(respond).transcribe_pcm_int16_async(b"\x00\x01" * 800)

        assert raised.value.code == "provider_invalid_response"

    async def test_a_timeout_is_a_timeout(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        with pytest.raises(STTProviderError) as raised:
            await service(respond).transcribe_pcm_int16_async(b"\x00\x01" * 800)

        assert raised.value.code == "provider_timeout"

    def test_no_key_is_its_own_code(self) -> None:
        with pytest.raises(STTProviderError) as raised:
            FishAudioSttService("")

        assert raised.value.code == "fishaudio_api_key_missing"
