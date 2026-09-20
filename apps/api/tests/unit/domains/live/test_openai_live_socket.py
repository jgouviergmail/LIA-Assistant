"""The server-side GPT-Live session: the start verdict, and a sample collected under bounds."""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import pytest

from src.core.constants import (
    OPENAI_LIVE_SAMPLE_RATE,
    OPENAI_LIVE_SAMPLE_TRANSCRIPT_QUIET_SECONDS,
    OPENAI_LIVE_SILENCE_CHUNK_MS,
)
from src.domains.live.providers.openai_live_socket import (
    OpenAiLiveRefused,
    OpenAiLiveSocket,
    sample_utterance,
    silence_chunk_b64,
)

pytestmark = pytest.mark.unit


class _ScriptedEvents:
    """A session that answers a scripted list of server events, one per receive, and records sends."""

    def __init__(self, events: list[dict[str, Any] | None]) -> None:
        self.events = list(events)
        self.sent: list[dict[str, Any]] = []

    async def send(self, event: dict[str, Any]) -> None:
        self.sent.append(event)

    async def receive(self, timeout: float) -> dict[str, Any] | None:
        await asyncio.sleep(0)  # a socket read yields; the silence task runs in between
        return self.events.pop(0) if self.events else None


class _FakeClock:
    """A clock the test advances by one step per reading."""

    def __init__(self, step: float) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


async def _no_pace(_seconds: float) -> None:
    # Yields once, as the real sleep does, so the silence task runs between two receives.
    await asyncio.sleep(0)


def _audio(n: int) -> dict[str, Any]:
    return {
        "type": "session.output_audio.delta",
        "delta": base64.b64encode(bytes([1]) * n).decode(),
    }


def test_silence_chunk_is_the_documented_pcm_length() -> None:
    raw = base64.b64decode(silence_chunk_b64())
    assert len(raw) == OPENAI_LIVE_SAMPLE_RATE * 2 * OPENAI_LIVE_SILENCE_CHUNK_MS // 1000
    assert set(raw) == {0}


async def test_start_reads_the_verdict_of_the_first_event() -> None:
    socket = OpenAiLiveSocket("sk-test", timeout=1)
    events = _ScriptedEvents([{"type": "session.started", "session": {"id": "live_1"}}])
    socket.send = events.send  # type: ignore[method-assign]
    socket.receive = events.receive  # type: ignore[method-assign]
    assert await socket.start({"model": "gpt-live-1"}) == {"id": "live_1"}
    assert events.sent[0]["type"] == "session.start" and events.sent[0]["session"] == {
        "model": "gpt-live-1"
    }


async def test_start_raises_the_providers_error_and_a_silence() -> None:
    # Measured 2026-09-19: an unknown voice answers `error` (forbidden) before
    # any start, an unknown model `invalid_model`.
    socket = OpenAiLiveSocket("sk-test", timeout=1)
    events = _ScriptedEvents(
        [
            {
                "type": "error",
                "error": {"code": "forbidden", "message": "Voice session access denied."},
            }
        ]
    )
    socket.send = events.send  # type: ignore[method-assign]
    socket.receive = events.receive  # type: ignore[method-assign]
    with pytest.raises(OpenAiLiveRefused) as caught:
        await socket.start({"model": "gpt-live-1"})
    assert caught.value.code == "forbidden"
    quiet = OpenAiLiveSocket("sk-test", timeout=1)
    silent = _ScriptedEvents([])
    quiet.send = silent.send  # type: ignore[method-assign]
    quiet.receive = silent.receive  # type: ignore[method-assign]
    with pytest.raises(OpenAiLiveRefused) as timed_out:
        await quiet.start({"model": "gpt-live-1"})
    assert timed_out.value.code == "timeout"


async def test_sample_streams_silence_asks_once_and_stops_when_the_transcript_goes_quiet() -> None:
    # The stream is continuous (full duplex): after the sentence, silence
    # keeps coming; the transcript's quiet is what ends the collection.
    events = _ScriptedEvents(
        [
            None,
            _audio(10),
            {"type": "session.output_transcript.delta", "delta": "Hello"},
            _audio(10),
            {"type": "session.output_transcript.delta", "delta": ", LIA."},
            _audio(10),
            _audio(10),
            _audio(10),
            _audio(10),
            _audio(10),
        ]
    )
    clock = _FakeClock(step=0.3)
    pcm = await sample_utterance(events, "say hello", max_seconds=30, clock=clock, pace=_no_pace)
    asked = [e for e in events.sent if e["type"] == "session.instructions.append"]
    assert asked == [
        {
            "type": "session.instructions.append",
            "event_id": "sample",
            "delegation_id": None,
            "content": "say hello",
        }
    ]
    assert any(e["type"] == "session.input_audio.append" for e in events.sent)
    # Stopped after the quiet, not at the end of the script.
    assert 20 <= len(pcm) < 70
    assert clock.now < 0.3 * 30
    assert OPENAI_LIVE_SAMPLE_TRANSCRIPT_QUIET_SECONDS <= clock.now


async def test_sample_is_bounded_by_max_seconds_after_the_first_delta() -> None:
    events = _ScriptedEvents([_audio(5)] * 200)
    clock = _FakeClock(step=0.5)
    pcm = await sample_utterance(events, "say hello", max_seconds=3, clock=clock, pace=_no_pace)
    assert 5 <= len(pcm) <= 5 * 12
    assert events.events, "the script was not drained: the bound stopped the collection"


async def test_sample_gives_up_when_no_audio_ever_comes() -> None:
    events = _ScriptedEvents([None] * 100)
    clock = _FakeClock(step=1.0)
    pcm = await sample_utterance(events, "say hello", max_seconds=4, clock=clock, pace=_no_pace)
    assert pcm == b""
    assert events.events, "bounded by max_seconds even without a first delta"


async def test_sample_raises_the_providers_error_on_the_ask() -> None:
    events = _ScriptedEvents(
        [{"type": "error", "error": {"code": "missing_required_parameter", "message": "content"}}]
    )
    with pytest.raises(OpenAiLiveRefused) as caught:
        await sample_utterance(
            events, "say hello", max_seconds=5, clock=_FakeClock(0.1), pace=_no_pace
        )
    assert caught.value.code == "missing_required_parameter"
