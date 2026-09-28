"""Gemini TTS speaks the Interactions API shape measured live, and bills its tokens."""

from __future__ import annotations

import array
import base64
import io
import json
import wave
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice import gemini_tts_client as module
from src.domains.voice.billing import UsageReportingTTSClient, synthesize_billed
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.gemini_tts_client import GeminiTTSClient
from src.domains.voice.protocol import TTSClient
from src.infrastructure.observability.metrics_voice import voice_tts_errors_total

pytestmark = pytest.mark.unit

WAV = b"RIFF\x00\x00\x00\x00WAVEfmt fake-samples"


def _answer(
    audio: bytes = WAV,
    *,
    usage: dict[str, int] | None = None,
    mime_type: str = "audio/wav",
) -> dict[str, Any]:
    return {
        "status": "completed",
        "usage": usage or {"total_input_tokens": 20, "total_output_tokens": 158},
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "audio",
                        "mime_type": mime_type,
                        "data": base64.b64encode(audio).decode(),
                    }
                ],
            }
        ],
    }


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        LLMConfigOverrideCache,
        "get_api_key",
        classmethod(lambda cls, provider: "k-test" if provider == "gemini" else None),
    )
    yield


def client_with(
    handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any
) -> GeminiTTSClient:
    return GeminiTTSClient("gemini-tts-model", transport=httpx.MockTransport(handler), **kwargs)


class TestRequestShape:
    async def test_it_posts_the_measured_interactions_shape(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=_answer())

        client = client_with(handler, output_format="wav")
        await client.synthesize("Bonjour.", "Kore", style="warm, lively")
        await client.close()

        request = seen[0]
        assert request.url.path.endswith("/v1beta/interactions")
        assert request.headers["x-goog-api-key"] == "k-test"
        body = json.loads(request.content)
        assert body["model"] == "gemini-tts-model"
        assert body["response_format"] == {"type": "audio"}
        assert body["generation_config"] == {"speech_config": [{"voice": "Kore"}]}
        content = body["input"][0]["content"][0]
        assert content["text"] == "Bonjour."
        assert content["annotations"] == [{"type": "speech_metadata", "style": "warm, lively"}]

    async def test_no_style_sends_no_annotation(self) -> None:
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(200, json=_answer())

        client = client_with(handler, output_format="wav")
        await client.synthesize("Bonjour.", "Puck")
        await client.close()
        assert "annotations" not in seen[0]["input"][0]["content"][0]


class TestResult:
    async def test_it_reports_the_vendor_tokens(self) -> None:
        client = client_with(
            lambda _r: httpx.Response(
                200, json=_answer(usage={"total_input_tokens": 125, "total_output_tokens": 949})
            ),
            output_format="wav",
        )
        result = await client.synthesize_with_usage("x" * 510, "Kore")
        await client.close()
        assert (result.audio, result.characters) == (WAV, 510)
        assert (result.input_tokens, result.output_tokens) == (125, 949)
        assert client.audio_format == "wav"

    async def test_mp3_output_is_transcoded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []

        async def fake_transcode(audio: bytes, **kwargs: Any) -> bytes:
            calls.append({"audio": audio, **kwargs})
            return b"ID3-mp3"

        monkeypatch.setattr(module, "transcode", fake_transcode)
        client = client_with(lambda _r: httpx.Response(200, json=_answer()), mp3_bitrate_kbps=96)
        audio = await client.synthesize("Bonjour.", "Kore")
        await client.close()
        assert audio == b"ID3-mp3"
        assert client.audio_format == "mp3"
        assert calls[0]["audio"] == WAV
        assert calls[0]["output_format"] == "mp3"
        assert "96k" in calls[0]["args"]

    @pytest.mark.parametrize("rate", [24_000, 16_000])
    async def test_raw_samples_are_wrapped_before_anything_reads_them(self, rate: int) -> None:
        """Measured on dev 2026-09-26: the 2.5 previews answer ``audio/L16`` — raw
        little-endian samples, no header — where the 3.8 models answer a WAV; read
        as a WAV they failed every transcode (« audio could not be encoded »)."""
        pcm = array.array("h", [-7, -3, 9_000, 9_000]).tobytes()
        mime = f"audio/L16;codec=pcm;rate={rate}"
        client = client_with(
            lambda _r: httpx.Response(200, json=_answer(pcm, mime_type=mime)),
            output_format="wav",
        )
        audio = await client.synthesize("Bonjour.", "Kore")
        await client.close()
        with wave.open(io.BytesIO(audio)) as reader:
            assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (
                1,
                2,
                rate,
            )
            assert reader.readframes(reader.getnframes()) == pcm

    @pytest.mark.parametrize("mime", ["audio/L16;codec=pcm;rate=0", "audio/L16;codec=pcm"])
    async def test_raw_samples_without_a_usable_rate_are_read_at_the_vendors_rate(
        self, mime: str
    ) -> None:
        """A rate of 0 would make the container writer raise outside the client's
        own error: the samples are read at the rate the vendor documents instead."""
        pcm = array.array("h", [5, 6]).tobytes()
        client = client_with(
            lambda _r: httpx.Response(200, json=_answer(pcm, mime_type=mime)),
            output_format="wav",
        )
        audio = await client.synthesize("Bonjour.", "Kore")
        await client.close()
        with wave.open(io.BytesIO(audio)) as reader:
            assert reader.getframerate() == 24_000

    async def test_raw_samples_reach_the_transcoder_as_a_wav(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        received: list[bytes] = []

        async def fake_transcode(audio: bytes, **kwargs: Any) -> bytes:
            received.append(audio)
            return b"ID3-mp3"

        monkeypatch.setattr(module, "transcode", fake_transcode)
        pcm = array.array("h", [1, 2, 3]).tobytes()
        answer = _answer(pcm, mime_type="audio/L16;codec=pcm;rate=24000")
        client = client_with(lambda _r: httpx.Response(200, json=answer))
        assert await client.synthesize("Bonjour.", "Kore") == b"ID3-mp3"
        await client.close()
        assert received[0][:4] == b"RIFF"

    async def test_base64_surface(self) -> None:
        client = client_with(lambda _r: httpx.Response(200, json=_answer()), output_format="wav")
        encoded = await client.synthesize_base64("Bonjour.", "Kore")
        await client.close()
        assert base64.b64decode(encoded) == WAV

    async def test_it_satisfies_both_protocols(self) -> None:
        client = client_with(lambda _r: httpx.Response(200, json=_answer()), output_format="wav")
        assert isinstance(client, TTSClient)
        assert isinstance(client, UsageReportingTTSClient)
        result = await synthesize_billed(client, "Bonjour.", "Kore")
        await client.close()
        assert result.output_tokens == 158


class TestFailures:
    @pytest.mark.parametrize(
        ("response", "code"),
        [
            (
                httpx.Response(429, headers={"Retry-After": "7"}, text="slow down"),
                "provider_rate_limited",
            ),
            (httpx.Response(500, text="boom"), "provider_http_error"),
            (httpx.Response(200, text="not json"), "provider_invalid_response"),
            (httpx.Response(200, json={"steps": []}), "provider_invalid_response"),
        ],
    )
    async def test_vendor_failures_carry_a_stable_code(
        self, response: httpx.Response, code: str
    ) -> None:
        client = client_with(lambda _r: response, output_format="wav")
        with pytest.raises(TTSProviderError) as caught:
            await client.synthesize("Bonjour.", "Kore")
        await client.close()
        assert caught.value.code == code
        if code == "provider_rate_limited":
            assert caught.value.retry_after_seconds == 7.0

    async def test_an_error_carries_the_vendor_status_never_its_prose(self) -> None:
        body = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "text: my words"}}
        client = client_with(lambda _r: httpx.Response(400, json=body), output_format="wav")
        with pytest.raises(TTSProviderError) as caught:
            await client.synthesize("my words", "Kore")
        await client.close()
        assert "INVALID_ARGUMENT" in str(caught.value)
        assert "my words" not in str(caught.value)
        assert isinstance(caught.value.details, dict)
        assert caught.value.details["vendor_status"] == "INVALID_ARGUMENT"

    async def test_an_interactions_refusal_is_logged_by_its_facts(self) -> None:
        """Measured on dev 2026-09-26: the Interactions API names its refusal in
        ``error.code`` — read as « unknown » and logged nowhere, a radio refused on
        every line left no trace but its music."""
        body = {
            "error": {
                "code": "invalid_request",
                "message": "Speech annotations are not supported for model 'm'.",
            }
        }
        client = client_with(lambda _r: httpx.Response(400, json=body), output_format="wav")
        with capture_logs() as logs, pytest.raises(TTSProviderError) as caught:
            await client.synthesize("Bonjour.", "Kore", style="Speak warmly.")
        await client.close()

        assert caught.value.code == "provider_http_error"
        assert caught.value.details == {"status_code": 400, "vendor_status": "invalid_request"}
        [entry] = [log for log in logs if log["event"] == "gemini_tts_http_error"]
        assert (entry["model"], entry["status_code"], entry["vendor_status"]) == (
            "gemini-tts-model",
            400,
            "invalid_request",
        )
        assert "annotations" not in json.dumps(entry, default=str)  # the prose stays out

    @pytest.mark.parametrize(
        "error",
        [
            {"code": "Speech annotations are not supported"},  # prose, not a code
            {"code": 400},
            {"message": "no code at all"},
            "not an object",
        ],
    )
    async def test_an_error_that_names_no_bounded_code_reads_unknown(self, error: object) -> None:
        client = client_with(
            lambda _r: httpx.Response(400, json={"error": error}), output_format="wav"
        )
        with pytest.raises(TTSProviderError) as caught:
            await client.synthesize("Bonjour.", "Kore")
        await client.close()
        assert isinstance(caught.value.details, dict)
        assert caught.value.details["vendor_status"] == "unknown"

    async def test_an_answer_without_audio_is_counted_and_says_what_was_billed(self) -> None:
        """Never observed live; should it happen, the vendor's count is seen, never lost."""
        body = {
            "status": "completed",
            "usage": {"total_input_tokens": 3, "total_output_tokens": 0},
            "steps": [],
        }
        errors = voice_tts_errors_total.labels(error_type="empty_response", voice_name="Kore")
        before = errors._value.get()
        client = client_with(lambda _r: httpx.Response(200, json=body), output_format="wav")
        with capture_logs() as logs, pytest.raises(TTSProviderError) as caught:
            await client.synthesize("Bonjour.", "Kore")
        await client.close()

        assert caught.value.code == "provider_invalid_response"
        assert caught.value.details == {"input_tokens": 3, "output_tokens": 0}
        [entry] = [log for log in logs if log["event"] == "gemini_tts_no_audio"]
        assert (entry["input_tokens"], entry["output_tokens"]) == (3, 0)
        assert errors._value.get() == before + 1

    async def test_a_missing_usage_report_bills_characters_never_nothing(self) -> None:
        answer = _answer()
        answer["usage"] = {}
        client = client_with(lambda _r: httpx.Response(200, json=answer), output_format="wav")
        result = await client.synthesize_with_usage("Bonjour.", "Kore")
        await client.close()
        assert (result.input_tokens, result.output_tokens) == (None, None)
        assert result.characters == 8

    async def test_a_timeout_and_a_transport_error_are_told_apart(self) -> None:
        def timeout(_r: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow")

        def broken(_r: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        for handler, code in ((timeout, "provider_timeout"), (broken, "provider_network_error")):
            client = client_with(handler, output_format="wav")
            with pytest.raises(TTSProviderError) as caught:
                await client.synthesize("Bonjour.", "Kore")
            await client.close()
            assert caught.value.code == code

    async def test_a_voice_is_required(self) -> None:
        client = client_with(lambda _r: httpx.Response(200, json=_answer()))
        with pytest.raises(TTSProviderError, match="voice"):
            await client.synthesize("Bonjour.", None)
        await client.close()

    def test_no_key_no_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, p: None))
        with pytest.raises(TTSProviderError) as caught:
            GeminiTTSClient("gemini-tts-model")
        assert caught.value.code == "api_key_missing"

    async def test_close_twice_is_harmless(self) -> None:
        client = client_with(lambda _r: httpx.Response(200, json=_answer()))
        await client.close()
        await client.close()
