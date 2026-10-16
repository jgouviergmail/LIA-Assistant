"""Read a user-visible text aloud, cost-tracked (Lot 4-A2, ADR-237).

Owns the full readout unit: tracking context, voice service lifecycle
(closed in ``finally`` — F005: the provider httpx client never leaks),
sanitation, base64 decoding, and ONE container: the readout answers
``audio/mpeg``, and only MP3 sentences join byte to byte — an engine configured
for raw samples returns a WAV per sentence, which joined plays its first
sentence alone (ADR-345), so those are decoded and encoded once. Lives in the
VOICE domain on purpose: callers (briefing today) must not import
``chat.service`` themselves — that edge closed a ``briefing<->chat`` runtime
cycle (F009 guard) when it lived in the briefing router.
"""

from __future__ import annotations

import base64
import uuid
from typing import Literal
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    VOICE_READOUT_MP3_BITRATE_KBPS,
    VOICE_READOUT_PCM_SAMPLE_RATE,
    VOICE_READOUT_TRANSCODE_TIMEOUT_SECONDS,
)
from src.domains.chat.service import TrackingContext
from src.domains.voice.service import VoiceCommentService
from src.infrastructure.media.ffmpeg import transcode
from src.infrastructure.media.pcm import wav_container

logger = structlog.get_logger(__name__)

#: The container a readout answers in.
_MP3_MIME = "audio/mpeg"


async def _as_one_mp3(parts: list[tuple[bytes, str]]) -> bytes:
    """The sentences as ONE MP3 file, whatever container each came back in.

    Args:
        parts: Each sentence's audio and its MIME type, in reading order.

    Returns:
        The MP3 bytes.

    Raises:
        FfmpegError: When a sentence cannot be decoded or the file encoded.
    """
    if all(mime == _MP3_MIME for _, mime in parts):
        return b"".join(audio for audio, _ in parts)
    samples = bytearray()
    for audio, _ in parts:
        samples += await transcode(
            audio,
            output_format="s16le",
            args=["-ac", "1", "-ar", str(VOICE_READOUT_PCM_SAMPLE_RATE)],
            timeout_s=VOICE_READOUT_TRANSCODE_TIMEOUT_SECONDS,
        )
    return await transcode(
        wav_container(bytes(samples), sample_rate=VOICE_READOUT_PCM_SAMPLE_RATE),
        output_format="mp3",
        args=["-codec:a", "libmp3lame", "-b:a", f"{VOICE_READOUT_MP3_BITRATE_KBPS}k"],
        timeout_s=VOICE_READOUT_TRANSCODE_TIMEOUT_SECONDS,
    )


async def synthesize_user_text(
    *,
    user_id: UUID,
    user_language: str,
    text: str,
    lia_gender: Literal["male", "female"] | None = None,
    max_sentences: int | None = None,
    run_prefix: str = "text_readout",
) -> bytes:
    """Synthesize ``text`` for the user and return the MP3 bytes (buffered).

    Args:
        user_id: Authenticated owner (drives tracking and prosody).
        user_language: Language code for voice selection.
        text: The text to read (already validated/bounded by the caller).
        lia_gender: Avatar gender preference (voice selection, as in chat).
        max_sentences: Sentence cap (None = the voice chat-mode default).
        run_prefix: Run-id prefix naming the calling surface.

    Returns:
        The MP3 audio bytes: one file, whatever the engine's container.

    Raises:
        Exception: Any provider/synthesis or encoding failure — the caller maps
            it to its API error contract. The voice service is closed either way.
    """
    from src.domains.agents.services.streaming.voice_stream_helpers import (
        _sanitize_text_for_tts,
    )

    run_id = f"{run_prefix}_{uuid.uuid4().hex[:12]}"
    tracker = TrackingContext(
        run_id=run_id,
        user_id=user_id,
        session_id=f"{run_prefix}_{user_id}",
        conversation_id=None,
    )
    voice_service = VoiceCommentService(
        tracker=tracker,
        run_id=run_id,
        lia_gender=lia_gender,
        user_id=str(user_id),
    )
    chunks: list[tuple[bytes, str]] = []
    try:
        async for chunk in voice_service.stream_direct_tts(
            text=_sanitize_text_for_tts(text),
            user_language=user_language,
            max_sentences=(
                max_sentences
                if max_sentences is not None
                else settings.voice_chat_mode_max_sentences
            ),
        ):
            chunks.append((base64.b64decode(chunk.audio_base64), chunk.mime_type))
        if not chunks:
            # stream_direct_tts swallows per-sentence provider errors by
            # design (chat best-effort). For a readout, silence IS the
            # failure: absence of an exception is not proof of delivery —
            # and a silent run must never be committed as a paid success.
            raise RuntimeError(
                f"text readout produced no audio (run_id={run_id}, "
                f"characters={len(text)}) — check the TTS provider logs"
            )
        # Committed BEFORE the encoding: the sentences were synthesised, and
        # billed, whatever happens to the file built from them.
        await tracker.commit()
        audio = await _as_one_mp3(chunks)
    finally:
        await voice_service.close()
    logger.info(
        "text_readout_synthesized",
        run_id=run_id,
        user_id=str(user_id),
        characters=len(text),
        chunks=len(chunks),
    )
    return audio
