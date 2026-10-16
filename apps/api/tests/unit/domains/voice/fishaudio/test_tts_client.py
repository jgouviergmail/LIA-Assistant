"""The Fish Audio speech client: the request it sends, what it returns, how it fails.

Every shape here was MEASURED on ``s2.1-pro-free`` before it was written
(2026-10-13): the ``model`` header picks the engine (a missing or unknown one is
served AND billed as ``s2.1-pro``), ``pcm`` is raw 16-bit mono at the requested
rate, a refusal is ``{"message", "status"}`` with an ``x-fish-error-code``
header, a 429 carries no ``Retry-After``, and the speaking rate is bounded to
[0.5, 2.0]. No test here reaches the network.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Any

import aiohttp
import httpx
import pytest
from structlog.testing import capture_logs

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.audio_output import mix_audio_format
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.fishaudio import tts_client as module
from src.domains.voice.fishaudio.tts_client import FishAudioTTSClient
from src.domains.voice.protocol import RawAudioSpec
from src.domains.voice.provider_capacity import ProviderCapacityUnavailable
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    yield from fresh_module_logger(module)


@pytest.fixture(autouse=True)
def fish_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        LLMConfigOverrideCache,
        "get_api_key",
        classmethod(lambda cls, provider: "fish-key" if provider == "fishaudio" else None),
    )


@pytest.fixture(autouse=True)
def slots(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, float]]:
    """Record every account slot the client takes (the real gate is proven on Redis)."""
    taken: list[tuple[str, str, float]] = []

    @asynccontextmanager
    async def recording(
        provider: str, api_key: str, *, timeout_seconds: float
    ) -> AsyncIterator[None]:
        taken.append((provider, api_key, timeout_seconds))
        yield

    monkeypatch.setattr(module, "provider_slot", recording)
    return taken


def client_with(
    respond: Callable[[httpx.Request], httpx.Response], **options: Any
) -> FishAudioTTSClient:
    return FishAudioTTSClient(
        model=options.pop("model", "s2.1-pro-free"),
        http_transport=httpx.MockTransport(respond),
        **options,
    )


def recording(
    sent: list[httpx.Request], content: bytes = b"ID3audio"
) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, content=content)

    return respond


def body_of(request: httpx.Request) -> dict[str, Any]:
    payload = json.loads(request.content)
    assert isinstance(payload, dict)
    return payload


class TestTheRequest:
    async def test_it_names_the_model_the_voice_and_the_container(self) -> None:
        sent: list[httpx.Request] = []
        client = client_with(recording(sent))
        try:
            audio = await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert audio == b"ID3audio"
        (request,) = sent
        assert (request.method, request.url.path) == ("POST", "/v1/tts")
        assert request.headers["authorization"] == "Bearer fish-key"
        assert request.headers["model"] == "s2.1-pro-free"
        assert body_of(request) == {
            "text": "Bonjour.",
            "reference_id": "voice-id",
            "format": "mp3",
            "sample_rate": 44100,
            "mp3_bitrate": 128,
        }

    async def test_pcm_is_raw_samples_at_the_configured_rate(self) -> None:
        sent: list[httpx.Request] = []
        client = client_with(recording(sent, b"\x00\x01" * 4), output_format="pcm_24000")
        try:
            await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert body_of(sent[0]) == {
            "text": "Bonjour.",
            "reference_id": "voice-id",
            "format": "pcm",
            "sample_rate": 24000,
        }
        assert client.audio_format == "pcm"
        assert client.raw_audio_spec == RawAudioSpec(24000)
        assert mix_audio_format(client) == "wav"

    @pytest.mark.parametrize("bitrate", [64, 128, 192])
    async def test_an_mp3_bitrate_is_the_one_configured(self, bitrate: int) -> None:
        sent: list[httpx.Request] = []
        client = client_with(recording(sent), output_format=f"mp3_44100_{bitrate}")
        try:
            await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert body_of(sent[0])["mp3_bitrate"] == bitrate
        assert client.raw_audio_spec is None
        assert client.audio_format == "mp3"

    async def test_an_unknown_container_is_the_default_and_is_said(self) -> None:
        sent: list[httpx.Request] = []
        with capture_logs() as logs:
            client = client_with(recording(sent), output_format="flac_96000")
        try:
            await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert body_of(sent[0])["format"] == "mp3"
        assert [entry["event"] for entry in logs] == ["fishaudio_output_format_unknown"]

    @pytest.mark.parametrize("latency", ["normal", "balanced", "low"])
    async def test_a_latency_is_sent_when_configured(self, latency: str) -> None:
        sent: list[httpx.Request] = []
        client = client_with(recording(sent), latency=latency)
        try:
            await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert body_of(sent[0])["latency"] == latency

    async def test_an_unknown_latency_is_never_sent(self) -> None:
        sent: list[httpx.Request] = []
        with capture_logs() as logs:
            client = client_with(recording(sent), latency="instant")
        try:
            await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert "latency" not in body_of(sent[0])
        assert [entry["event"] for entry in logs] == ["fishaudio_latency_unknown"]

    @pytest.mark.parametrize(
        ("configured", "per_call", "sent_speed"),
        [
            (None, None, None),
            (0.9, None, 0.9),
            (0.9, 1.1, 1.1),
            (None, 5.0, 2.0),
            (None, 0.1, 0.5),
            (3.0, None, 2.0),
        ],
    )
    async def test_the_speaking_rate_is_bounded_to_what_the_vendor_accepts(
        self, configured: float | None, per_call: float | None, sent_speed: float | None
    ) -> None:
        """A rate outside [0.5, 2.0] is a 422 for the whole line: it is repaired, never sent."""
        sent: list[httpx.Request] = []
        client = client_with(recording(sent), speed=configured)
        kwargs: dict[str, Any] = {} if per_call is None else {"speed": per_call}
        try:
            await client.synthesize("Bonjour.", "voice-id", **kwargs)
        finally:
            await client.close()
        prosody = body_of(sent[0]).get("prosody")
        assert prosody == (None if sent_speed is None else {"speed": sent_speed})

    async def test_controls_of_other_engines_are_ignored(self) -> None:
        sent: list[httpx.Request] = []
        client = client_with(recording(sent))
        try:
            await client.synthesize(
                "Bonjour.", "voice-id", voice_settings={"stability": 0.3}, style="warm"
            )
        finally:
            await client.close()
        assert set(body_of(sent[0])) == {
            "text",
            "reference_id",
            "format",
            "sample_rate",
            "mp3_bitrate",
        }

    async def test_a_voice_is_required_and_nothing_is_sent_without_one(self) -> None:
        sent: list[httpx.Request] = []
        client = client_with(recording(sent))
        try:
            with pytest.raises(TTSProviderError) as caught:
                await client.synthesize("Bonjour.", None)
        finally:
            await client.close()
        assert caught.value.code == "voice_missing"
        assert sent == []


class TestTheAccount:
    async def test_every_request_takes_a_slot_of_the_account(
        self, slots: list[tuple[str, str, float]]
    ) -> None:
        client = client_with(recording([]), timeout_seconds=12.0)
        try:
            await client.synthesize("Un.", "voice-id")
            await client.synthesize("Deux.", "voice-id")
        finally:
            await client.close()
        assert slots == [("fishaudio", "fish-key", 12.0)] * 2

    async def test_an_unreservable_slot_is_a_network_failure_and_sends_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        @asynccontextmanager
        async def refused(*_: object, **__: object) -> AsyncIterator[None]:
            raise ProviderCapacityUnavailable("fishaudio")
            yield  # pragma: no cover - the generator shape

        monkeypatch.setattr(module, "provider_slot", refused)
        sent: list[httpx.Request] = []
        client = client_with(recording(sent))
        try:
            with pytest.raises(TTSProviderError) as caught:
                await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert caught.value.code == "provider_network_error"
        assert caught.value.details == {"stage": "capacity_reservation"}
        assert caught.value.transient
        assert sent == []

    def test_no_key_no_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: None)
        )
        with pytest.raises(TTSProviderError) as caught:
            FishAudioTTSClient(model="s2.1-pro-free")
        assert caught.value.code == "api_key_missing"


class TestAFailure:
    @pytest.mark.parametrize(
        ("status", "code", "transient", "rate_limited"),
        [
            (400, "provider_http_error", False, False),
            (401, "provider_http_error", False, False),
            (402, "provider_http_error", False, False),
            (404, "provider_http_error", False, False),
            (429, "provider_rate_limited", True, True),
            (500, "provider_http_error", True, False),
            (503, "provider_http_error", True, False),
        ],
    )
    async def test_a_refusal_is_classified_by_its_status(
        self, status: int, code: str, transient: bool, rate_limited: bool
    ) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status,
                json={"message": "refused « the words of the line »", "status": status},
                headers={"x-fish-error-code": "invalid_api_key"},
            )

        client = client_with(respond)
        with capture_logs() as logs:
            try:
                with pytest.raises(TTSProviderError) as caught:
                    await client.synthesize("the words of the line", "voice-id")
            finally:
                await client.close()
        error = caught.value
        assert (error.code, error.transient, error.rate_limited) == (code, transient, rate_limited)
        assert error.details == {"status_code": status, "vendor_code": "invalid_api_key"}
        assert error.retry_after_seconds is None  # Fish states none (measured)
        assert "the words of the line" not in error.message
        assert "the words of the line" not in repr(logs)

    async def test_a_vendor_code_that_is_not_an_identifier_is_dropped(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, headers={"x-fish-error-code": "Reference x not found"})

        client = client_with(respond)
        try:
            with pytest.raises(TTSProviderError) as caught:
                await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert caught.value.details == {"status_code": 400, "vendor_code": None}

    async def test_an_empty_answer_is_an_invalid_response(self) -> None:
        client = client_with(recording([], b""))
        try:
            with pytest.raises(TTSProviderError) as caught:
                await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert caught.value.code == "provider_invalid_response"
        assert caught.value.transient

    async def test_a_timeout_is_a_timeout(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        client = client_with(respond)
        try:
            with pytest.raises(TTSProviderError) as caught:
                await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert caught.value.code == "provider_timeout"

    async def test_a_transport_failure_is_a_network_failure(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = client_with(respond)
        try:
            with pytest.raises(TTSProviderError) as caught:
                await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()
        assert caught.value.code == "provider_network_error"
        assert caught.value.details == {"exception_type": "ConnectError"}


class TestTheSocket:
    """The WebSocket transport (ADR-345): its route out, and its fallback."""

    async def test_the_socket_goes_out_through_the_deployments_proxy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """aiohttp reads no proxy from the environment: the demonstrator's API
        container has no other route out, so a direct socket never connects."""
        opened: list[dict[str, Any]] = []

        def ws_connect(session: Any, url: str, **kwargs: Any) -> Any:
            opened.append({"url": url, **kwargs})
            raise aiohttp.ClientConnectionError("no route")

        monkeypatch.setattr(aiohttp.ClientSession, "ws_connect", ws_connect)
        monkeypatch.setattr(module, "configured_proxy", lambda: "http://proxy.local:3128")
        sent: list[httpx.Request] = []
        client = client_with(recording(sent), transport="websocket")
        try:
            audio = await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()

        assert opened[0]["url"] == "wss://api.fish.audio/v1/tts/live"
        assert opened[0]["proxy"] == "http://proxy.local:3128"
        # The session failed in transit: the text was answered over HTTP.
        assert audio == b"ID3audio" and len(sent) == 1

    async def test_an_unknown_transport_is_http_with_a_warning(self) -> None:
        sent: list[httpx.Request] = []
        with capture_logs() as logs:
            client = client_with(recording(sent), transport="carrier-pigeon")
        try:
            await client.synthesize("Bonjour.", "voice-id")
        finally:
            await client.close()

        assert len(sent) == 1
        assert any(entry["event"] == "fishaudio_transport_unknown" for entry in logs)
