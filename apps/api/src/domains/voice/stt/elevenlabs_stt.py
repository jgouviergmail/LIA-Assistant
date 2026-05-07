"""ElevenLabs Scribe Speech-To-Text service.

Calls ``POST {base_url}/speech-to-text`` with the raw PCM Int16 LE mono
buffer received from the frontend (no WAV wrapping needed: the
``file_format=pcm_s16le_16`` payload field tells ElevenLabs to consume the
buffer as raw 16-bit PCM at 16 kHz, mono, little-endian — matches our
``VOICE_INPUT_SAMPLE_RATE`` exactly).

Pricing is audio-billed (e.g. Scribe v2 at $0.22/hour). Cost computation
runs separately in the persistence layer via
``infrastructure.cache.pricing_cache.get_cached_cost_audio_usd_eur``;
this service only returns the authoritative ``audio_duration_seconds``
returned by the provider so the cost computation matches exactly what
ElevenLabs bills for.
"""

from __future__ import annotations

import httpx
import structlog

from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.protocol import STTResult

logger = structlog.get_logger(__name__)


# ISO-639-1 codes for the 6 LIA UI languages. Anything outside this set is
# omitted from the request, letting ElevenLabs auto-detect the language.
_VALID_ISO_639_1: frozenset[str] = frozenset({"en", "fr", "de", "es", "it", "zh"})


class ElevenLabsSttService:
    """Speech-To-Text via the ElevenLabs Scribe API."""

    def __init__(
        self,
        api_key: str,
        model: str = "scribe_v2",
        base_url: str = "https://api.elevenlabs.io/v1",
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise STTProviderError(
                code="elevenlabs_api_key_missing",
                message="ElevenLabs API key is not configured",
            )
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def transcribe_pcm_int16_async(
        self,
        pcm_int16_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> STTResult:
        if not pcm_int16_bytes:
            return STTResult(text="", audio_duration_seconds=0.0, language_code=language)

        if sample_rate != 16000:
            # The pcm_s16le_16 ElevenLabs format expects exactly 16 kHz.
            # The frontend always streams at 16 kHz; reject anything else
            # rather than silently mistranscribing.
            raise STTProviderError(
                code="provider_invalid_response",
                message=f"Unsupported sample rate for ElevenLabs Scribe: {sample_rate}Hz (must be 16000Hz)",
            )

        url = f"{self._base_url}/speech-to-text"
        headers = {
            "xi-api-key": self._api_key,
            "Accept": "application/json",
        }
        files = {
            "file": ("audio.pcm", pcm_int16_bytes, "application/octet-stream"),
        }
        data: dict[str, str] = {
            "model_id": self._model,
            "file_format": "pcm_s16le_16",
            "tag_audio_events": "false",
            "timestamps_granularity": "none",
        }
        if language and language.lower() in _VALID_ISO_639_1:
            data["language_code"] = language.lower()

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(url, headers=headers, files=files, data=data)
        except TimeoutError as e:
            raise STTProviderError(
                code="provider_timeout",
                message=f"ElevenLabs request timed out after {self._timeout_seconds}s",
            ) from e
        except httpx.TimeoutException as e:
            raise STTProviderError(
                code="provider_timeout",
                message=str(e) or "ElevenLabs request timed out",
            ) from e
        except httpx.HTTPError as e:
            raise STTProviderError(
                code="provider_http_error",
                message=f"ElevenLabs HTTP error: {e}",
            ) from e

        if response.status_code == 429:
            retry_after_header = response.headers.get("Retry-After")
            try:
                retry_after = float(retry_after_header) if retry_after_header else None
            except ValueError:
                retry_after = None
            raise STTProviderError(
                code="provider_rate_limited",
                message="ElevenLabs rate limit hit",
                retry_after_seconds=retry_after,
            )

        if response.status_code >= 400:
            # Body kept short on purpose — useful for logs without flooding.
            body_excerpt = response.text[:512]
            raise STTProviderError(
                code="provider_http_error",
                message=f"ElevenLabs returned HTTP {response.status_code}",
                details=body_excerpt,
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise STTProviderError(
                code="provider_invalid_response",
                message="ElevenLabs response is not valid JSON",
            ) from e

        text = payload.get("text")
        duration = payload.get("audio_duration_secs")
        if not isinstance(text, str) or not isinstance(duration, (int, float)):
            raise STTProviderError(
                code="provider_invalid_response",
                message="ElevenLabs response missing 'text' or 'audio_duration_secs'",
                details=payload,
            )

        resolved_language = payload.get("language_code")
        logger.info(
            "elevenlabs_stt_completed",
            model=self._model,
            audio_duration_seconds=float(duration),
            text_length=len(text),
            language=resolved_language,
        )
        return STTResult(
            text=text,
            audio_duration_seconds=float(duration),
            language_code=resolved_language if isinstance(resolved_language, str) else None,
        )
