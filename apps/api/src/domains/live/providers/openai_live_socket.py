"""One GPT-Live session over WebSocket, server side, on the person's key (ADR-299, wave 2 A9).

Two acts need it and nothing else does — the activation PROBE and the voice
SAMPLE — because GPT-Live's voices are not the speech endpoint's (measured
2026-09-19: none of the twelve is accepted by ``/v1/audio/speech``), so the
only faithful sample is the live model itself, for a few seconds, on the
person's own key (never counted, ADR-299). The browser never comes here: it
speaks WebRTC, and the offer exchange is an HTTP call in the provider.

Measured the same day on the dev instance's key:
- ``session.start`` answers ``session.started`` in 1.2-1.7 s; an unknown
  voice answers ``error`` (``forbidden``) BEFORE any start — so, unlike
  Gemini, the provider refuses a wrong voice itself — and an unknown model
  ``invalid_model``;
- ``session.instructions.append`` requires an explicit ``delegation_id: null``
  and a ``content`` field (the reference shows ``instructions``);
- a greeting is rendered only while INPUT audio flows — the session clock
  advances with it («keep input audio running») — so the sample streams
  silence at real-time pace; the first audio delta came 0.7 s after the
  append, the transcript exactly the sentence asked for, and ``usage.seconds``
  counted the input audio (8.0 s for the run).
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from src.core.constants import (
    OPENAI_LIVE_CLOSE_WAIT_SECONDS,
    OPENAI_LIVE_SAMPLE_RATE,
    OPENAI_LIVE_SAMPLE_TRANSCRIPT_QUIET_SECONDS,
    OPENAI_LIVE_SILENCE_CHUNK_MS,
    OPENAI_LIVE_WS_MAX_MESSAGE_BYTES,
    OPENAI_LIVE_WS_URL,
)


class OpenAiLiveRefused(Exception):
    """The provider answered an ``error`` event: its code and its words."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class LiveEvents(Protocol):
    """What the sample needs of an open session: send an event, receive one."""

    async def send(self, event: dict[str, Any]) -> None: ...

    async def receive(self, timeout: float) -> dict[str, Any] | None: ...


class OpenAiLiveSocket:
    """A session over ``wss://api.openai.com/v1/live/sessions`` on the person's key.

    The aiohttp session is built per act and closed with it (the singleton
    rule); ``start`` sends the config and reads the provider's verdict.
    """

    def __init__(self, api_key: str, *, timeout: float) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._session: Any = None
        self._ws: Any = None

    async def __aenter__(self) -> OpenAiLiveSocket:
        import aiohttp

        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(
                OPENAI_LIVE_WS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=aiohttp.ClientWSTimeout(ws_close=self._timeout),
                max_msg_size=OPENAI_LIVE_WS_MAX_MESSAGE_BYTES,
            )
        except BaseException:
            await self._session.close()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()

    async def send(self, event: dict[str, Any]) -> None:
        """One client event."""
        await self._ws.send_str(json.dumps(event))

    async def receive(self, timeout: float) -> dict[str, Any] | None:
        """The next server event, or None when nothing came within ``timeout``."""
        import aiohttp

        try:
            message = await asyncio.wait_for(self._ws.receive(), timeout=timeout)
        except TimeoutError:
            return None
        if message.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
            raw = message.data
            parsed = json.loads(raw if isinstance(raw, str) else raw.decode())
            return parsed if isinstance(parsed, dict) else None
        if message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
            raise OpenAiLiveRefused("closed", "the provider closed the connection")
        if message.type == aiohttp.WSMsgType.ERROR:
            raise OpenAiLiveRefused("transport", str(self._ws.exception()))
        return None

    async def start(self, session_config: dict[str, Any]) -> dict[str, Any]:
        """Send ``session.start`` and read the verdict.

        Args:
            session_config: The ``session`` object (model, instructions, audio, delegation).

        Returns:
            The resolved session the provider echoes in ``session.started``.

        Raises:
            OpenAiLiveRefused: The provider answered ``error`` (its code and
                words), closed the connection, or answered nothing in time.
        """
        await self.send({"type": "session.start", "event_id": "start", "session": session_config})
        event = await self.receive(self._timeout)
        if event is None:
            raise OpenAiLiveRefused("timeout", "the provider did not answer in time")
        return _started_or_raise(event)

    async def close(self) -> None:
        """``session.close``, then wait — bounded — for ``session.closed``."""
        await self.send({"type": "session.close", "event_id": "close"})
        deadline = time.monotonic() + min(self._timeout, OPENAI_LIVE_CLOSE_WAIT_SECONDS)
        while time.monotonic() < deadline:
            event = await self.receive(max(0.1, deadline - time.monotonic()))
            if event is None or event.get("type") == "session.closed":
                return


def _started_or_raise(event: dict[str, Any]) -> dict[str, Any]:
    """The session of a ``session.started`` event; anything else is a refusal."""
    kind = str(event.get("type"))
    if kind == "session.started":
        session = event.get("session")
        return session if isinstance(session, dict) else {}
    if kind == "error":
        raw_error = event.get("error")
        error: dict[str, Any] = raw_error if isinstance(raw_error, dict) else {}
        raise OpenAiLiveRefused(str(error.get("code") or "error"), str(error.get("message") or ""))
    raise OpenAiLiveRefused("unexpected", kind)


def silence_chunk_b64(rate: int = OPENAI_LIVE_SAMPLE_RATE) -> str:
    """One chunk of 16-bit mono silence at ``rate``, base64, ``OPENAI_LIVE_SILENCE_CHUNK_MS`` long."""
    return base64.b64encode(bytes(rate * 2 * OPENAI_LIVE_SILENCE_CHUNK_MS // 1000)).decode("ascii")


async def sample_utterance(
    events: LiveEvents,
    greeting: str,
    *,
    max_seconds: float,
    clock: Callable[[], float] = time.monotonic,
    pace: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> bytes:
    """Ask an OPEN session to speak once and collect its audio.

    Streams input silence at real-time pace (the session clock advances with
    it), appends the greeting instruction, then gathers ``output_audio``
    deltas until the transcript has been quiet for
    ``OPENAI_LIVE_SAMPLE_TRANSCRIPT_QUIET_SECONDS`` after it began, or
    ``max_seconds`` after the first audio — the output stream is continuous
    (full duplex), so silence follows the sentence for as long as the session
    stays open.

    Args:
        events: The open session (``OpenAiLiveSocket`` or a test double).
        greeting: The rendered instruction asking for the sentence.
        max_seconds: The most audio wall time collected after the first delta.
        clock: A monotonic clock (a test drives a fake one).
        pace: The sleep between two silence chunks (a test skips it).

    Returns:
        The raw 16-bit mono PCM at ``OPENAI_LIVE_SAMPLE_RATE``, untrimmed.

    Raises:
        OpenAiLiveRefused: An ``error`` event named the greeting, or the
            provider closed the connection.
    """
    chunk = silence_chunk_b64()

    async def _stream_silence() -> None:
        while True:
            await events.send({"type": "session.input_audio.append", "audio": chunk})
            await pace(OPENAI_LIVE_SILENCE_CHUNK_MS / 1000)

    streaming = asyncio.create_task(_stream_silence())
    try:
        await events.send(
            {
                "type": "session.instructions.append",
                "event_id": "sample",
                "delegation_id": None,
                "content": greeting,
            }
        )
        return await _collect_audio(events, max_seconds=max_seconds, clock=clock)
    finally:
        streaming.cancel()
        # The task owns its coroutine: awaited here so nothing is left pending.
        await asyncio.gather(streaming, return_exceptions=True)


async def _collect_audio(
    events: LiveEvents, *, max_seconds: float, clock: Callable[[], float]
) -> bytes:
    """The audio deltas of one utterance, bounded by the transcript's silence and ``max_seconds``."""
    audio = bytearray()
    first_audio_at: float | None = None
    last_transcript_at: float | None = None
    started_at = clock()
    while True:
        now = clock()
        if first_audio_at is not None and now - first_audio_at >= max_seconds:
            break
        if last_transcript_at is not None and (
            now - last_transcript_at >= OPENAI_LIVE_SAMPLE_TRANSCRIPT_QUIET_SECONDS
        ):
            break
        if first_audio_at is None and now - started_at >= max_seconds:
            break
        event = await events.receive(0.5)
        if event is None:
            continue
        kind = str(event.get("type"))
        if kind == "session.output_audio.delta":
            audio.extend(base64.b64decode(str(event.get("delta") or "")))
            first_audio_at = first_audio_at if first_audio_at is not None else clock()
        elif kind == "session.output_transcript.delta":
            last_transcript_at = clock()
        elif kind == "error":
            _started_or_raise(event)
    return bytes(audio)


__all__ = [
    "LiveEvents",
    "OpenAiLiveRefused",
    "OpenAiLiveSocket",
    "sample_utterance",
    "silence_chunk_b64",
]
