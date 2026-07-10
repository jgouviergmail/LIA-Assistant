"""Stateless voice/TTS primitives for the agent SSE stream (ADR-122).

Companion module of :mod:`voice_coordinator`: everything here is a pure
function (or a self-contained pipeline helper) with no coordinator state —
TTS text sanitization, the voice-start gate, SSE audio-chunk formatting,
the parallel queue pump and the chat-pipeline teardown. The stateful voice
machine lives in :class:`~.voice_coordinator.VoiceStreamCoordinator`.

Extracted verbatim from ``api/service.py`` (B2 extraction #1) — behavior and
structlog event names are unchanged; the golden net is
``tests/agents/test_agent_service_stream_characterization.py``.
"""

import asyncio
import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from src.domains.agents.api.schemas import ChatStreamChunk
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.auth.models import User
    from src.domains.voice.sentence_streamer import ProgressiveSentenceStreamer
    from src.domains.voice.service import VoiceCommentService

logger = get_logger(__name__)

# ADR-117 Lot 2: async probe answering "is anyone subscribed to this run's
# stream right now?" — injected by the detached-producer path so voice
# synthesis (a pure per-character cost) is skipped with no listeners.
ListenerProbe = Callable[[], Awaitable[bool]]


# Recognised HTML element tags emitted by the response/display layer. Used to
# detect *real* markup before stripping it for TTS, so plain prose with bare
# angle brackets ("x < 5 and y > 3") or Markdown symbols is left untouched.
_HTML_TAG_RE = re.compile(
    r"</?(?:div|p|span|style|script|h[1-6]|ul|ol|li|table|thead|tbody|tr|td|th"
    r"|br|hr|a|strong|em|b|i|blockquote|code|pre|img)\b",
    re.IGNORECASE,
)


def _looks_like_html(text: str) -> bool:
    """Cheaply detect genuine HTML markup (not a bare '<' in prose or code).

    Guards :func:`_sanitize_text_for_tts` so plain text such as
    ``"x < 5 and y > 3"`` is never run through ``html_to_text`` — whose final
    ``re.sub(r"<[^>]+>", "", text)`` would otherwise delete ``"< 5 and y >"``.
    Only recognised HTML element tags trigger stripping; the LLM's
    ``lia-response`` wrapper is detected via its own ``<div>`` / ``<style>``
    tags, so no separate (false-positive-prone) substring check is needed.
    """
    if not text:
        return False
    return bool(_HTML_TAG_RE.search(text))


def _sanitize_text_for_tts(text: str) -> str:
    """Strip HTML to speakable plain text, but only when markup is present.

    Defense-in-depth safety net for every path that may feed the TTS engine
    the raw assistant response (reference turns, post-LLM data cards, sync
    voice fallbacks). A no-op on Markdown / plain prose, so it is safe to apply
    unconditionally at TTS entry points without mangling normal replies.
    """
    if not text or not _looks_like_html(text):
        return text
    from src.domains.agents.display.components.base import html_to_text

    return html_to_text(text, preserve_links=False)


def _sanitize_and_truncate_for_tts(text: str, max_chars: int) -> str:
    """Strip HTML (when present) then clamp to the voice-context char budget.

    Thin convenience wrapper over :func:`_sanitize_text_for_tts` for the voice
    fallback paths that feed a length-capped context to the voice LLM.
    """
    return _sanitize_text_for_tts(text)[:max_chars]


def _format_voice_audio_chunk(audio_chunk: Any) -> ChatStreamChunk:
    """Format a voice audio chunk for SSE emission (DRY helper).

    Centralizes the ChatStreamChunk creation for voice audio to avoid
    code duplication across progressive emission, drain, and sync paths.

    Args:
        audio_chunk: VoiceAudioChunk object from VoiceCommentService

    Returns:
        ChatStreamChunk ready for SSE emission
    """
    return ChatStreamChunk(
        type="voice_audio_chunk",
        content=audio_chunk.model_dump(),
        metadata={
            "phrase_index": audio_chunk.phrase_index,
            "is_last": audio_chunk.is_last,
        },
    )


async def _should_start_voice(
    user_obj: "User | None",
    has_listeners: ListenerProbe | None,
    run_id: str,
    voice_path: str,
) -> bool:
    """Gate every voice-synthesis start point (ADR-117 Lot 2).

    Voice synthesis is a pure per-character cost: when the run executes
    detached and nobody is subscribed to its stream, synthesizing audio
    is waste. The probe is None on paths without presence tracking
    (legacy inline SSE, scheduled actions, channels) — behavior is then
    unchanged.

    Args:
        user_obj: The User (or None) — voice_enabled preference source.
        has_listeners: Async presence probe, or None (no gating).
        run_id: Run identifier (logging).
        voice_path: Which start point is asking (logging):
            "chat_progressive" | "agent_parallel" | "sync_fallback".

    Returns:
        True when voice synthesis should start.
    """
    if user_obj is None or not user_obj.voice_enabled:
        return False
    if has_listeners is None:
        return True
    try:
        listening = await has_listeners()
    except Exception as probe_err:  # noqa: BLE001 — fail-open on Redis hiccup
        logger.warning(
            "voice_listener_probe_failed",
            run_id=run_id,
            voice_path=voice_path,
            error=str(probe_err),
        )
        return True
    if not listening:
        logger.info(
            "voice_skipped_no_listeners",
            run_id=run_id,
            voice_path=voice_path,
        )
    return listening


async def _stream_voice_chunks_to_queue(
    voice_service: Any,
    context_summary: str,
    personality_instruction: str,
    user_language: str,
    current_datetime: str,
    user_query: str,
    chunk_queue: asyncio.Queue,
    user_timezone: str | None = None,
) -> None:
    """Stream voice audio chunks to a queue for progressive emission.

    Used for parallel voice generation: puts chunks into queue as they're
    generated (one per sentence), allowing early emission during text streaming.

    Args:
        voice_service: VoiceCommentService instance
        context_summary: Rich context from registry (generate_text_summary_for_llm)
        personality_instruction: Personality instruction for voice LLM
        user_language: User's language code (fr, en, etc.)
        current_datetime: ISO datetime string (in the user's timezone)
        user_query: Original user message
        chunk_queue: asyncio.Queue to put chunks into for progressive emission
        user_timezone: User's IANA timezone (defense in depth: lets the
            voice service resolve a correct fallback datetime)

    Note:
        Puts None as sentinel value when generation is complete.
    """
    try:
        async for audio_chunk in voice_service.stream_voice_comment(
            context_summary=context_summary,
            personality_instruction=personality_instruction,
            user_language=user_language,
            current_datetime=current_datetime,
            user_query=user_query,
            user_timezone=user_timezone,
        ):
            await chunk_queue.put(audio_chunk)
    finally:
        # Sentinel to signal completion
        await chunk_queue.put(None)


async def _cleanup_chat_voice_pipeline(
    streamer: "ProgressiveSentenceStreamer | None",
    drain_task: "asyncio.Task[None] | None",
    run_id: str,
    service: "VoiceCommentService | None" = None,
) -> None:
    """Tear down the chat-mode sentence streaming pipeline.

    Called from every code path that exits the SSE generator before the
    normal cleanup ran (HITL interrupt fallback, GraphInterrupt at the
    outer except, exception in the streaming loop) AND from the success
    path so the persistent httpx pool inside the ElevenLabs TTS client
    is released deterministically.

    Steps (each best-effort, never re-raises):
        1. Cancel any in-flight TTS task via ``streamer.cancel_pending``.
        2. Cancel and await the drain task — without this, the
           ``_drain()`` coroutine keeps consuming the streamer queue
           forever and holds a TCP connection to the TTS provider.
        3. Close the underlying ``VoiceCommentService`` so its
           persistent httpx client is properly aclosed (otherwise we
           leak the keep-alive connection pool until process restart).

    Idempotent and tolerant to already-completed/None values.
    """
    if streamer is None and drain_task is None and service is None:
        return
    try:
        if streamer is not None:
            streamer.cancel_pending()
        if drain_task is not None and not drain_task.done():
            drain_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await drain_task
        if service is not None:
            try:
                await service.close()
            except Exception as close_err:  # noqa: BLE001
                logger.warning(
                    "chat_voice_service_close_failed",
                    run_id=run_id,
                    error=str(close_err),
                )
    except Exception as cleanup_err:  # noqa: BLE001 — non-fatal cleanup
        logger.warning(
            "chat_voice_pipeline_cleanup_failed",
            run_id=run_id,
            error=str(cleanup_err),
            error_type=type(cleanup_err).__name__,
        )
