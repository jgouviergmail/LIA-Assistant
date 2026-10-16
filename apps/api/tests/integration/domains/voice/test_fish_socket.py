"""Fish Audio over a REAL local WebSocket (ADR-345): the session, its fallback, its refusals.

A local aiohttp server plays the vendor's socket (``/v1/tts/live``, MessagePack
frames); HTTP goes to a mock transport so a fallback is visible. Nothing
reaches the network.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import msgpack
import pytest
from aiohttp import WSMsgType, web

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.fishaudio import tts_client as module
from src.domains.voice.fishaudio.tts_client import FishAudioTTSClient
from src.infrastructure.observability.metrics_voice import (
    voice_tts_requests_total,
    voice_tts_transport_fallbacks_total,
)

pytestmark = pytest.mark.integration

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@pytest.fixture(autouse=True)
def fish_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        LLMConfigOverrideCache,
        "get_api_key",
        classmethod(lambda cls, provider: "fish-key" if provider == "fishaudio" else None),
    )

    @asynccontextmanager
    async def free_slot(
        provider: str, api_key: str, *, timeout_seconds: float
    ) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(module, "provider_slot", free_slot)


@asynccontextmanager
async def vendor(handler: Handler, port: int) -> AsyncIterator[str]:
    app = web.Application()
    app.router.add_get("/v1/tts/live", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


def client(base_url: str, http: list[httpx.Request]) -> FishAudioTTSClient:
    def respond(request: httpx.Request) -> httpx.Response:
        http.append(request)
        return httpx.Response(200, content=b"ID3http")

    return FishAudioTTSClient(
        model="s2.1-pro-free",
        transport="websocket",
        base_url=base_url,
        http_transport=httpx.MockTransport(respond),
    )


def session(answers: list[dict[str, Any]], seen: list[Any]) -> Handler:
    async def handle(request: web.Request) -> web.StreamResponse:
        seen.append(dict(request.headers))
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            if message.type is not WSMsgType.BINARY:
                continue
            event = msgpack.unpackb(message.data, raw=False)
            seen.append(event)
            if event["event"] == "stop":
                for answer in answers:
                    await ws.send_bytes(msgpack.packb(answer))
                await ws.close()
        return ws

    return handle


async def test_one_session_voices_the_text_and_its_audio_comes_back(unused_tcp_port: int) -> None:
    seen: list[Any] = []
    http: list[httpx.Request] = []
    answers: list[dict[str, Any]] = [
        {"event": "audio", "audio": b"ID3one"},
        {"event": "audio", "audio": b"two"},
        {"event": "finish", "reason": "stop"},
    ]
    async with vendor(session(answers, seen), unused_tcp_port) as base_url:
        fish = client(base_url, http)
        try:
            audio = await fish.synthesize("Bonjour.", "voice-id", speed=1.2)
        finally:
            await fish.close()

    headers, start, text, stop = seen
    assert audio == b"ID3onetwo"
    assert http == []  # nothing went over HTTP
    assert headers["model"] == "s2.1-pro-free"
    assert headers["Authorization"] == "Bearer fish-key"
    assert start["event"] == "start"
    assert start["request"]["text"] == ""
    assert start["request"]["reference_id"] == "voice-id"
    assert start["request"]["prosody"] == {"speed": 1.2}
    assert text == {"event": "text", "text": "Bonjour."}
    assert stop == {"event": "stop"}


async def test_a_session_that_fails_in_transit_is_answered_over_http(unused_tcp_port: int) -> None:
    fallback = voice_tts_transport_fallbacks_total.labels(
        provider="fishaudio", reason="provider_invalid_response"
    )
    before = fallback._value.get()
    http: list[httpx.Request] = []
    answers: list[dict[str, Any]] = [
        {"event": "audio", "audio": b"cut"},
        {"event": "finish", "reason": "error"},
    ]
    async with vendor(session(answers, []), unused_tcp_port) as base_url:
        fish = client(base_url, http)
        try:
            audio = await fish.synthesize("Bonjour.", "voice-id")
        finally:
            await fish.close()

    assert audio == b"ID3http"
    assert len(http) == 1 and http[0].url.path == "/v1/tts"
    assert fallback._value.get() == before + 1


@pytest.mark.parametrize(
    ("status", "code"), [(429, "provider_rate_limited"), (401, "provider_http_error")]
)
async def test_a_refused_handshake_is_never_retried_over_http(
    unused_tcp_port: int, status: int, code: str
) -> None:
    async def refuse(request: web.Request) -> web.StreamResponse:
        return web.Response(status=status, text="no")

    http: list[httpx.Request] = []
    async with vendor(refuse, unused_tcp_port) as base_url:
        fish = client(base_url, http)
        try:
            with pytest.raises(TTSProviderError) as raised:
                await fish.synthesize("Bonjour.", "voice-id")
        finally:
            await fish.close()

    assert raised.value.code == code
    assert isinstance(raised.value.details, dict)
    assert raised.value.details["status_code"] == status
    assert http == []


@pytest.fixture
def quick_stall(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stall bound a test can wait out (the real one is ten seconds)."""
    monkeypatch.setattr(module, "FISHAUDIO_SOCKET_STALL_SECONDS", 0.3)


def silent_after(answers: list[dict[str, Any]], *, close_delay_s: float = 0.0) -> Handler:
    """A vendor that sends ``answers`` once the text is stopped, then nothing more.

    It keeps reading, so the client's close is answered — ``close_delay_s`` late.
    """

    async def handle(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            if message.type is not WSMsgType.BINARY:
                continue
            if msgpack.unpackb(message.data, raw=False)["event"] == "stop":
                for answer in answers:
                    await ws.send_bytes(msgpack.packb(answer))
                await asyncio.sleep(close_delay_s)
        return ws

    return handle


@pytest.mark.usefixtures("quick_stall")
@pytest.mark.parametrize(
    "before_silence",
    [[], [{"event": "audio", "audio": b"ID3half"}]],
    ids=["never-answers", "stops-mid-stream"],
)
async def test_a_silent_session_is_answered_over_http_once_it_stalls(
    unused_tcp_port: int, before_silence: list[dict[str, Any]]
) -> None:
    """A silent session is bounded by its silence (ten seconds), never by the
    request's own 60 s: a chat turn waits for its voice far less than that."""
    fallback = voice_tts_transport_fallbacks_total.labels(
        provider="fishaudio", reason="provider_timeout"
    )
    before = fallback._value.get()
    http: list[httpx.Request] = []
    async with vendor(silent_after(before_silence), unused_tcp_port) as base_url:
        fish = client(base_url, http)
        started = time.perf_counter()
        try:
            audio = await fish.synthesize("Bonjour.", "voice-id")
        finally:
            await fish.close()

    assert audio == b"ID3http"
    assert len(http) == 1 and http[0].url.path == "/v1/tts"
    assert fallback._value.get() == before + 1
    assert time.perf_counter() - started < 5.0  # the request's own bound is 60 s


@pytest.mark.usefixtures("quick_stall")
@pytest.mark.parametrize("request_bound", [60.0, 0.25])
async def test_a_slow_close_after_the_finish_keeps_the_sessions_audio(
    unused_tcp_port: int,
    request_bound: float,
) -> None:
    """The audio is whole at the finish: a close the vendor answers late is not a
    stall, and re-voicing the text over HTTP would bill it twice."""
    answers: list[dict[str, Any]] = [
        {"event": "audio", "audio": b"ID3whole"},
        {"event": "finish", "reason": "stop"},
    ]
    http: list[httpx.Request] = []
    failed = voice_tts_requests_total.labels(status="error", voice_name="voice-id")
    before = failed._value.get()
    async with vendor(silent_after(answers, close_delay_s=1.0), unused_tcp_port) as base_url:
        fish = client(base_url, http)
        fish._timeout_seconds = request_bound
        try:
            audio = await fish.synthesize("Bonjour.", "voice-id")
        finally:
            await fish.close()

    assert audio == b"ID3whole"
    assert http == []
    assert failed._value.get() == before


async def test_cancellation_after_the_finish_still_cancels_without_http_replay(
    unused_tcp_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    finished = asyncio.Event()
    original_read = module.LiveAudio.read

    def observed_read(self: module.LiveAudio, frame: bytes) -> bool:
        complete = original_read(self, frame)
        if complete:
            finished.set()
        return complete

    monkeypatch.setattr(module.LiveAudio, "read", observed_read)
    answers = [
        {"event": "audio", "audio": b"ID3whole"},
        {"event": "finish", "reason": "stop"},
    ]
    http: list[httpx.Request] = []
    async with vendor(silent_after(answers, close_delay_s=1.0), unused_tcp_port) as base_url:
        fish = client(base_url, http)
        speaking = asyncio.create_task(fish.synthesize("Bonjour.", "voice-id"))
        try:
            await asyncio.wait_for(finished.wait(), timeout=5)
            assert not speaking.done()
            speaking.cancel()
            with pytest.raises(asyncio.CancelledError):
                await speaking
        finally:
            if not speaking.done():
                speaking.cancel()
            await asyncio.gather(speaking, return_exceptions=True)
            await fish.close()
    assert http == []
