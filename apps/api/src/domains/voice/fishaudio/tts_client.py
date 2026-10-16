"""Fish Audio text-to-speech client (``POST /v1/tts``).

Implements :class:`~src.domains.voice.protocol.TTSClient` and
:class:`~src.domains.voice.protocol.RawAudioTTSClient`. Measured on
``s2.1-pro-free`` before it was written (2026-10-13):

- the ``model`` header picks the engine, and a missing or unknown one is served
  AND billed as ``s2.1-pro`` — this client always names its model;
- the voice is a ``reference_id`` (a 32-hex model id of the voice library);
- ``pcm`` is raw signed 16-bit mono samples at the requested ``sample_rate``;
- the account caps its in-flight requests (5 on the first tier) across
  synthesis, transcription and voice design, so every request takes a slot of
  the shared ``fishaudio`` allowance; a 429 carries no ``Retry-After``;
- billing is per million UTF-8 BYTES of text (the ``fishaudio`` voice family).

It also implements :class:`~src.domains.voice.protocol.DialogueTTSClient`: several
voices in one streamed request, each turn placed on the timeline the vendor
returns (:mod:`src.domains.voice.fishaudio.dialogue`). A slot may ask for the
vendor's WebSocket instead of HTTP (:mod:`src.domains.voice.fishaudio.live`):
one session per synthesis, and a session that fails in transit — or falls silent
for ``FISHAUDIO_SOCKET_STALL_SECONDS`` — is answered over HTTP, counted, never
silent.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from typing import NoReturn

import aiohttp
import httpx
import structlog

from src.core.constants import (
    DEFAULT_FISHAUDIO_BASE_URL,
    FISHAUDIO_DIALOGUE_TIMEOUT_SECONDS,
    FISHAUDIO_PROVIDER_NAME,
    FISHAUDIO_SOCKET_STALL_SECONDS,
)
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.egress import configured_proxy
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.fishaudio.dialogue import (
    DIALOGUE_PATH,
    TimestampedStream,
    compose_dialogue,
    turn_starts,
)
from src.domains.voice.fishaudio.formats import (
    DEFAULT_FISH_OUTPUT_FORMAT,
    DEFAULT_FISH_TRANSPORT,
    FISH_LATENCIES,
    FISH_OUTPUT_FORMATS,
    FISH_TRANSPORTS,
    FishFormat,
    bounded_speed,
)
from src.domains.voice.fishaudio.live import LiveAudio, live_url, opening_frames
from src.domains.voice.fishaudio.wire import auth_headers, refusal_of
from src.domains.voice.protocol import DialogueAudio, DialogueTurn, RawAudioSpec
from src.domains.voice.provider_capacity import ProviderCapacityUnavailable, provider_slot
from src.infrastructure.observability.metrics_voice import (
    voice_tts_errors_total,
    voice_tts_latency_seconds,
    voice_tts_requests_total,
    voice_tts_transport_fallbacks_total,
)

logger = structlog.get_logger(__name__)


def _container(output_format: str | None) -> FishFormat:
    """The declared container a stored token names, or the vendor's default."""
    if output_format is None:
        return FISH_OUTPUT_FORMATS[DEFAULT_FISH_OUTPUT_FORMAT]
    container = FISH_OUTPUT_FORMATS.get(output_format)
    if container is None:
        # Mechanically repairable: the default container is audible everywhere.
        logger.warning("fishaudio_output_format_unknown", output_format=output_format)
        return FISH_OUTPUT_FORMATS[DEFAULT_FISH_OUTPUT_FORMAT]
    return container


def _latency(latency: str | None) -> str | None:
    """A latency the vendor accepts, else none (its own default applies)."""
    if latency is None or latency in FISH_LATENCIES:
        return latency
    logger.warning("fishaudio_latency_unknown", latency=latency)
    return None


def _transport(transport: str | None) -> str:
    """A transport the client speaks, else HTTP (the default)."""
    if transport is None or transport in FISH_TRANSPORTS:
        return transport or DEFAULT_FISH_TRANSPORT
    logger.warning("fishaudio_transport_unknown", transport=transport)
    return DEFAULT_FISH_TRANSPORT


class FishAudioTTSClient:
    """Fish Audio TTS, billed per UTF-8 byte of the text it is sent."""

    def __init__(
        self,
        model: str,
        *,
        output_format: str | None = None,
        latency: str | None = None,
        speed: float | None = None,
        transport: str | None = None,
        base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
        timeout_seconds: float = 60.0,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        api_key = LLMConfigOverrideCache.get_api_key(FISHAUDIO_PROVIDER_NAME)
        if not api_key:
            raise TTSProviderError(
                code="api_key_missing",
                message="Fish Audio API key is not configured — TTS cannot synthesise.",
            )
        self.model = model
        self._api_key = api_key
        self._container = _container(output_format)
        self._latency = _latency(latency)
        self._speed = speed
        self._transport = _transport(transport)
        self._live_url = live_url(base_url)
        # Opened on the first socket session, closed with the client.
        self._socket: aiohttp.ClientSession | None = None
        self._timeout_seconds = timeout_seconds
        # One persistent client per TTSClient instance: sentences are synthesised
        # back to back, and the TLS handshake (Hong Kong, measured) would dominate.
        self._http_client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=http_transport,
            headers=auth_headers(api_key, model=model),
        )

    @property
    def provider_name(self) -> str:
        """Provider id for logs, metrics and the cost recorder."""
        return FISHAUDIO_PROVIDER_NAME

    @property
    def audio_format(self) -> str:
        """The container this client returns (``mp3`` or ``pcm``)."""
        return self._container.codec

    @property
    def raw_audio_spec(self) -> RawAudioSpec | None:
        """The rate of raw samples, never a guessed one; ``None`` for MP3."""
        if self._container.codec != "pcm":
            return None
        return RawAudioSpec(self._container.sample_rate)

    def _body(self, text: str, voice: str, speed: object) -> dict[str, object]:
        body: dict[str, object] = {"text": text, "reference_id": voice, **self._container.wire()}
        if self._latency is not None:
            body["latency"] = self._latency
        rate = self._speed
        if isinstance(speed, int | float) and not isinstance(speed, bool):
            rate = float(speed)  # the per-call pace wins over the configured rate
        if rate is not None:
            body["prosody"] = {"speed": bounded_speed(rate)}
        return body

    async def synthesize(self, text: str, voice_name: str | None = None, **kwargs: object) -> bytes:
        """Synthesise ``text`` with the voice ``voice_name`` (a library model id).

        Args:
            text: What to say.
            voice_name: The voice's model id.
            **kwargs: ``speed`` — a per-call speaking rate (the radio's pace),
                over the configured one. Other engines' controls are ignored.

        Returns:
            The audio, in :attr:`audio_format`.

        Raises:
            TTSProviderError: On a missing voice, an unreservable account slot,
                a transport or HTTP failure, or an answer without audio.
        """
        if not voice_name:
            raise TTSProviderError(code="voice_missing", message="Fish Audio TTS needs a voice")
        body = self._body(text, voice_name, kwargs.get("speed"))
        if self._transport == "websocket":
            try:
                return await self._over_socket(body, voice_name)
            except TTSProviderError as error:
                # A quota is the account's, and a refusal would be the same
                # over HTTP: only a session that failed in transit is retried.
                if error.rate_limited or not error.transient:
                    raise
                voice_tts_transport_fallbacks_total.labels(
                    provider=FISHAUDIO_PROVIDER_NAME, reason=error.code
                ).inc()
                logger.info("fishaudio_socket_fallback", model=self.model, error_code=error.code)
        start = time.perf_counter()
        async with self._account_slot(voice_name, self._timeout_seconds):
            response = await self._http_client.post("/v1/tts", json=body)
        voice_tts_latency_seconds.labels(voice_name=voice_name).observe(time.perf_counter() - start)
        if response.status_code >= 400:
            self._raise_refusal(response, voice_name)
        if not response.content:
            self._count_failure("empty_response", voice_name)
            raise TTSProviderError(
                code="provider_invalid_response", message="Fish Audio TTS answered no audio"
            )
        voice_tts_requests_total.labels(status="success", voice_name=voice_name).inc()
        logger.debug(
            "fishaudio_tts_synthesised",
            model=self.model,
            voice_id=voice_name,
            audio_bytes=len(response.content),
        )
        return response.content

    async def synthesize_dialogue(
        self, turns: Sequence[DialogueTurn], **kwargs: object
    ) -> DialogueAudio:
        """Voice ``turns`` in one streamed request, and place each turn in its audio.

        Args:
            turns: The turns, in order.
            **kwargs: ``speed`` — one speaking rate for every turn.

        Returns:
            The audio, the text the vendor billed, and each turn's start
            (``None`` when the timing could not place every turn).

        Raises:
            ValueError: When there is no turn to voice.
            TTSProviderError: As :meth:`synthesize` does, and on a stream that
                is not the documented shape or carries no audio.
        """
        if not turns:
            raise ValueError("a dialogue needs at least one turn")
        text, voices = compose_dialogue(turns)
        body = {**self._body(text, voices[0], kwargs.get("speed")), "reference_id": voices}
        stream = TimestampedStream()
        start = time.perf_counter()
        async with self._account_slot(voices[0], FISHAUDIO_DIALOGUE_TIMEOUT_SECONDS):
            async with self._http_client.stream("POST", DIALOGUE_PATH, json=body) as response:
                if response.status_code >= 400:
                    self._raise_refusal(response, voices[0])
                async for line in response.aiter_lines():
                    stream.feed(line)
        voice_tts_latency_seconds.labels(voice_name=voices[0]).observe(time.perf_counter() - start)
        if not stream.audio:
            self._count_failure("empty_response", voices[0])
            raise TTSProviderError(
                code="provider_invalid_response", message="Fish Audio dialogue answered no audio"
            )
        starts = turn_starts([turn.words for turn in turns], stream.timeline())
        voice_tts_requests_total.labels(status="success", voice_name=voices[0]).inc()
        logger.debug(
            "fishaudio_dialogue_synthesised",
            model=self.model,
            turns=len(turns),
            voices=len(voices),
            audio_bytes=len(stream.audio),
            placed=starts is not None,
        )
        return DialogueAudio(audio=stream.audio, sent_text=text, turn_starts_s=starts)

    async def _over_socket(self, body: dict[str, object], voice: str) -> bytes:
        """One session of the vendor's socket for one text (see the module docstring).

        A session is bounded by its silence: a vendor that answers nothing for
        ``FISHAUDIO_SOCKET_STALL_SECONDS`` — through its handshake, or between two
        frames — has stalled, a transient failure :meth:`synthesize` answers over
        HTTP. The finish disarms the bound: the audio is whole, and a close the
        vendor acknowledges late must not cost it.
        """
        if self._socket is None:
            self._socket = aiohttp.ClientSession()
        received = LiveAudio()
        start = time.perf_counter()
        async with self._account_slot(voice, self._timeout_seconds, completed=received):
            try:
                await self._exchange(self._socket, body, received)
            except aiohttp.WSServerHandshakeError as exc:
                self._raise_socket_refusal(exc.status, voice)
            except (aiohttp.ClientError, TimeoutError) as exc:
                if not received.complete:
                    self._raise_socket_transport(exc, voice)
                logger.warning("fishaudio_socket_close_failed", error_type=type(exc).__name__)
        if not received.complete:
            self._count_failure("empty_response", voice)
            raise TTSProviderError(
                code="provider_invalid_response",
                message="Fish Audio socket ended without its audio",
                details={"stage": "socket", "finished": received.finished},
            )
        voice_tts_latency_seconds.labels(voice_name=voice).observe(time.perf_counter() - start)
        voice_tts_requests_total.labels(status="success", voice_name=voice).inc()
        logger.debug(
            "fishaudio_tts_synthesised",
            model=self.model,
            voice_id=voice,
            audio_bytes=len(received.audio),
            transport="websocket",
        )
        return received.audio

    def _raise_socket_transport(
        self, error: aiohttp.ClientError | TimeoutError, voice: str
    ) -> NoReturn:
        """Classify a failed exchange before its successful finish."""
        timed_out = isinstance(error, TimeoutError)
        self._count_failure("timeout" if timed_out else "http", voice)
        raise TTSProviderError(
            code="provider_timeout" if timed_out else "provider_network_error",
            message=(
                f"Fish Audio socket was silent for {FISHAUDIO_SOCKET_STALL_SECONDS}s"
                if timed_out
                else "Fish Audio socket transport error"
            ),
            details={"stage": "socket", "exception_type": type(error).__name__},
        ) from error

    async def _exchange(
        self, session: aiohttp.ClientSession, body: dict[str, object], received: LiveAudio
    ) -> None:
        """Send one text over a socket and read its audio into ``received``.

        Bounded by its silence: the bound is rearmed by every frame and disarmed by
        the finish, before the close (see :meth:`_over_socket`).
        """
        loop = asyncio.get_running_loop()
        async with asyncio.timeout(FISHAUDIO_SOCKET_STALL_SECONDS) as silence:
            async with session.ws_connect(
                self._live_url,
                headers=auth_headers(self._api_key, model=self.model),
                # aiohttp reads no proxy from the environment (voice/egress.py).
                proxy=configured_proxy(),
            ) as socket:
                for frame in opening_frames(body):
                    await socket.send_bytes(frame)
                silence.reschedule(loop.time() + FISHAUDIO_SOCKET_STALL_SECONDS)
                async for message in socket:
                    if message.type is aiohttp.WSMsgType.ERROR:
                        return
                    if message.type is aiohttp.WSMsgType.BINARY and received.read(message.data):
                        silence.reschedule(None)
                        return
                    silence.reschedule(loop.time() + FISHAUDIO_SOCKET_STALL_SECONDS)

    def _raise_socket_refusal(self, status: int, voice: str) -> NoReturn:
        """A refused socket handshake, classified by its status like an HTTP refusal."""
        self._count_failure(f"http_{status}", voice)
        logger.warning("fishaudio_socket_refused", model=self.model, status_code=status)
        code = "provider_rate_limited" if status == 429 else "provider_http_error"
        raise TTSProviderError(
            code=code,
            message=f"Fish Audio socket refused with HTTP {status}",
            details={"status_code": status, "stage": "socket"},
        )

    @asynccontextmanager
    async def _account_slot(
        self, voice: str, bound_s: float, *, completed: LiveAudio | None = None
    ) -> AsyncIterator[None]:
        """One request's share of the account, bounded whole, its failures typed.

        The quota belongs to the account, across sentences, clients and workers:
        queueing and HTTP are bounded together so a lease always outlives its
        request.
        """
        try:
            async with asyncio.timeout(bound_s):
                async with provider_slot(
                    FISHAUDIO_PROVIDER_NAME, self._api_key, timeout_seconds=bound_s
                ):
                    yield
        except ProviderCapacityUnavailable as exc:
            raise TTSProviderError(
                code="provider_network_error",
                message="Fish Audio capacity could not be reserved.",
                details={"stage": "capacity_reservation"},
            ) from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            if completed is not None and completed.complete:
                # The deadline interrupted cleanup after the vendor's successful
                # finish. Keep that audio; buying the text again would duplicate it.
                logger.warning("fishaudio_socket_close_timed_out", timeout_seconds=bound_s)
                return
            self._count_failure("timeout", voice)
            raise TTSProviderError(
                code="provider_timeout",
                message=f"Fish Audio TTS timed out after {bound_s}s",
            ) from exc
        except httpx.HTTPError as exc:
            self._count_failure("http", voice)
            raise TTSProviderError(
                code="provider_network_error",
                message="Fish Audio TTS transport error",
                details={"exception_type": type(exc).__name__},
            ) from exc

    @staticmethod
    def _count_failure(error_type: str, voice: str) -> None:
        voice_tts_errors_total.labels(error_type=error_type, voice_name=voice).inc()
        voice_tts_requests_total.labels(status="error", voice_name=voice).inc()

    def _raise_refusal(self, response: httpx.Response, voice: str) -> NoReturn:
        refusal = refusal_of(response)
        self._count_failure(f"http_{refusal.status}", voice)
        # Its facts, never its prose: the message may quote the line refused.
        logger.warning(
            "fishaudio_tts_http_error",
            model=self.model,
            status_code=refusal.status,
            vendor_code=refusal.vendor_code,
        )
        code = "provider_rate_limited" if refusal.status == 429 else "provider_http_error"
        raise TTSProviderError(
            code=code,
            message=f"Fish Audio TTS returned HTTP {refusal.status} ({refusal.vendor_code})",
            details=refusal.details(),
        )

    async def close(self) -> None:
        """Close the persistent HTTP client, and the socket session if one opened."""
        # Already closed, or its loop already gone: nothing left to release.
        with suppress(RuntimeError, httpx.HTTPError):
            await self._http_client.aclose()
        if self._socket is not None:
            # Same reasons: closed already, or its loop gone.
            with suppress(RuntimeError, aiohttp.ClientError):
                await self._socket.close()
            self._socket = None


__all__ = ["FishAudioTTSClient"]
