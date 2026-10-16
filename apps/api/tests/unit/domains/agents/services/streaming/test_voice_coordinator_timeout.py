"""A chat turn whose progressive voice never finishes is counted, then voiced directly.

Measured on Docker dev 2026-10-14: three Fish Audio socket syntheses of one chat
turn returned nothing for 22 s; the turn waited ``voice_parallel_timeout_seconds``,
cancelled them and voiced the answer again through the direct path — and nothing counted it,
so the dashboard's « Fallbacks » panel showed a clean turn. The wait running out
is now ``voice_fallback_total{reason="timeout"}``, the reason the metric already
documented and nothing produced.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from src.domains.agents.services.streaming import voice_coordinator as coordinator_module
from src.domains.agents.services.streaming.voice_coordinator import (
    VoiceStreamContext,
    VoiceStreamCoordinator,
)
from src.domains.voice import service as voice_service_module
from src.domains.voice.schemas import VoiceAudioChunk
from src.infrastructure.observability.metrics_voice import voice_fallback_total

pytestmark = pytest.mark.unit


class _Tracker:
    """The run's tracker, as the coordinator uses it: committed after synthesis."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _Streamer:
    """A sentence streamer that took the answer and will never finish voicing it."""

    def __init__(self) -> None:
        self.fed: list[str] = []
        self.closed = False

    def feed(self, text: str) -> None:
        self.fed.append(text)

    def close_input(self) -> None:
        self.closed = True


async def _never_finishes() -> None:
    """The drain of a sentence the vendor never answers."""
    await asyncio.Event().wait()


class _VoiceService:
    """Stands in for ``VoiceCommentService``: a stalled progressive path, a working direct one."""

    drains: list[asyncio.Task[None]] = []
    direct_texts: list[str] = []

    def __init__(self, **_: Any) -> None:
        pass

    async def start_progressive_chat_stream(
        self, user_language: str, chunk_queue: asyncio.Queue[Any], max_sentences: int | None = None
    ) -> tuple[_Streamer, asyncio.Task[None]]:
        drain = asyncio.create_task(_never_finishes())
        _VoiceService.drains.append(drain)
        return _Streamer(), drain

    async def stream_direct_tts(
        self, text: str, user_language: str, max_sentences: int
    ) -> AsyncIterator[VoiceAudioChunk]:
        _VoiceService.direct_texts.append(text)
        yield VoiceAudioChunk(audio_base64="SUQz", phrase_index=0, phrase_text=text, is_last=True)

    async def close(self) -> None:
        return None


@pytest.fixture
def stalled_voice(monkeypatch: pytest.MonkeyPatch) -> type[_VoiceService]:
    async def listening(*_: Any, **__: Any) -> bool:
        return True

    _VoiceService.drains = []
    _VoiceService.direct_texts = []
    monkeypatch.setattr(coordinator_module, "_should_start_voice", listening)
    monkeypatch.setattr(voice_service_module, "VoiceCommentService", _VoiceService)
    monkeypatch.setattr(coordinator_module.settings, "voice_parallel_timeout_seconds", 0.05)
    return _VoiceService


def _coordinator(tracker: _Tracker) -> VoiceStreamCoordinator:
    context = VoiceStreamContext(
        run_id="run-stalled-voice",
        user_id="user-1",
        user_language="fr",
        user_timezone="UTC",
        user_message="Bonjour",
        lia_gender="female",
        personality_instruction=None,
        user_obj=None,
        has_listeners=None,
        start_time=0.0,
    )
    return VoiceStreamCoordinator(context, tracker)  # type: ignore[arg-type]


async def test_a_progressive_voice_that_never_finishes_is_counted_then_voiced_directly(
    stalled_voice: type[_VoiceService],
) -> None:
    counter = voice_fallback_total.labels(reason="timeout")
    before = counter._value.get()
    tracker = _Tracker()
    coordinator = _coordinator(tracker)

    await coordinator.on_router_decision("conversation")
    coordinator.feed_token("Bonjour, voici la réponse.")
    coordinator.close_input()
    chunks = [
        chunk
        async for chunk in coordinator.finalize(
            response_content="Bonjour, voici la réponse.",
            hitl_interrupted=False,
            voice_context_registry=None,
        )
    ]

    assert counter._value.get() == before + 1
    (drain,) = stalled_voice.drains
    assert drain.cancelled()
    # The answer was still voiced, through the direct path, and its cost committed.
    assert stalled_voice.direct_texts == ["Bonjour, voici la réponse."]
    assert [chunk.type for chunk in chunks] == [
        "voice_comment_start",
        "voice_audio_chunk",
        "voice_complete",
    ]
    assert chunks[-1].metadata is not None
    assert chunks[-1].metadata["source"] == "direct_tts_chat_mode"
    assert tracker.commits == 1
