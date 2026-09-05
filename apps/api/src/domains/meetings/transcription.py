"""Transcription of a normalized meeting recording (ADR-258).

One entry point, :func:`transcribe_meeting`, dispatches on the resolved engine:

- **remote** (ElevenLabs Scribe, OpenAI) — the whole Opus file goes to the
  provider in ONE request (``SttFileTranscriberProtocol``); the words come back
  with speaker ids when the engine diarizes, and are folded into speaker turns.
  The audio-billed cost is computed from the administered pricing and recorded
  in the user's statistics like the voice path does.
- **local** (Sherpa-onnx Whisper) — the file is decoded back to 16 kHz PCM by
  ffmpeg in BLOCKS (a three-hour meeting is 345 MB of PCM; a block is 19 MB)
  and each block runs through the VAD-windowed decoder with no duration cap.

Whatever the engine, the caller's ``heartbeat`` is awaited regularly so the
processing lease stays alive during a call that may take minutes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import MEETINGS_LOCAL_BLOCK_SECONDS
from src.core.security.utils import decrypt_data
from src.domains.meetings.engine import ResolvedEngine, resolve_engine
from src.domains.meetings.models import MeetingSttEnginePreference, MeetingSttProvider
from src.domains.meetings.schemas import TranscriptTurn
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.protocol import TranscriptWord
from src.infrastructure.cache.pricing_cache import get_cached_cost_audio_usd_eur

logger = structlog.get_logger(__name__)

#: Provider error codes a later attempt cannot fix — the meeting fails for good
#: instead of burning its retry budget.
PERMANENT_STT_CODES: frozenset[str] = frozenset(
    {
        "invalid_api_key",
        "provider_file_too_large",
        "elevenlabs_api_key_missing",
        "openai_api_key_missing",
        "provider_unknown",
    }
)
#: Silence between two words of the SAME speaker above which a new turn starts.
TURN_GAP_SECONDS = 2.0
#: Stable speaker labels the minutes use (``S1``, ``S2``, …): provider ids are
#: opaque (``speaker_0``, ``A``) and change between providers.
SPEAKER_LABEL_PREFIX = "S"
#: Sample rate the local decoder expects.
_LOCAL_SAMPLE_RATE = 16000


class TranscriptionError(Exception):
    """A transcription failed; ``transient`` tells the job whether to retry."""

    def __init__(self, code: str, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.transient = transient


@dataclass(frozen=True)
class TranscriptionOutcome:
    """What an engine produced for one meeting."""

    turns: list[TranscriptTurn]
    language_code: str | None
    audio_duration_seconds: float
    provider: MeetingSttProvider
    model: str | None
    diarized: bool
    #: ``None`` when no administered price exists for the model — an unknown
    #: price is not a free one (a count shown to the user is a claim, ADR-185).
    #: The local engine reports an exact ``0.0``.
    cost_usd: float | None
    cost_eur: float | None

    @property
    def speaker_labels(self) -> list[str]:
        """Distinct speaker labels in order of first appearance."""
        seen: list[str] = []
        for turn in self.turns:
            if turn.speaker not in seen:
                seen.append(turn.speaker)
        return seen

    @property
    def text(self) -> str:
        """The transcript as plain text (one line per turn)."""
        return transcript_text(self.turns)


# ----------------------------------------------------------------------------
# Pure helpers (unit-tested without any engine)
# ----------------------------------------------------------------------------


def outcome_from_row(meeting: Any) -> TranscriptionOutcome | None:
    """The transcription a previous attempt CHECKPOINTED on the row, or ``None``.

    A claim reads this before calling an engine again: the transcript was paid
    once. ``None`` when nothing was transcribed yet or when the user deleted the
    transcript since (``transcript_deleted_at``) — then the audio is transcribed
    again. The USD figure is not stored on the row, so it comes back ``None``:
    an absent price is not a zero one (ADR-185).

    Args:
        meeting: The claimed row (``transcript_encrypted`` and the ``stt_*`` columns).
    """
    if not meeting.transcript_encrypted or meeting.transcript_deleted_at is not None:
        return None
    raw = json.loads(decrypt_data(meeting.transcript_encrypted))
    turns = [TranscriptTurn.model_validate(item) for item in raw]
    provider = MeetingSttProvider(meeting.stt_provider) if meeting.stt_provider else None
    if provider is None:
        return None
    duration = float(meeting.stt_audio_seconds or meeting.audio_duration_seconds or 0.0)
    return TranscriptionOutcome(
        turns=turns,
        language_code=meeting.stt_detected_language,
        audio_duration_seconds=duration,
        provider=provider,
        model=meeting.stt_model,
        diarized=bool(meeting.stt_diarized),
        cost_usd=None,
        cost_eur=meeting.stt_cost_eur,
    )


def speaker_label_map(words: Sequence[TranscriptWord]) -> dict[str, str]:
    """Provider speaker ids → ``S1``, ``S2``, … in order of first appearance."""
    labels: dict[str, str] = {}
    for word in words:
        if word.speaker is not None and word.speaker not in labels:
            labels[word.speaker] = f"{SPEAKER_LABEL_PREFIX}{len(labels) + 1}"
    return labels


def _clean(text: str) -> str:
    """Collapse whitespace; providers interleave ``spacing`` words with real ones."""
    return " ".join(text.split())


def build_turns(
    words: Sequence[TranscriptWord], *, fallback_speaker: str = f"{SPEAKER_LABEL_PREFIX}1"
) -> list[TranscriptTurn]:
    """Fold timestamped words into speaker turns.

    A new turn starts when the speaker changes or when the same speaker pauses
    for more than :data:`TURN_GAP_SECONDS`. Words without a speaker (a
    non-diarizing engine) all belong to ``fallback_speaker``.

    Args:
        words: Provider words, in time order.
        fallback_speaker: Label for words carrying no speaker id.

    Returns:
        Turns with non-empty text; empty when no word carries text.
    """
    labels = speaker_label_map(words)
    turns: list[TranscriptTurn] = []
    current_words: list[str] = []
    current_speaker: str | None = None
    current_start = 0.0
    current_end = 0.0

    def _flush() -> None:
        text = _clean(" ".join(current_words))
        if text and current_speaker is not None:
            turns.append(
                TranscriptTurn(
                    speaker=current_speaker, start=current_start, end=current_end, text=text
                )
            )

    for word in words:
        if not word.text.strip():
            continue
        speaker = labels.get(word.speaker or "", fallback_speaker)
        new_turn = (
            current_speaker is None
            or speaker != current_speaker
            or word.start - current_end > TURN_GAP_SECONDS
        )
        if new_turn:
            _flush()
            current_words = []
            current_speaker = speaker
            current_start = max(0.0, word.start)
        current_words.append(word.text)
        current_end = max(current_end if not new_turn else word.start, word.end, word.start)
    _flush()
    return turns


def turns_from_text(
    text: str, *, duration_seconds: float, speaker: str = f"{SPEAKER_LABEL_PREFIX}1"
) -> list[TranscriptTurn]:
    """One turn covering the whole recording (engines that return plain text)."""
    cleaned = _clean(text)
    if not cleaned:
        return []
    return [
        TranscriptTurn(speaker=speaker, start=0.0, end=max(0.0, duration_seconds), text=cleaned)
    ]


def transcript_text(turns: Sequence[TranscriptTurn]) -> str:
    """Plain-text transcript, one ``Sn: …`` line per turn."""
    return "\n".join(f"{turn.speaker}: {turn.text}" for turn in turns)


def is_transient_provider_code(code: str) -> bool:
    """Whether a provider error code deserves another attempt."""
    return code not in PERMANENT_STT_CODES


# ----------------------------------------------------------------------------
# Heartbeats
# ----------------------------------------------------------------------------


async def _run_with_heartbeats[T](
    work: Awaitable[T], heartbeat: Callable[[], Awaitable[None]], interval_seconds: float
) -> T:
    """Await ``work`` while calling ``heartbeat`` every ``interval_seconds``."""

    async def _pulse() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await heartbeat()

    pulse = asyncio.create_task(_pulse(), name="meeting_stt_heartbeat")
    try:
        return await work
    finally:
        pulse.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pulse


# ----------------------------------------------------------------------------
# Engines
# ----------------------------------------------------------------------------


async def _record_remote_spend(user_id: UUID, duration_seconds: float, cost_eur: float) -> None:
    """Account the audio-billed call in the user's statistics (best effort, logged)."""
    from src.domains.chat.service import StatisticsService

    try:
        await StatisticsService.record_remote_stt(user_id, duration_seconds, Decimal(str(cost_eur)))
    except Exception as exc:  # noqa: BLE001 — accounting must never fail the minutes
        logger.warning("meeting_stt_spend_record_failed", user_id=str(user_id), error=str(exc))


async def _transcribe_remote(
    engine: ResolvedEngine,
    *,
    audio_path: Path,
    mime_type: str,
    duration_seconds: float,
    language_hint: str | None,
    user_id: UUID,
    heartbeat: Callable[[], Awaitable[None]],
) -> TranscriptionOutcome:
    from src.domains.voice.stt.factory import build_file_transcriber

    if not engine.api_key or not engine.model:
        raise TranscriptionError(
            "provider_unknown", "remote engine resolved without key or model", transient=False
        )
    client = build_file_transcriber(
        engine.provider.value,
        api_key=engine.api_key,
        model=engine.model,
        timeout_seconds=float(settings.meetings_stt_timeout_seconds),
    )
    try:
        result = await _run_with_heartbeats(
            client.transcribe_file_async(
                str(audio_path),
                mime_type,
                diarize=engine.diarized,
                language=language_hint,
                timeout_seconds=float(settings.meetings_stt_timeout_seconds),
            ),
            heartbeat,
            float(settings.meetings_job_heartbeat_interval_seconds),
        )
    except STTProviderError as exc:
        raise TranscriptionError(
            exc.code, exc.message, transient=is_transient_provider_code(exc.code)
        ) from exc
    except (OSError, TimeoutError) as exc:
        raise TranscriptionError("provider_io_error", str(exc), transient=True) from exc

    billed_seconds = (
        float(result.audio_duration_seconds)
        if result.audio_duration_seconds and result.audio_duration_seconds > 0
        else duration_seconds
    )
    turns = build_turns(result.words) if result.words else []
    if not turns:
        turns = turns_from_text(result.text, duration_seconds=billed_seconds)
    cost_usd, cost_eur = get_cached_cost_audio_usd_eur(engine.model, billed_seconds)
    await _record_remote_spend(user_id, billed_seconds, cost_eur)
    if not turns:
        raise TranscriptionError("no_speech", "the recording contains no speech", transient=False)
    # The pricing cache answers (0, 0) for a model it does not know: that is an
    # absence of price, never a price of zero.
    priced = cost_usd > 0 or cost_eur > 0
    return TranscriptionOutcome(
        turns=turns,
        language_code=result.language_code,
        audio_duration_seconds=billed_seconds,
        provider=engine.provider,
        model=engine.model,
        diarized=bool(result.diarized),
        cost_usd=cost_usd if priced else None,
        cost_eur=cost_eur if priced else None,
    )


async def _decode_block(audio_path: Path, *, offset_seconds: float, length_seconds: float) -> bytes:
    """One block of the recording as raw 16 kHz mono int16 PCM (ffmpeg on stdout)."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{offset_seconds:.3f}",
        "-t",
        f"{length_seconds:.3f}",
        "-i",
        str(audio_path),
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        str(_LOCAL_SAMPLE_RATE),
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise TranscriptionError(
            "decode_failed", stderr.decode(errors="replace")[:200], transient=True
        )
    return stdout


async def _transcribe_local(
    *,
    audio_path: Path,
    duration_seconds: float,
    language_hint: str | None,
    heartbeat: Callable[[], Awaitable[None]],
) -> TranscriptionOutcome:
    from src.domains.voice.stt.sherpa_stt import get_stt_service

    service = get_stt_service()

    async def _on_window(_index: int, _total: int) -> None:
        await heartbeat()

    texts: list[str] = []
    # At least one block: a zero probe (a broken container) still gets one decode.
    blocks = max(1, math.ceil(max(duration_seconds, 0.0) / MEETINGS_LOCAL_BLOCK_SECONDS))
    for index in range(blocks):
        pcm = await _decode_block(
            audio_path,
            offset_seconds=index * MEETINGS_LOCAL_BLOCK_SECONDS,
            length_seconds=MEETINGS_LOCAL_BLOCK_SECONDS,
        )
        if not pcm:
            break
        text = await service.transcribe_unbounded_pcm_async(
            pcm, language=language_hint, on_window=_on_window
        )
        if text.strip():
            texts.append(text.strip())
        await heartbeat()

    turns = turns_from_text(" ".join(texts), duration_seconds=duration_seconds)
    if not turns:
        raise TranscriptionError("no_speech", "the recording contains no speech", transient=False)
    return TranscriptionOutcome(
        turns=turns,
        language_code=language_hint,
        audio_duration_seconds=duration_seconds,
        provider=MeetingSttProvider.LOCAL,
        model=None,
        diarized=False,
        cost_usd=0.0,
        cost_eur=0.0,
    )


async def transcribe_meeting(
    engine: ResolvedEngine,
    *,
    audio_path: Path,
    mime_type: str,
    duration_seconds: float,
    language_hint: str | None,
    user_id: UUID,
    heartbeat: Callable[[], Awaitable[None]],
) -> TranscriptionOutcome:
    """Transcribe the normalized recording with the resolved engine.

    Args:
        engine: Engine resolved at claim time (the truth at processing time).
        audio_path: Normalized Opus file.
        mime_type: Its MIME type (``audio/webm`` or ``audio/ogg``).
        duration_seconds: Duration measured by ffprobe (billing fallback).
        language_hint: ISO-639-1 hint, or ``None`` for auto-detection.
        user_id: Owner (spend accounting).
        heartbeat: Awaited regularly so the job lease survives the call.

    Raises:
        TranscriptionError: With ``transient`` telling the job whether to retry.
    """
    hint = None if not language_hint or language_hint == "auto" else language_hint
    if engine.is_remote:
        return await _transcribe_remote(
            engine,
            audio_path=audio_path,
            mime_type=mime_type,
            duration_seconds=duration_seconds,
            language_hint=hint,
            user_id=user_id,
            heartbeat=heartbeat,
        )
    return await _transcribe_local(
        audio_path=audio_path,
        duration_seconds=duration_seconds,
        language_hint=hint,
        heartbeat=heartbeat,
    )


async def transcribe_with_fallback(
    preference: MeetingSttEnginePreference,
    *,
    audio_path: Path,
    mime_type: str,
    duration_seconds: float,
    language_hint: str | None,
    user_id: UUID,
    heartbeat: Callable[[], Awaitable[None]],
) -> TranscriptionOutcome:
    """Walk the engine chain until one transcribes.

    A PERMANENT provider fault (a refused or missing key, a file the provider
    cannot take) says nothing about the next engine: the chain continues past
    that provider, within the user's preference (``remote`` never falls to the
    local engine). A transient fault is raised at once — the job's retry budget
    owns it. Measured 2026-09-03: the dev instance stores an ElevenLabs key ID
    in place of a key; without this walk every meeting dead-lettered although
    an OpenAI key was one step further down the chain.

    Raises:
        TranscriptionError: The last engine's error when every engine failed,
            or the first transient error met.
    """
    tried: set[MeetingSttProvider] = set()
    last: TranscriptionError | None = None
    while True:
        engine = resolve_engine(preference, exclude=frozenset(tried))
        if engine is None:
            if last is not None:
                raise last
            raise TranscriptionError(
                "no_engine_available", "no transcription engine is available", transient=False
            )
        try:
            return await transcribe_meeting(
                engine,
                audio_path=audio_path,
                mime_type=mime_type,
                duration_seconds=duration_seconds,
                language_hint=language_hint,
                user_id=user_id,
                heartbeat=heartbeat,
            )
        except TranscriptionError as exc:
            if exc.transient or exc.code == "no_speech":
                raise
            logger.warning(
                "meeting_engine_fallback",
                user_id=str(user_id),
                provider=engine.provider.value,
                code=exc.code,
            )
            tried.add(engine.provider)
            last = exc
