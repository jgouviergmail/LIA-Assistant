"""Gemini text-to-speech client (the Interactions API).

Implements :class:`TTSClient` and :class:`UsageReportingTTSClient`: Gemini bills
the TOKENS of a synthesis — text in, audio out — and says how many in its usage
report, so the caller can price the call on what the vendor actually counts.

Shapes MEASURED on 2026-09-26 against the live API (not read from a page):

- ``POST /v1beta/interactions`` with the text in ``input[0].content[0]``, the
  delivery direction in a ``speech_metadata`` annotation's ``style`` (only the
  models that take one: the 2.5 and 3.1 previews answer 400 to any annotation —
  :func:`src.domains.voice.families.controls_for` decides, the caller asks), and
  the prebuilt voice in ``generation_config.speech_config[0].voice``;
- the audio comes back base64 in ``steps[].content[]`` (``type: audio``): a WAV
  (``audio/wav``: 24 kHz, mono, 16-bit) from the 3.8 models, raw samples
  (``audio/L16;codec=pcm;rate=24000``) from the 2.5 previews — wrapped here in
  a WAV container; the usage in ``usage.total_input_tokens`` /
  ``usage.total_output_tokens`` (about 35 audio tokens per second of speech).

The WAV is returned as is (``output_format="wav"``, what an audio mixer wants
lossless) or transcoded to MP3 (the default): an MP3 stream can be joined byte
to byte, a WAV stream cannot, and the readout paths join sentences.
"""

from __future__ import annotations

import base64
import re
import time
from contextlib import suppress
from typing import Any, Final, Literal, NoReturn

import httpx
import structlog

from src.core.constants import GEMINI_TTS_SAMPLE_RATE
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.billing import SynthesisResult
from src.domains.voice.exceptions import TTSProviderError
from src.infrastructure.media.ffmpeg import FfmpegError, transcode
from src.infrastructure.media.pcm import wav_container
from src.infrastructure.observability.metrics_voice import (
    voice_tts_errors_total,
    voice_tts_latency_seconds,
    voice_tts_requests_total,
)

logger = structlog.get_logger(__name__)

#: The Gemini API root the Interactions endpoint hangs off.
GEMINI_API_BASE_URL: Final[str] = "https://generativelanguage.googleapis.com/v1beta"

GeminiOutputFormat = Literal["mp3", "wav"]

#: An error code worth logging is a bounded identifier (``invalid_request``), never prose.
_VENDOR_CODE: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9_]{0,63}")


def _audio_part(payload: dict[str, Any]) -> tuple[str, str] | None:
    """The base64 audio of an Interactions response and its declared type, or ``None``."""
    for step in payload.get("steps") or []:
        for part in step.get("content") or []:
            if part.get("type") == "audio" and isinstance(part.get("data"), str):
                mime_type = part.get("mime_type")
                return str(part["data"]), mime_type if isinstance(mime_type, str) else ""
    return None


#: The answers that carry raw samples and no container.
_RAW_PCM_TYPES: Final = frozenset({"audio/l16", "audio/pcm"})


def _playable(audio: bytes, mime_type: str) -> bytes:
    """The audio in a container a reader can probe.

    Measured 2026-09-26 on the Interactions API: the 3.8 models answer
    ``audio/wav``, the 2.5 previews ``audio/L16;codec=pcm;rate=24000`` — raw
    samples, little-endian whatever RFC 2586 says of L16 (the first samples,
    near silence, read as such). Read as a WAV, every transcode of them failed.
    """
    base, *parameters = (piece.strip() for piece in mime_type.split(";"))
    if base.lower() not in _RAW_PCM_TYPES:
        return audio
    rate = GEMINI_TTS_SAMPLE_RATE
    for parameter in parameters:
        name, _, value = parameter.partition("=")
        if name.strip().lower() == "rate" and value.strip().isdigit() and int(value) > 0:
            rate = int(value)
    return wav_container(audio, sample_rate=rate)


def _reported_tokens(payload: dict[str, Any]) -> tuple[int, int]:
    """Text tokens in and audio tokens out as the vendor's report states them (0 when silent)."""
    usage = payload.get("usage") or {}
    return int(usage.get("total_input_tokens") or 0), int(usage.get("total_output_tokens") or 0)


def _usage(payload: dict[str, Any]) -> tuple[int, int] | None:
    """Text tokens in and audio tokens out as the vendor counted them, when it did.

    ``None`` when the report is absent or empty: zero tokens would price a
    paid synthesis at nothing, so the caller falls back to characters instead.
    """
    tokens_in, tokens_out = _reported_tokens(payload)
    return (tokens_in, tokens_out) if tokens_out > 0 else None


def _vendor_status(response: httpx.Response) -> str:
    """The vendor's symbolic error status, never its prose.

    Two shapes name it: ``error.status`` (``INVALID_ARGUMENT``, the
    ``generateContent`` family) and ``error.code`` (``invalid_request``, what
    the Interactions API answered on 2026-09-26). An error body can quote the
    request; a log line carries facts, not the person's words (ADR-317), so
    only a bounded identifier travels.
    """
    try:
        payload = response.json()
    except ValueError:
        return "unparsed"
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "unknown"
    status = error.get("status")
    if isinstance(status, str) and status.isupper():
        return status
    code = error.get("code")
    if isinstance(code, str) and _VENDOR_CODE.fullmatch(code):
        return code
    return "unknown"


class GeminiTTSClient:
    """Gemini TTS, billed on the tokens its usage report states."""

    def __init__(
        self,
        model: str,
        *,
        output_format: GeminiOutputFormat = "mp3",
        mp3_bitrate_kbps: int = 64,
        timeout_seconds: float = 60.0,
        base_url: str = GEMINI_API_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        api_key = LLMConfigOverrideCache.get_api_key("gemini")
        if not api_key:
            raise TTSProviderError(
                code="api_key_missing",
                message="Gemini API key is not configured — TTS cannot synthesise.",
            )
        self.model = model
        self._output_format: GeminiOutputFormat = output_format
        self._mp3_bitrate_kbps = mp3_bitrate_kbps
        self._timeout_seconds = timeout_seconds
        self._url = f"{base_url.rstrip('/')}/interactions"
        # One persistent client per TTSClient instance: sentences are synthesised
        # back to back, and the TLS handshake would dominate a short one.
        self._http_client = httpx.AsyncClient(
            timeout=timeout_seconds,
            transport=transport,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        )

    @property
    def provider_name(self) -> str:
        """Provider id for logs, metrics and the cost recorder."""
        return "gemini"

    @property
    def audio_format(self) -> str:
        """The container this client returns."""
        return self._output_format

    def _body(self, text: str, voice: str, style: str | None) -> dict[str, Any]:
        content: dict[str, Any] = {"type": "text", "text": text}
        if style:
            content["annotations"] = [{"type": "speech_metadata", "style": style}]
        return {
            "model": self.model,
            "input": [{"type": "user_input", "content": [content]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]},
        }

    async def _post(self, body: dict[str, Any], voice: str) -> httpx.Response:
        start = time.perf_counter()
        try:
            response = await self._http_client.post(self._url, json=body)
        except httpx.TimeoutException as exc:
            voice_tts_errors_total.labels(error_type="timeout", voice_name=voice).inc()
            voice_tts_requests_total.labels(status="error", voice_name=voice).inc()
            raise TTSProviderError(
                code="provider_timeout",
                message=f"Gemini TTS timed out after {self._timeout_seconds}s",
            ) from exc
        except httpx.HTTPError as exc:
            voice_tts_errors_total.labels(error_type="http", voice_name=voice).inc()
            voice_tts_requests_total.labels(status="error", voice_name=voice).inc()
            raise TTSProviderError(
                code="provider_network_error",
                message="Gemini TTS transport error",
                details={"exception_type": type(exc).__name__},
            ) from exc
        voice_tts_latency_seconds.labels(voice_name=voice).observe(time.perf_counter() - start)
        if response.status_code >= 400:
            self._raise_for_status(response, voice)
        return response

    def _raise_for_status(self, response: httpx.Response, voice: str) -> None:
        status = response.status_code
        voice_tts_errors_total.labels(error_type=f"http_{status}", voice_name=voice).inc()
        voice_tts_requests_total.labels(status="error", voice_name=voice).inc()
        vendor = _vendor_status(response)
        # Its facts, never its prose: a refusal on every line of a radio session was
        # visible nowhere but in the music that kept playing (2026-09-26).
        logger.warning(
            "gemini_tts_http_error", model=self.model, status_code=status, vendor_status=vendor
        )
        if status == 429:
            retry_after: float | None = None
            with suppress(TypeError, ValueError):
                retry_after = float(response.headers.get("Retry-After", ""))
            raise TTSProviderError(
                code="provider_rate_limited",
                message=f"Gemini TTS rate limited ({vendor})",
                retry_after_seconds=retry_after,
                details={"status_code": status},
            )
        raise TTSProviderError(
            code="provider_http_error",
            message=f"Gemini TTS returned HTTP {status} ({vendor})",
            details={"status_code": status, "vendor_status": vendor},
        )

    @staticmethod
    def _count_failure(error_type: str, voice: str) -> None:
        """Count a synthesis that answered 200 and still failed."""
        voice_tts_errors_total.labels(error_type=error_type, voice_name=voice).inc()
        voice_tts_requests_total.labels(status="error", voice_name=voice).inc()

    def _raise_without_audio(self, payload: object, voice: str) -> NoReturn:
        """Refuse an answer that carries no audio, saying what the vendor counted.

        Never observed (measured 2026-09-26: seven inputs built to draw
        silence — punctuation, emoji, a bare URL, « stay silent », a digit,
        invisible characters — all came back spoken; an empty one is refused
        with a 400 and no usage). Should it happen, the tokens the vendor
        reported are logged: a spend nobody records must at least be seen.
        """
        self._count_failure("empty_response", voice)
        tokens_in, tokens_out = _reported_tokens(payload) if isinstance(payload, dict) else (0, 0)
        logger.warning(
            "gemini_tts_no_audio",
            model=self.model,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
        )
        raise TTSProviderError(
            code="provider_invalid_response",
            message="Gemini TTS answered no audio",
            details={"input_tokens": tokens_in, "output_tokens": tokens_out},
        )

    async def synthesize_with_usage(
        self, text: str, voice_name: str | None = None, **kwargs: object
    ) -> SynthesisResult:
        """Synthesize ``text`` and return the audio with the vendor's usage.

        Args:
            text: What to say.
            voice_name: A prebuilt voice (``Kore``, ``Puck``…).
            **kwargs: ``style`` — a natural-language direction of how the line
                should sound. Anything else is ignored (protocol compatibility).

        Returns:
            The audio in :attr:`audio_format`, and the billed tokens.

        Raises:
            TTSProviderError: On a missing voice, a transport or HTTP failure,
                or an answer without audio.
        """
        if not voice_name:
            raise TTSProviderError(code="voice_missing", message="Gemini TTS needs a voice")
        style = kwargs.get("style")
        body = self._body(text, voice_name, style if isinstance(style, str) else None)
        response = await self._post(body, voice_name)
        try:
            payload = response.json()
        except ValueError as exc:
            self._count_failure("invalid_response", voice_name)
            raise TTSProviderError(
                code="provider_invalid_response", message="Gemini TTS answered no JSON"
            ) from exc
        part = _audio_part(payload) if isinstance(payload, dict) else None
        if part is None or not part[0]:
            self._raise_without_audio(payload, voice_name)
        audio = _playable(base64.b64decode(part[0]), part[1])
        if self._output_format == "mp3":
            try:
                audio = await transcode(
                    audio,
                    output_format="mp3",
                    args=["-codec:a", "libmp3lame", "-b:a", f"{self._mp3_bitrate_kbps}k"],
                    timeout_s=self._timeout_seconds,
                )
            except FfmpegError as exc:
                self._count_failure("encoding_error", voice_name)
                raise TTSProviderError(
                    code="provider_invalid_response",
                    message="Gemini TTS audio could not be encoded",
                ) from exc
        usage = _usage(payload)
        if usage is None:
            # Priced per character instead: under-billed, never billed at nothing.
            logger.warning("gemini_tts_usage_missing", model=self.model, characters=len(text))
        voice_tts_requests_total.labels(status="success", voice_name=voice_name).inc()
        logger.debug(
            "gemini_tts_synthesised",
            model=self.model,
            voice=voice_name,
            characters=len(text),
            audio_bytes=len(audio),
            usage=usage,
        )
        return SynthesisResult(
            audio=audio,
            characters=len(text),
            input_tokens=usage[0] if usage else None,
            output_tokens=usage[1] if usage else None,
        )

    async def synthesize(self, text: str, voice_name: str | None = None, **kwargs: object) -> bytes:
        """Synthesize ``text`` (protocol surface; the usage is dropped)."""
        return (await self.synthesize_with_usage(text, voice_name, **kwargs)).audio

    async def synthesize_base64(
        self, text: str, voice_name: str | None = None, **kwargs: object
    ) -> str:
        """Synthesize ``text`` as base64 (protocol surface)."""
        audio = await self.synthesize(text, voice_name, **kwargs)
        return base64.b64encode(audio).decode("ascii")

    async def close(self) -> None:
        """Close the persistent HTTP client."""
        # Already closed, or its loop already gone: nothing left to release.
        with suppress(RuntimeError, httpx.HTTPError):
            await self._http_client.aclose()


__all__ = ["GEMINI_API_BASE_URL", "GeminiTTSClient"]
