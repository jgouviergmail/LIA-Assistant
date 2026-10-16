"""Fish Audio speech-to-text (``POST /v1/asr``): the voice mode's clip and a meeting's file (ADR-345).

Read from the vendor's documentation on 2026-10-14 — no paid transcription was
run (owner decision: no paid validation):

- the ``model`` header picks ``transcribe-1`` or ``transcribe-1-pro``; a missing
  or inexact one is served AND billed as ``transcribe-1``, so this client always
  names its model;
- the audio is a multipart ``audio`` file in a container: raw PCM is refused, so
  the voice mode's samples are wrapped in WAV;
- ``transcribe-1-pro`` writes speaker markers (``<|speaker:N|>``) INSIDE ``text``
  even with diarization off, and emotion cues unless ``tag_audio_events=false``:
  LIA's transcript is the words alone;
- with timestamps, the pro model answers ``speaker_turns``, each kept here as one
  word-shaped entry (the contract OpenAI's diarized segments already follow);
- the fields beyond ``audio``, ``language`` and ``ignore_timestamps`` are the pro
  model's only, and are sent to it alone;
- up to 60 minutes per request (longer: 400 ``audio_too_long``), billed per audio
  hour on the duration ROUNDED UP to the second — the duration returned here is
  that billed one;
- every request holds one slot of the account's concurrency, shared with
  synthesis and voice design (the ``fishaudio`` capacity pool).

A refusal is classified by its status and the vendor's bounded code; its body
never travels — it may quote the words transcribed.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, BinaryIO, Final

import httpx
import structlog

from src.core.constants import (
    DEFAULT_FISHAUDIO_BASE_URL,
    FISHAUDIO_PROVIDER_NAME,
    FISHAUDIO_STT_MODEL_DEFAULT,
)
from src.domains.voice.fishaudio.wire import auth_headers, refusal_of
from src.domains.voice.provider_capacity import ProviderCapacityUnavailable, provider_slot
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.protocol import STTFileResult, STTResult, TranscriptWord
from src.infrastructure.media.wav import wav_bytes

logger = structlog.get_logger(__name__)

#: The model that marks speakers and takes the pro-only fields.
_PRO: Final[str] = "transcribe-1-pro"
#: The ISO-639-1 hints worth sending (the vendor may refuse any other form).
_VALID_ISO_639_1: Final[frozenset[str]] = frozenset({"en", "fr", "de", "es", "it", "zh"})
#: A speaker marker the pro model writes inside its text.
_SPEAKER_MARKER: Final[re.Pattern[str]] = re.compile(r"<\|speaker:\d{1,3}\|>")
_BLANKS: Final[re.Pattern[str]] = re.compile(r"\s+")
#: The vendor codes that name a recording longer than one request takes.
_TOO_LONG: Final[frozenset[str]] = frozenset({"audio_too_long"})


def _words_only(text: str) -> str:
    """``text`` without the pro model's speaker markers, its blanks collapsed."""
    return _BLANKS.sub(" ", _SPEAKER_MARKER.sub(" ", text)).strip()


def _seconds(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


class FishAudioSttService:
    """Speech-To-Text via Fish Audio's ``/v1/asr``."""

    def __init__(
        self,
        api_key: str,
        model: str = FISHAUDIO_STT_MODEL_DEFAULT,
        *,
        base_url: str = DEFAULT_FISHAUDIO_BASE_URL,
        timeout_seconds: float = 60.0,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise STTProviderError(
                code="fishaudio_api_key_missing", message="Fish Audio API key is not configured"
            )
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_transport = http_transport

    @property
    def supports_diarization(self) -> bool:
        """Only ``transcribe-1-pro`` marks speakers."""
        return self._model == _PRO

    async def transcribe_pcm_int16_async(
        self,
        pcm_int16_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> STTResult:
        """Transcribe the voice mode's clip (raw PCM, wrapped in WAV: the vendor refuses raw)."""
        if not pcm_int16_bytes:
            return STTResult(text="", audio_duration_seconds=0.0, language_code=language)
        payload = await self._post(
            ("audio.wav", wav_bytes(pcm_int16_bytes, sample_rate), "audio/wav"),
            timestamps=False,
            diarize=False,
            language=language,
            timeout_seconds=self._timeout_seconds,
        )
        return STTResult(
            text=_words_only(payload["text"]),
            audio_duration_seconds=self._billed_seconds(payload),
            language_code=self._language(payload, language),
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
        """Transcribe a whole file; speaker turns when the model marks speakers.

        The file is streamed from disk by httpx, never loaded into memory here
        (a meeting runs up to an hour — the sibling engines' contract).
        """
        try:
            handle = open(path, "rb")  # noqa: SIM115 — streamed by httpx, closed below
        except OSError as exc:
            raise STTProviderError(
                code="provider_http_error",
                message=f"Audio file unreadable: {exc.__class__.__name__}",
            ) from exc
        diarized = diarize and self.supports_diarization
        try:
            payload = await self._post(
                (Path(path).name, handle, mime_type),
                timestamps=True,
                diarize=diarized,
                language=language,
                timeout_seconds=timeout_seconds,
            )
        finally:
            handle.close()
        words = self._turns(payload) if diarized else []
        if not words:
            words = self._segments(payload)
        result = STTFileResult(
            text=_words_only(payload["text"]),
            words=words,
            audio_duration_seconds=self._billed_seconds(payload),
            language_code=self._language(payload, language),
            diarized=any(word.speaker for word in words),
        )
        logger.info(
            "fishaudio_stt_file_completed",
            model=self._model,
            audio_duration_seconds=result.audio_duration_seconds,
            entries=len(result.words),
            speakers=len({word.speaker for word in result.words if word.speaker}),
        )
        return result

    # ------------------------------------------------------------------
    # Request
    # ------------------------------------------------------------------

    def _fields(self, *, timestamps: bool, diarize: bool, language: str | None) -> dict[str, str]:
        """The form fields: the pro model alone is sent its own."""
        data = {"ignore_timestamps": "false" if timestamps else "true"}
        if language and language.lower() in _VALID_ISO_639_1:
            data["language"] = language.lower()
        if self._model == _PRO:
            data["tag_audio_events"] = "false"
            data["diarize"] = "true" if diarize else "false"
        return data

    async def _post(
        self,
        audio: tuple[str, bytes | BinaryIO, str],
        *,
        timestamps: bool,
        diarize: bool,
        language: str | None,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        data = self._fields(timestamps=timestamps, diarize=diarize, language=language)
        async with self._account_slot(timeout_seconds):
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout_seconds,
                transport=self._http_transport,
                headers=auth_headers(self._api_key, model=self._model),
            ) as client:
                response = await client.post("/v1/asr", files={"audio": audio}, data=data)
        if response.status_code >= 400:
            self._raise_refusal(response)
        return self._payload(response)

    @asynccontextmanager
    async def _account_slot(self, bound_s: float) -> AsyncIterator[None]:
        """The request's share of the account, bounded whole, its failures typed."""
        try:
            async with asyncio.timeout(bound_s):
                async with provider_slot(
                    FISHAUDIO_PROVIDER_NAME, self._api_key, timeout_seconds=bound_s
                ):
                    yield
        except ProviderCapacityUnavailable as exc:
            raise STTProviderError(
                code="provider_http_error",
                message="Fish Audio capacity could not be reserved.",
                details={"stage": "capacity_reservation"},
            ) from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise STTProviderError(
                code="provider_timeout", message=f"Fish Audio ASR timed out after {bound_s}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise STTProviderError(
                code="provider_http_error",
                message="Fish Audio ASR transport error",
                details={"exception_type": type(exc).__name__},
            ) from exc

    @staticmethod
    def _raise_refusal(response: httpx.Response) -> None:
        """A refusal by its facts: status and bounded vendor code, never the body."""
        try:
            body = response.json()
        except ValueError:
            body = None
        refusal = refusal_of(
            response, body_code=body.get("code") if isinstance(body, dict) else None
        )
        status, code = refusal.status, refusal.vendor_code
        logger.warning("fishaudio_stt_http_error", status_code=status, vendor_code=code)
        if status == 429:
            raise STTProviderError(code="provider_rate_limited", message="Fish Audio rate limit")
        if status in (401, 403):
            raise STTProviderError(
                code="invalid_api_key",
                message="Fish Audio rejected the configured API key",
                details=refusal.details(),
            )
        if status == 402:
            raise STTProviderError(
                code="provider_payment_required",
                message="Fish Audio has no credit left on the configured account",
                details=refusal.details(),
            )
        if status == 413 or code in _TOO_LONG:
            raise STTProviderError(
                code="provider_file_too_large",
                message="Fish Audio refused the recording's size or length",
                details=refusal.details(),
            )
        raise STTProviderError(
            code="provider_http_error",
            message=f"Fish Audio ASR returned HTTP {status}",
            details=refusal.details(),
        )

    # ------------------------------------------------------------------
    # Answer
    # ------------------------------------------------------------------

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, Any]:
        """The transcription object, or ``provider_invalid_response`` (its body never travels)."""
        try:
            payload = response.json()
        except ValueError as exc:
            raise STTProviderError(
                code="provider_invalid_response", message="Fish Audio ASR answer is not JSON"
            ) from exc
        if not (
            isinstance(payload, dict)
            and isinstance(payload.get("text"), str)
            and isinstance(payload.get("duration"), int | float)
        ):
            raise STTProviderError(
                code="provider_invalid_response",
                message="Fish Audio ASR answer lacks its text or duration",
            )
        return payload

    @staticmethod
    def _billed_seconds(payload: dict[str, Any]) -> float:
        """The duration the vendor bills: the audio's, rounded UP to the second."""
        return float(math.ceil(max(_seconds(payload.get("duration")), 0.0)))

    @staticmethod
    def _language(payload: dict[str, Any], hint: str | None) -> str | None:
        code = payload.get("language_code")
        return code if isinstance(code, str) and code else hint

    @staticmethod
    def _turns(payload: dict[str, Any]) -> list[TranscriptWord]:
        """Each speaker turn as one word-shaped entry (OpenAI's diarized contract)."""
        return [
            TranscriptWord(
                text=text,
                start=max(_seconds(turn.get("start")), 0.0),
                end=max(_seconds(turn.get("end")), 0.0),
                speaker=str(turn["speaker"]) if turn.get("speaker") is not None else None,
            )
            for turn, text in _timed_texts(payload.get("speaker_turns"))
        ]

    @staticmethod
    def _segments(payload: dict[str, Any]) -> list[TranscriptWord]:
        """The timed words, with no speaker (the model did not mark one)."""
        return [
            TranscriptWord(
                text=text,
                start=max(_seconds(segment.get("start")), 0.0),
                end=max(_seconds(segment.get("end")), 0.0),
            )
            for segment, text in _timed_texts(payload.get("segments"))
        ]


def _timed_texts(entries: object) -> list[tuple[dict[str, Any], str]]:
    """Each timed entry with its words alone (markers removed), the empty ones left out."""
    if not isinstance(entries, list):
        return []
    pairs = [
        (entry, _words_only(str(entry.get("text", ""))))
        for entry in entries
        if isinstance(entry, dict)
    ]
    return [(entry, text) for entry, text in pairs if text]


__all__ = ["FishAudioSttService"]
