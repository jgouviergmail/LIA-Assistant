"""ElevenLabs Text-to-Speech client.

Implements the :class:`TTSClient` protocol for ElevenLabs voices.
Endpoint: ``POST /v1/text-to-speech/{voice_id}`` with the text payload
and an optional ``voice_settings`` block. Returns the audio bytes for
the requested format (MP3 by default).

API key permissions required:
- ``text_to_speech`` to call the TTS endpoint.
- ``voices_read`` to populate the admin voice picker (handled separately
  by ``voices_catalog.get_elevenlabs_voices``).
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx
import structlog

from src.core.constants import DEFAULT_ELEVENLABS_BASE_URL
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.exceptions import TTSProviderError
from src.infrastructure.observability.metrics_voice import (
    voice_tts_errors_total,
    voice_tts_latency_seconds,
    voice_tts_requests_total,
)

logger = structlog.get_logger(__name__)

# Audio formats supported by ElevenLabs TTS that map cleanly onto LIA's
# downstream playback. The provider exposes more variants (e.g. pcm_16000,
# pcm_22050, mp3_22050_32) — we expose only the high-quality MP3 default
# and leave room to extend via provider_config if a use-case ever asks.
_DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
# Output formats whose decoding shape isn't MP3 (kept for future-proofing).
_NON_MP3_FORMATS = frozenset({"pcm_16000", "pcm_22050", "pcm_24000", "pcm_44100", "ulaw_8000"})


class ElevenLabsTTSClient:
    """ElevenLabs TTS client.

    Constructed by the factory with the active provider config. The
    ``model_id`` (one of ``eleven_multilingual_v2`` / ``eleven_turbo_v2_5``
    / ``eleven_flash_v2_5``) drives both the synthesis quality and the
    pricing row used by the cost tracker downstream.
    """

    def __init__(
        self,
        model: str = "eleven_turbo_v2_5",
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
        output_format: str = _DEFAULT_OUTPUT_FORMAT,
        voice_settings: dict[str, Any] | None = None,
    ) -> None:
        api_key = LLMConfigOverrideCache.get_api_key("elevenlabs")
        if not api_key:
            raise TTSProviderError(
                code="api_key_missing",
                message=(
                    "ElevenLabs API key is not configured — TTS cannot synthesise. "
                    "Add the key under Tarification LLM Texte → Provider Keys."
                ),
            )
        self._api_key = api_key
        self.model = model
        self._base_url = (base_url or DEFAULT_ELEVENLABS_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._output_format = output_format
        self._voice_settings = voice_settings or {}

        # Persistent HTTP client — one per TTSClient instance. Reusing the
        # same connection across calls saves ~100–300 ms per synthesis (TLS
        # handshake + DNS + TCP setup); critical when synthesising several
        # short sentences in a row (sentence streaming flow).
        self._http_client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=self._timeout_seconds,
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=60.0,
            ),
            headers={
                "xi-api-key": self._api_key,
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # TTSClient protocol surface
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "elevenlabs"

    @property
    def audio_format(self) -> str:
        # The TTSClient protocol expects a short MIME-like extension token.
        if self._output_format in _NON_MP3_FORMATS:
            return self._output_format.split("_", 1)[0]  # "pcm" / "ulaw"
        return "mp3"

    async def synthesize(
        self,
        text: str,
        voice_name: str | None = None,
        **_: Any,
    ) -> bytes:
        """Synthesise ``text`` to audio bytes using ``voice_name`` (= voice_id).

        Returns the raw bytes; format is given by :attr:`audio_format`.
        """
        if not voice_name:
            raise ValueError("ElevenLabs TTS requires an explicit voice_id (voice_name).")

        voice_id = voice_name
        url = f"{self._base_url}/text-to-speech/{voice_id}"
        params = {"output_format": self._output_format}
        body: dict[str, Any] = {
            "text": text,
            "model_id": self.model,
        }
        if self._voice_settings:
            body["voice_settings"] = self._voice_settings

        # Align with the shared voice_tts_* Prometheus counters which carry
        # ["voice_name"] (latency / requests) and ["error_type", "voice_name"]
        # (errors). Using extra labels (e.g. ``provider``) raises
        # ``Incorrect label names`` at the prometheus_client library level and
        # silently breaks every TTS request — provider is implicit via
        # voice_id pattern (UUID = ElevenLabs, short = OpenAI).
        start = time.perf_counter()
        try:
            # Reuse the persistent client (default headers already set).
            response = await self._http_client.post(url, params=params, json=body)
        except (TimeoutError, httpx.TimeoutException) as exc:
            voice_tts_errors_total.labels(error_type="timeout", voice_name=voice_id).inc()
            voice_tts_requests_total.labels(status="error", voice_name=voice_id).inc()
            raise TTSProviderError(
                code="provider_timeout",
                message=f"ElevenLabs TTS timed out after {self._timeout_seconds}s",
            ) from exc
        except httpx.HTTPError as exc:
            voice_tts_errors_total.labels(error_type="http", voice_name=voice_id).inc()
            voice_tts_requests_total.labels(status="error", voice_name=voice_id).inc()
            raise TTSProviderError(
                code="provider_network_error",
                message=f"ElevenLabs TTS HTTP error: {exc}",
                details={"exception_type": type(exc).__name__},
            ) from exc

        latency = time.perf_counter() - start
        voice_tts_latency_seconds.labels(voice_name=voice_id).observe(latency)

        if response.status_code >= 400:
            voice_tts_errors_total.labels(
                error_type=f"http_{response.status_code}", voice_name=voice_id
            ).inc()
            voice_tts_requests_total.labels(status="error", voice_name=voice_id).inc()
            # Distinguish rate limiting (429) from generic 4xx/5xx so the
            # streamer can surface a precise Retry-After when the provider
            # supplies one.
            if response.status_code == 429:
                retry_after_raw = response.headers.get("Retry-After")
                retry_after_seconds: float | None = None
                if retry_after_raw is not None:
                    try:
                        retry_after_seconds = float(retry_after_raw)
                    except (TypeError, ValueError):
                        retry_after_seconds = None
                raise TTSProviderError(
                    code="provider_rate_limited",
                    message=f"ElevenLabs TTS rate limited: {response.text[:200]}",
                    retry_after_seconds=retry_after_seconds,
                    details={"status_code": 429},
                )
            raise TTSProviderError(
                code="provider_http_error",
                message=(
                    f"ElevenLabs TTS returned HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                ),
                details={"status_code": response.status_code},
            )

        voice_tts_requests_total.labels(status="success", voice_name=voice_id).inc()
        logger.debug(
            "elevenlabs_tts_synthesised",
            model=self.model,
            voice_id=voice_id,
            audio_bytes=len(response.content),
            latency_s=round(latency, 3),
        )
        return response.content

    async def synthesize_base64(
        self,
        text: str,
        voice_name: str | None = None,
        **kwargs: Any,
    ) -> str:
        audio = await self.synthesize(text, voice_name=voice_name, **kwargs)
        return base64.b64encode(audio).decode("ascii")

    async def close(self) -> None:
        """Close the persistent httpx client and release pooled connections."""
        try:
            await self._http_client.aclose()
        except Exception:
            # Already closed or never opened; non-fatal.
            pass
