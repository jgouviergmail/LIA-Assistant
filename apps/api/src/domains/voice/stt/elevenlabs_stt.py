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

from typing import Any, Final

import httpx
import structlog

from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.protocol import STTFileResult, STTResult, TranscriptWord
from src.domains.voice.vendor_refusal import (
    ELEVENLABS_CODE_PATHS,
    payload_shape,
    refusal_from_body,
    retry_after_of,
)

logger = structlog.get_logger(__name__)


# ISO-639-1 codes for the 6 LIA UI languages. Anything outside this set is
# omitted from the request, letting ElevenLabs auto-detect the language.
_VALID_ISO_639_1: frozenset[str] = frozenset({"en", "fr", "de", "es", "it", "zh"})
#: Vendor codes naming the configured key as the cause, whatever the status: a
#: key ID stored in place of a key answered 400 ``api_key_id_used_as_api_key``
#: (2026-09-02); a key lacking the operation's permission answers 401
#: ``missing_permissions`` (seen) or 403 ``insufficient_permissions`` (documented).
_KEY_REFUSALS: Final[frozenset[str]] = frozenset(
    {
        "invalid_api_key",
        "missing_api_key",
        "api_key_id_used_as_api_key",
        "missing_permissions",
        "insufficient_permissions",
    }
)


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

        self._raise_for_status(response)
        payload = self._json_payload(response)
        text, duration = self._text_and_duration(payload)
        resolved_language = payload.get("language_code")
        logger.info(
            "elevenlabs_stt_completed",
            model=self._model,
            audio_duration_seconds=duration,
            text_length=len(text),
            language=resolved_language,
        )
        return STTResult(
            text=text,
            audio_duration_seconds=duration,
            language_code=resolved_language if isinstance(resolved_language, str) else None,
        )

    async def transcribe_file_async(
        self,
        path: str,
        mime_type: str,
        *,
        diarize: bool,
        language: str | None,
        timeout_seconds: float,
    ) -> STTFileResult:
        """Transcribe a whole audio file (meetings, ADR-258) with optional diarization.

        Scribe accepts every major container up to 5 GB and returns one
        ``speaker_id`` per word when ``diarize`` is set (measured live
        2026-09-02: a two-voice Ogg/Opus dialogue came back with two speakers,
        a WebM truncated at 60 % of its bytes was still accepted). The file is
        streamed from disk by httpx, never loaded into memory here.
        """
        data = self._file_request_data(diarize=diarize, language=language)
        response = await self._post_file(
            path, mime_type, data=data, timeout_seconds=timeout_seconds
        )
        self._raise_for_status(response)
        result = self._parse_file_payload(self._json_payload(response), diarize=diarize)
        logger.info(
            "elevenlabs_stt_file_completed",
            model=self._model,
            audio_duration_seconds=result.audio_duration_seconds,
            words=len(result.words),
            speakers=len({w.speaker for w in result.words if w.speaker}),
            language=result.language_code,
        )
        return result

    def _file_request_data(self, *, diarize: bool, language: str | None) -> dict[str, str]:
        """Form fields of a Scribe file request."""
        data = {
            "model_id": self._model,
            "diarize": "true" if diarize else "false",
            "timestamps_granularity": "word",
            "tag_audio_events": "false",
        }
        if language and language.lower() in _VALID_ISO_639_1:
            data["language_code"] = language.lower()
        return data

    async def _post_file(
        self, path: str, mime_type: str, *, data: dict[str, str], timeout_seconds: float
    ) -> httpx.Response:
        """Stream the file to Scribe; transport failures become classified errors."""
        url = f"{self._base_url}/speech-to-text"
        headers = {"xi-api-key": self._api_key, "Accept": "application/json"}
        try:
            with open(path, "rb") as handle:
                files = {"file": (path.rsplit("/", 1)[-1], handle, mime_type)}
                async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                    return await client.post(url, headers=headers, files=files, data=data)
        except OSError as e:
            raise STTProviderError(
                code="provider_http_error", message=f"Audio file unreadable: {e.__class__.__name__}"
            ) from e
        except httpx.TimeoutException as e:
            raise STTProviderError(
                code="provider_timeout",
                message=str(e) or f"ElevenLabs request timed out after {timeout_seconds}s",
            ) from e
        except httpx.HTTPError as e:
            raise STTProviderError(
                code="provider_http_error", message=f"ElevenLabs HTTP error: {e}"
            ) from e

    @staticmethod
    def _json_payload(response: httpx.Response) -> dict[str, Any]:
        """The JSON object of a 2xx response, or ``provider_invalid_response``."""
        try:
            payload = response.json()
        except ValueError as e:
            raise STTProviderError(
                code="provider_invalid_response", message="ElevenLabs response is not valid JSON"
            ) from e
        if not isinstance(payload, dict):
            raise STTProviderError(
                code="provider_invalid_response", message="ElevenLabs response is not an object"
            )
        return payload

    @staticmethod
    def _word_from_payload(word: dict[str, Any]) -> TranscriptWord:
        speaker = word.get("speaker_id")
        return TranscriptWord(
            text=str(word.get("text", "")),
            start=float(word.get("start", 0.0) or 0.0),
            end=float(word.get("end", 0.0) or 0.0),
            speaker=str(speaker) if speaker is not None else None,
        )

    @staticmethod
    def _text_and_duration(payload: dict[str, Any]) -> tuple[str, float]:
        """The transcription and its billed duration, or ``provider_invalid_response``.

        The answer is the person's words, so a payload LIA cannot read travels
        by its keys alone (ADR-317).
        """
        text = payload.get("text")
        duration = payload.get("audio_duration_secs")
        if not isinstance(text, str) or not isinstance(duration, (int, float)):
            raise STTProviderError(
                code="provider_invalid_response",
                message="ElevenLabs response missing 'text' or 'audio_duration_secs'",
                details=payload_shape(payload),
            )
        return text, float(duration)

    def _parse_file_payload(self, payload: dict[str, Any], *, diarize: bool) -> STTFileResult:
        """Validate the Scribe file payload and shape it as ``STTFileResult``."""
        text, duration = self._text_and_duration(payload)
        words = [
            self._word_from_payload(word)
            for word in payload.get("words", [])
            if isinstance(word, dict) and word.get("type", "word") == "word"
        ]
        resolved_language = payload.get("language_code")
        return STTFileResult(
            text=text,
            words=words,
            audio_duration_seconds=duration,
            language_code=resolved_language if isinstance(resolved_language, str) else None,
            diarized=diarize and any(w.speaker for w in words),
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Map an HTTP failure to a classified ``STTProviderError`` — by its facts alone.

        A refused body may quote what was being transcribed, so the error and
        its log line carry the status and the vendor's bounded code, never the
        body (ADR-317). A vendor code naming the key, whatever the status, or a
        refused authentication (401) naming no other cause is ``invalid_api_key``:
        the user is told to fix the admin setting rather than to retry. The code
        decides first — the vendor answers ``quota_exceeded`` with 400 or 401 too.
        """
        if response.status_code < 400:
            return
        refusal = refusal_from_body(response, *ELEVENLABS_CODE_PATHS)
        logger.warning(
            "elevenlabs_stt_http_error",
            status_code=refusal.status,
            vendor_code=refusal.vendor_code,
        )
        if refusal.status == 429:
            raise STTProviderError(
                code="provider_rate_limited",
                message="ElevenLabs rate limit hit",
                retry_after_seconds=retry_after_of(response),
                details=refusal.details(),
            )
        if refusal.vendor_code in _KEY_REFUSALS or (
            refusal.status == 401 and refusal.vendor_code is None
        ):
            raise STTProviderError(
                code="invalid_api_key",
                message="ElevenLabs rejected the configured API key",
                details=refusal.details(),
            )
        if refusal.vendor_code == "audio_too_short":
            raise STTProviderError(
                code="provider_audio_too_short",
                message="ElevenLabs requires a longer audio recording",
                details=refusal.details(),
            )
        raise STTProviderError(
            code="provider_http_error",
            message=f"ElevenLabs returned HTTP {refusal.status}",
            details=refusal.details(),
        )
