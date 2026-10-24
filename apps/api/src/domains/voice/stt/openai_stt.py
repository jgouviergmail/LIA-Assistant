"""OpenAI speech-to-text service (``POST /v1/audio/transcriptions``).

Second remote engine of the meetings feature (ADR-258) and the fallback when
no ElevenLabs key is configured: most self-hosted instances already hold an
OpenAI key for their LLM slots. Measured live 2026-09-02: ``gpt-4o-mini-
transcribe`` transcribes a 53 s WebM in 2.7 s; ``gpt-4o-transcribe-diarize``
with ``response_format=diarized_json`` separates two speakers into segments
``{speaker, start, end, text}`` in 24 s; Ogg/Opus is accepted although the
documentation lists only mp3/mp4/mpeg/mpga/m4a/wav/webm.

Provider constraints the caller must respect: **25 MB per request** (the
meetings normalizer keeps the whole recording under it), and diarization only
on the ``-diarize`` model. Pricing is audio-billed per minute and administered
in ``llm_model_pricing``; this service only returns the duration.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from src.core.constants import OPENAI_STT_DIARIZE_MODEL_DEFAULT
from src.domains.voice.stt.audio_file import open_audio_file
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.protocol import STTFileResult, STTResult, TranscriptWord
from src.domains.voice.vendor_refusal import (
    OPENAI_CODE_PATHS,
    payload_shape,
    refusal_from_body,
    retry_after_of,
)
from src.infrastructure.file_transfer import LocalFileRead
from src.infrastructure.media.wav import wav_bytes
from src.infrastructure.multipart_upload import FormFile, multipart_upload

logger = structlog.get_logger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_VALID_ISO_639_1: frozenset[str] = frozenset({"en", "fr", "de", "es", "it", "zh"})


class OpenAISttService:
    """Speech-To-Text via the OpenAI transcriptions API."""

    def __init__(
        self,
        api_key: str,
        model: str = OPENAI_STT_DIARIZE_MODEL_DEFAULT,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key:
            raise STTProviderError(
                code="openai_api_key_missing", message="OpenAI API key is not configured"
            )
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def supports_diarization(self) -> bool:
        """Only the ``-diarize`` model returns speaker labels."""
        return self._model.endswith("-diarize")

    async def transcribe_pcm_int16_async(
        self,
        pcm_int16_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> STTResult:
        """WebSocket parity: raw PCM wrapped in a WAV header (OpenAI has no raw-PCM format)."""
        if not pcm_int16_bytes:
            return STTResult(text="", audio_duration_seconds=0.0, language_code=language)
        wav = wav_bytes(pcm_int16_bytes, sample_rate)
        result = await self._post(
            wav,
            "audio.wav",
            "audio/wav",
            diarize=False,
            language=language,
            timeout_seconds=self._timeout_seconds,
        )
        return STTResult(
            text=result.text,
            audio_duration_seconds=result.audio_duration_seconds
            or len(pcm_int16_bytes) / (sample_rate * 2),
            language_code=result.language_code or language,
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
        """Transcribe a whole file; diarization when the model supports it.

        The file is streamed from disk, every read in a worker thread (AC-035).
        """
        audio = await open_audio_file(path)
        try:
            return await self._post(
                audio,
                path.rsplit("/", 1)[-1],
                mime_type,
                diarize=diarize and self.supports_diarization,
                language=language,
                timeout_seconds=timeout_seconds,
            )
        finally:
            await audio.close()

    async def _post(
        self,
        audio: bytes | LocalFileRead,
        filename: str,
        mime_type: str,
        *,
        diarize: bool,
        language: str | None,
        timeout_seconds: float,
    ) -> STTFileResult:
        data = self._request_data(diarize=diarize, language=language)
        response = await self._send(
            audio, filename, mime_type, data=data, timeout_seconds=timeout_seconds
        )
        self._raise_for_status(response)
        result = self._parse_payload(self._json_payload(response), language=language)
        logger.info(
            "openai_stt_file_completed",
            model=self._model,
            audio_duration_seconds=result.audio_duration_seconds,
            segments=len(result.words),
            speakers=len({w.speaker for w in result.words if w.speaker}),
        )
        return result

    def _request_data(self, *, diarize: bool, language: str | None) -> dict[str, str]:
        """Form fields of a transcription request (diarized JSON needs auto chunking)."""
        data: dict[str, str] = {"model": self._model}
        if diarize:
            data["response_format"] = "diarized_json"
            data["chunking_strategy"] = "auto"
        else:
            data["response_format"] = "json"
        if language and language.lower() in _VALID_ISO_639_1:
            data["language"] = language.lower()
        return data

    async def _send(
        self,
        audio: bytes | LocalFileRead,
        filename: str,
        mime_type: str,
        *,
        data: dict[str, str],
        timeout_seconds: float,
    ) -> httpx.Response:
        """POST the multipart request; transport failures become classified errors."""
        url = f"{self._base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        upload = multipart_upload(data, FormFile("file", filename, mime_type), audio)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                return await client.post(
                    url, headers={**headers, **upload.headers}, content=upload.content
                )
        except httpx.TimeoutException as e:
            raise STTProviderError(
                code="provider_timeout",
                message=str(e) or f"OpenAI request timed out after {timeout_seconds}s",
            ) from e
        except httpx.HTTPError as e:
            raise STTProviderError(
                code="provider_http_error", message=f"OpenAI HTTP error: {e}"
            ) from e

    @staticmethod
    def _json_payload(response: httpx.Response) -> dict[str, Any]:
        """The JSON object of a 2xx response, or ``provider_invalid_response``."""
        try:
            payload = response.json()
        except ValueError as e:
            raise STTProviderError(
                code="provider_invalid_response", message="OpenAI response is not valid JSON"
            ) from e
        if not isinstance(payload, dict):
            raise STTProviderError(
                code="provider_invalid_response", message="OpenAI response is not an object"
            )
        return payload

    @staticmethod
    def _segment_word(segment: dict[str, Any]) -> TranscriptWord:
        """A diarized SEGMENT is a speaker turn — one word-shaped entry keeps one contract."""
        speaker = segment.get("speaker")
        return TranscriptWord(
            text=str(segment.get("text", "")).strip(),
            start=float(segment.get("start", 0.0) or 0.0),
            end=float(segment.get("end", 0.0) or 0.0),
            speaker=str(speaker) if speaker is not None else None,
        )

    def _parse_payload(self, payload: dict[str, Any], *, language: str | None) -> STTFileResult:
        """Validate the transcription payload and shape it as ``STTFileResult``."""
        text = payload.get("text")
        if not isinstance(text, str):
            # The answer is the person's words: it travels by its keys alone (ADR-317).
            raise STTProviderError(
                code="provider_invalid_response",
                message="OpenAI response missing 'text'",
                details=payload_shape(payload),
            )
        words = [
            self._segment_word(segment)
            for segment in payload.get("segments", []) or []
            if isinstance(segment, dict)
        ]
        duration = payload.get("duration")
        duration_seconds = float(duration) if isinstance(duration, (int, float)) else 0.0
        if duration_seconds <= 0.0 and words:
            duration_seconds = max(w.end for w in words)
        return STTFileResult(
            text=text,
            words=words,
            audio_duration_seconds=duration_seconds,
            language_code=language,
            diarized=any(w.speaker for w in words),
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Map an HTTP failure to a classified ``STTProviderError`` — by its facts alone.

        A refused body may quote what was being transcribed, so the error and
        its log line carry the status and the vendor's bounded code, never the
        body (ADR-317).
        """
        if response.status_code < 400:
            return
        refusal = refusal_from_body(response, *OPENAI_CODE_PATHS)
        logger.warning(
            "openai_stt_http_error", status_code=refusal.status, vendor_code=refusal.vendor_code
        )
        if refusal.status == 429:
            raise STTProviderError(
                code="provider_rate_limited",
                message="OpenAI rate limit hit",
                retry_after_seconds=retry_after_of(response),
                details=refusal.details(),
            )
        if refusal.status == 401:
            raise STTProviderError(
                code="invalid_api_key",
                message="OpenAI rejected the configured API key",
                details=refusal.details(),
            )
        if refusal.status == 413:
            raise STTProviderError(
                code="provider_file_too_large",
                message="OpenAI refused the file size (25 MB per request)",
                details=refusal.details(),
            )
        raise STTProviderError(
            code="provider_http_error",
            message=f"OpenAI returned HTTP {refusal.status}",
            details=refusal.details(),
        )
