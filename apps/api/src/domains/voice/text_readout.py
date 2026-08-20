"""Read a user-visible text aloud, cost-tracked (Lot 4-A2, ADR-237).

Owns the full readout unit: tracking context, voice service lifecycle
(closed in ``finally`` — F005: the provider httpx client never leaks),
sanitation, and base64 decoding. Lives in the VOICE domain on purpose:
callers (briefing today) must not import ``chat.service`` themselves —
that edge closed a ``briefing<->chat`` runtime cycle (F009 guard) when it
lived in the briefing router.
"""

from __future__ import annotations

import base64
import uuid
from typing import Literal
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.chat.service import TrackingContext
from src.domains.voice.service import VoiceCommentService

logger = structlog.get_logger(__name__)


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
        The concatenated MP3 audio bytes.

    Raises:
        Exception: Any provider/synthesis failure — the caller maps it to
            its API error contract. The voice service is closed either way.
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
    chunks: list[bytes] = []
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
            chunks.append(base64.b64decode(chunk.audio_base64))
        if not chunks:
            # stream_direct_tts swallows per-sentence provider errors by
            # design (chat best-effort). For a readout, silence IS the
            # failure: absence of an exception is not proof of delivery —
            # and a silent run must never be committed as a paid success.
            raise RuntimeError(
                f"text readout produced no audio (run_id={run_id}, "
                f"characters={len(text)}) — check the TTS provider logs"
            )
        await tracker.commit()
    finally:
        await voice_service.close()
    logger.info(
        "text_readout_synthesized",
        run_id=run_id,
        user_id=str(user_id),
        characters=len(text),
        chunks=len(chunks),
    )
    return b"".join(chunks)
