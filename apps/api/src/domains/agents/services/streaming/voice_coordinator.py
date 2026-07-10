"""Voice/TTS coordination for the agent SSE stream (B2 extraction #1, ADR-122).

Owns the complete voice state machine that previously lived inline in
``AgentService._stream_with_new_services``:

- chat-mode progressive sentence streaming, started on the first
  ``router_decision`` with ``intention == "conversation"``;
- agent-mode parallel voice synthesis, started as soon as the tool-result
  registry becomes available during streaming;
- progressive audio emission while the text stream is still running;
- the three end-of-stream finalization paths (PATH 1 queue drain, PATH 2A
  chat-mode direct TTS, PATH 2B agent-mode Voice-LLM sync fallback);
- the two TTS cost backfill passes onto the archived assistant row;
- deterministic teardown of the voice services' persistent httpx clients.

The code was extracted verbatim (Feathers characterization-first): SSE event
order/content and structlog event names are unchanged. The golden net pinning
this contract is ``tests/agents/test_agent_service_stream_characterization.py``.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.core.config import settings
from src.core.time_utils import now_in_timezone
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.services.streaming.voice_stream_helpers import (
    ListenerProbe,
    _cleanup_chat_voice_pipeline,
    _format_voice_audio_chunk,
    _sanitize_and_truncate_for_tts,
    _sanitize_text_for_tts,
    _should_start_voice,
    _stream_voice_chunks_to_queue,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.auth.models import User
    from src.domains.chat.service import TrackingContext
    from src.domains.conversations.service import ConversationService
    from src.domains.voice.sentence_streamer import ProgressiveSentenceStreamer
    from src.domains.voice.service import VoiceCommentService

logger = get_logger(__name__)


@dataclass(slots=True)
class VoiceStreamContext:
    """Immutable per-run inputs of the voice coordination.

    Attributes:
        run_id: Run identifier (logging, chunk metadata).
        user_id: User UUID as string (VoiceCommentService attribution).
        user_language: User's language code for voice selection.
        user_timezone: User's IANA timezone (voice LLM datetime context).
        user_message: Original user message (voice LLM query context).
        lia_gender: LIA voice gender from the browser context.
        personality_instruction: Personality instruction for the voice LLM,
            or None when the user has no personality set.
        user_obj: The User row (or None) — voice_enabled preference source.
        has_listeners: Async presence probe (ADR-117 Lot 2), or None on
            paths without presence tracking.
        start_time: Stream start timestamp (elapsed-ms logging).
    """

    run_id: str
    user_id: str
    user_language: str
    user_timezone: str
    user_message: str
    lia_gender: str
    personality_instruction: str | None
    user_obj: "User | None"
    has_listeners: ListenerProbe | None
    start_time: float


class VoiceStreamCoordinator:
    """Coordinates voice/TTS synthesis alongside the agent SSE stream.

    One instance per run. The SSE generator drives it at fixed points
    (router decision, token, chunk processed, stream end, cleanup); the
    coordinator owns every piece of voice state and returns/yields the
    voice SSE chunks the generator must emit — nothing else about the
    stream is its business.
    """

    def __init__(self, context: VoiceStreamContext, tracker: "TrackingContext") -> None:
        """Initialize the coordinator with per-run context and the tracker.

        Args:
            context: Immutable per-run inputs (see VoiceStreamContext).
            tracker: The run's TrackingContext — voice services record their
                TTS cost on it; the coordinator commits after synthesis.
        """
        self._ctx = context
        self._tracker = tracker
        # Sentence streaming for chat-mode (intention=conversation): spun up
        # on the FIRST router_decision and fed token-by-token so the user
        # hears audio as soon as the first sentence is ready.
        self._chat_voice_streamer: ProgressiveSentenceStreamer | None = None
        self._chat_voice_drain_task: asyncio.Task[None] | None = None
        self._chat_voice_service: VoiceCommentService | None = None
        # Parallel voice generation (agent mode): task starts when the
        # tool-result registry becomes available during streaming.
        self._voice_service_parallel: VoiceCommentService | None = None
        self._voice_parallel_task: asyncio.Task[None] | None = None
        # Queue for PROGRESSIVE chunk emission (not wait for all).
        self._voice_chunk_queue: asyncio.Queue | None = None
        self._voice_start_emitted = False
        self._voice_complete_emitted = False
        self._voice_chunk_count = 0
        self._voice_needs_finalization = False
        self._tts_snapshot_for_done: dict[str, Any] | None = None

    @property
    def tts_snapshot_for_done(self) -> dict[str, Any] | None:
        """Per-message TTS attribution captured by the backfill passes.

        Sourced before ``cleanup_run_records()`` wipes the in-memory bucket;
        feeds the done-chunk metadata so the live frontend badge can render
        immediately without waiting for a page reload.
        """
        return self._tts_snapshot_for_done

    async def on_router_decision(self, intention: str) -> None:
        """Start the chat-mode progressive TTS pipeline when applicable.

        When the router classifies the turn as ``conversation`` (chat mode,
        no tools), the voice context registry will stay None and the legacy
        path would wait for response completion before starting TTS. Spin up
        a sentence streamer NOW so each sentence is synthesised as soon as
        it's complete in the chat LLM stream — first audio lands within ~1 s.

        Args:
            intention: The router's intention label for this turn.
        """
        if not (
            self._chat_voice_streamer is None
            and self._voice_parallel_task is None
            and intention == "conversation"
            and await _should_start_voice(
                self._ctx.user_obj, self._ctx.has_listeners, self._ctx.run_id, "chat_progressive"
            )
        ):
            return
        try:
            from src.domains.voice.service import VoiceCommentService

            self._chat_voice_service = VoiceCommentService(
                tracker=self._tracker,
                run_id=self._ctx.run_id,
                lia_gender=self._ctx.lia_gender,
                user_id=self._ctx.user_id,
            )
            if self._voice_chunk_queue is None:
                self._voice_chunk_queue = asyncio.Queue()
            (
                self._chat_voice_streamer,
                self._chat_voice_drain_task,
            ) = await self._chat_voice_service.start_progressive_chat_stream(
                user_language=self._ctx.user_language,
                chunk_queue=self._voice_chunk_queue,
            )
            logger.info(
                "chat_voice_progressive_started",
                run_id=self._ctx.run_id,
                elapsed_since_start_ms=int((time.time() - self._ctx.start_time) * 1000),
            )
        except Exception as chat_voice_err:
            logger.warning(
                "chat_voice_progressive_start_failed",
                run_id=self._ctx.run_id,
                error=str(chat_voice_err),
                error_type=type(chat_voice_err).__name__,
            )
            self._chat_voice_streamer = None
            self._chat_voice_drain_task = None

    def feed_token(self, content_fragment: str) -> None:
        """Feed a response token to the chat-mode sentence streamer.

        Sentences are extracted and TTS-dispatched as they complete. No-op
        when the chat-mode pipeline is not running.

        Args:
            content_fragment: The token's text fragment (may be empty).
        """
        if self._chat_voice_streamer is not None and content_fragment:
            self._chat_voice_streamer.feed(content_fragment)

    async def maybe_start_parallel(
        self, voice_context_registry: dict[str, Any] | None, chunk_type: str
    ) -> None:
        """Start parallel voice generation when the registry becomes available.

        The registry is populated after task_orchestrator completes tools, so
        voice generation can start before response_node finishes.

        Args:
            voice_context_registry: The streaming service's captured voice
                context registry (None until tools produce results).
            chunk_type: Type of the SSE chunk being processed (diagnostics).
        """
        # DIAGNOSTIC: Log when conditions are first met to debug first-message timing
        if self._voice_parallel_task is None and voice_context_registry is not None:
            logger.debug(
                "voice_parallel_conditions_check",
                run_id=self._ctx.run_id,
                chunk_type=chunk_type,
                has_registry=True,
                voice_enabled=(self._ctx.user_obj.voice_enabled if self._ctx.user_obj else None),
                will_start=bool(self._ctx.user_obj and self._ctx.user_obj.voice_enabled),
            )

        if (
            self._voice_parallel_task is None
            # If a chat-mode sentence streamer is already running (router said
            # ``conversation``) we must NOT spawn the agent-mode parallel
            # voice — both producers would race on ``voice_chunk_queue`` and
            # the chat audio would silently disappear when the parallel path
            # overwrites the queue reference below.
            and self._chat_voice_drain_task is None
            and voice_context_registry is not None
            and await _should_start_voice(
                self._ctx.user_obj, self._ctx.has_listeners, self._ctx.run_id, "agent_parallel"
            )
        ):
            # Import voice dependencies (lazy)
            from src.domains.agents.formatters.text_summary import (
                generate_text_summary_for_llm,
            )
            from src.domains.voice.service import VoiceCommentService

            try:
                # Build voice context from registry
                voice_context = generate_text_summary_for_llm(
                    voice_context_registry,
                    self._ctx.user_language,
                )

                # Create voice service for parallel generation
                self._voice_service_parallel = VoiceCommentService(
                    tracker=self._tracker,
                    run_id=self._ctx.run_id,
                    lia_gender=self._ctx.lia_gender,
                    user_id=self._ctx.user_id,
                )

                # Create queue for PROGRESSIVE chunk emission
                # Each audio chunk is put in queue as soon as it's ready
                self._voice_chunk_queue = asyncio.Queue()

                # Start parallel voice generation task (streams to queue)
                self._voice_parallel_task = asyncio.create_task(
                    _stream_voice_chunks_to_queue(
                        voice_service=self._voice_service_parallel,
                        context_summary=voice_context,
                        personality_instruction=self._ctx.personality_instruction or "",
                        user_language=self._ctx.user_language,
                        current_datetime=now_in_timezone(self._ctx.user_timezone).isoformat(),
                        user_query=self._ctx.user_message,
                        chunk_queue=self._voice_chunk_queue,
                        user_timezone=self._ctx.user_timezone,
                    )
                )

                logger.info(
                    "voice_parallel_task_started",
                    run_id=self._ctx.run_id,
                    voice_context_length=(len(voice_context) if voice_context else 0),
                    registry_items_count=len(voice_context_registry),
                    elapsed_since_start_ms=int((time.time() - self._ctx.start_time) * 1000),
                    mode="progressive_queue",
                )

            except Exception as parallel_start_error:
                # Non-fatal: Log and continue, will fallback to sync
                logger.warning(
                    "voice_parallel_task_start_failed",
                    run_id=self._ctx.run_id,
                    error=str(parallel_start_error),
                    error_type=type(parallel_start_error).__name__,
                )
                # voice_parallel_task stays None, fallback to sync later

    def drain_progressive_nowait(self) -> list[ChatStreamChunk]:
        """Drain available audio chunks for progressive mid-stream emission.

        Non-blocking (``get_nowait``): called after each SSE chunk is yielded
        so audio is emitted PROGRESSIVELY during streaming. On the queue's
        ``None`` sentinel, emits ``voice_complete`` (only if audio started).

        Returns:
            The voice SSE chunks to yield, in emission order (possibly empty).
        """
        chunks: list[ChatStreamChunk] = []
        if self._voice_chunk_queue is None or self._voice_complete_emitted:
            return chunks
        try:
            # Drain all available chunks from queue (non-blocking)
            while True:
                try:
                    audio_chunk = self._voice_chunk_queue.get_nowait()

                    # None is sentinel = generation complete
                    if audio_chunk is None:
                        # Emit voice_complete only if we started
                        if self._voice_start_emitted:
                            chunks.append(
                                ChatStreamChunk(
                                    type="voice_complete",
                                    content="",
                                    metadata={
                                        "run_id": self._ctx.run_id,
                                        "chunk_count": self._voice_chunk_count,
                                        "source": "parallel_progressive",
                                    },
                                )
                            )
                            self._voice_complete_emitted = True
                            logger.info(
                                "voice_progressive_complete",
                                run_id=self._ctx.run_id,
                                chunk_count=self._voice_chunk_count,
                            )
                        break

                    # First chunk: emit voice_comment_start
                    if not self._voice_start_emitted:
                        chunks.append(
                            ChatStreamChunk(
                                type="voice_comment_start",
                                content="",
                                metadata={"run_id": self._ctx.run_id},
                            )
                        )
                        self._voice_start_emitted = True
                        logger.info(
                            "voice_progressive_started",
                            run_id=self._ctx.run_id,
                            elapsed_since_start_ms=int((time.time() - self._ctx.start_time) * 1000),
                        )

                    # Emit audio chunk (DRY: use helper)
                    chunks.append(_format_voice_audio_chunk(audio_chunk))
                    self._voice_chunk_count += 1

                    logger.debug(
                        "voice_progressive_chunk_emitted",
                        run_id=self._ctx.run_id,
                        phrase_index=audio_chunk.phrase_index,
                        is_last=audio_chunk.is_last,
                    )

                except asyncio.QueueEmpty:
                    # No more chunks available right now
                    break

        except Exception as progressive_emit_error:
            # Non-fatal: will fallback to end-of-stream emission
            logger.warning(
                "voice_progressive_emission_failed",
                run_id=self._ctx.run_id,
                error=str(progressive_emit_error),
                error_type=type(progressive_emit_error).__name__,
            )
        return chunks

    def close_input(self) -> None:
        """Signal end-of-input to the chat-mode sentence streamer.

        Flushes its trailing buffer (last sentence — likely without a
        punctuation terminator) so the drain task can finalise once every
        TTS call resolves. No-op when the pipeline is not running.
        """
        if self._chat_voice_streamer is not None:
            try:
                self._chat_voice_streamer.close_input()
            except Exception as close_err:  # noqa: BLE001 — non-fatal
                logger.warning(
                    "chat_voice_streamer_close_failed",
                    run_id=self._ctx.run_id,
                    error=str(close_err),
                )

    async def finalize(
        self,
        *,
        response_content: str,
        hitl_interrupted: bool,
        voice_context_registry: dict[str, Any] | None,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """Emit remaining voice chunks or run the sync fallback (end of stream).

        Priority: 1) Progressive emission during streaming (may be complete)
                  2) PATH 1 — drain remaining queue chunks at end of stream
                  3) PATH 2 — sync fallback if no parallel task
                     (2A direct TTS in chat mode, 2B Voice-LLM in agent mode)
        Skipped entirely when voice already completed during streaming, on a
        HITL interrupt, on an empty response, or when nobody is listening.

        Args:
            response_content: The accumulated assistant response text.
            hitl_interrupted: True when this turn raised a HITL interrupt.
            voice_context_registry: The streaming service's registry at end
                of stream (None in pure chat mode).

        Yields:
            The voice SSE chunks to emit, in order.
        """
        self._voice_needs_finalization = (
            bool(response_content.strip())
            and not hitl_interrupted
            and not self._voice_complete_emitted  # Skip if already completed during streaming
            # Listener gating last (may hit Redis) — cheap checks first
            and await _should_start_voice(
                self._ctx.user_obj, self._ctx.has_listeners, self._ctx.run_id, "sync_fallback"
            )
        )

        # DIAGNOSTIC: Track parallel task state at end of streaming
        parallel_task_done = (
            self._voice_parallel_task.done() if self._voice_parallel_task is not None else None
        )
        logger.debug(
            "voice_feature_check",
            run_id=self._ctx.run_id,
            voice_needs_finalization=self._voice_needs_finalization,
            has_parallel_task=self._voice_parallel_task is not None,
            parallel_task_done=parallel_task_done,
            voice_start_emitted=self._voice_start_emitted,
            voice_complete_emitted=self._voice_complete_emitted,
            voice_chunk_count=self._voice_chunk_count,
            response_content_length=len(response_content) if response_content else 0,
        )

        # DIAGNOSTIC: Log if progressive emission started but not completed
        if self._voice_start_emitted and not self._voice_complete_emitted:
            logger.info(
                "voice_progressive_incomplete_will_drain",
                run_id=self._ctx.run_id,
                reason="Progressive emission started but not all chunks emitted",
                chunks_emitted_so_far=self._voice_chunk_count,
                parallel_task_done=parallel_task_done,
            )

        if not self._voice_needs_finalization:
            return

        try:
            from src.domains.agents.formatters.text_summary import (
                generate_text_summary_for_llm,
            )
            from src.domains.voice.service import VoiceCommentService

            chunk_count = self._voice_chunk_count  # Continue from progressive count
            voice_source = "unknown"

            # === PATH 1: Drain remaining chunks from queue ===
            # Two queue producers can populate voice_chunk_queue:
            # - voice_parallel_task (agent mode, registry-driven)
            # - chat_voice_drain_task (chat mode, sentence streamer)
            # Both push the same VoiceAudioChunk shape and end with
            # a None sentinel — the drain loop is identical.
            active_voice_task = self._voice_parallel_task or self._chat_voice_drain_task
            if self._voice_chunk_queue is not None and active_voice_task is not None:
                try:
                    # Wait for the producer task with configurable timeout
                    # This ensures all chunks are in the queue
                    await asyncio.wait_for(
                        active_voice_task,
                        timeout=settings.voice_parallel_timeout_seconds,
                    )
                    voice_source = (
                        "parallel_drain"
                        if self._voice_parallel_task is not None
                        else "chat_progressive_drain"
                    )

                    # Drain remaining chunks from queue
                    while True:
                        try:
                            audio_chunk = self._voice_chunk_queue.get_nowait()

                            # None is sentinel = generation complete
                            if audio_chunk is None:
                                break

                            # First chunk: emit voice_comment_start if not yet emitted
                            if not self._voice_start_emitted:
                                yield ChatStreamChunk(
                                    type="voice_comment_start",
                                    content="",
                                    metadata={"run_id": self._ctx.run_id},
                                )
                                self._voice_start_emitted = True

                            # Emit audio chunk (DRY: use helper)
                            yield _format_voice_audio_chunk(audio_chunk)
                            chunk_count += 1

                        except asyncio.QueueEmpty:
                            break

                    logger.info(
                        "voice_queue_drained_at_end",
                        run_id=self._ctx.run_id,
                        total_chunk_count=chunk_count,
                        progressive_count=self._voice_chunk_count,
                        drained_count=chunk_count - self._voice_chunk_count,
                    )

                    # Commit TTS tokens tracked during voice generation
                    # TrackingContext already exited, but tracker instance persists
                    # TTS records were added to _node_records by _track_tts_cost()
                    # This incremental commit persists them to DB via UPSERT
                    await self._tracker.commit()

                except TimeoutError:
                    logger.warning(
                        "voice_parallel_task_timeout",
                        run_id=self._ctx.run_id,
                        timeout_seconds=settings.voice_parallel_timeout_seconds,
                    )
                    # Cancel and await for proper cleanup (asyncio best practice)
                    active_voice_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await active_voice_task
                    # Fall through to sync generation
                    # (voice_chunk_queue needs no reset: never read again on this path)
                    self._voice_parallel_task = None
                    self._chat_voice_drain_task = None

                except Exception as parallel_error:
                    logger.warning(
                        "voice_parallel_task_failed",
                        run_id=self._ctx.run_id,
                        error=str(parallel_error),
                        error_type=type(parallel_error).__name__,
                    )
                    # Fall through to sync generation
                    # (voice_chunk_queue needs no reset: never read again on this path)
                    self._voice_parallel_task = None
                    self._chat_voice_drain_task = None

            # === PATH 2: Sync fallback (chat mode or parallel failed) ===
            # Skip if a chat-mode progressive streamer already synthesised the
            # audio (its drain task above is the producer,
            # voice_complete_emitted will be True).
            if (
                self._voice_parallel_task is None
                and self._chat_voice_drain_task is None
                and chunk_count == 0
            ):
                # Emit voice_comment_start for sync path
                yield ChatStreamChunk(
                    type="voice_comment_start",
                    content="",
                    metadata={"run_id": self._ctx.run_id},
                )
                self._voice_start_emitted = True

                # Determine voice generation mode
                is_chat_mode = voice_context_registry is None

                # === PATH 2A: Chat mode - Direct TTS (skip Voice LLM) ===
                # When there's no registry (pure chat), TTS the response directly
                # This is faster and more natural for conversational responses
                if is_chat_mode:
                    voice_source = "direct_tts_chat_mode"

                    logger.info(
                        "voice_direct_tts_chat_mode",
                        run_id=self._ctx.run_id,
                        response_length=len(response_content),
                        max_sentences=settings.voice_chat_mode_max_sentences,
                    )

                    # Create voice service for direct TTS
                    voice_service = VoiceCommentService(
                        tracker=self._tracker,
                        run_id=self._ctx.run_id,
                        lia_gender=self._ctx.lia_gender,
                        user_id=self._ctx.user_id,
                    )

                    # Direct TTS: skip voice LLM, synthesize response directly
                    async for audio_chunk in voice_service.stream_direct_tts(
                        text=_sanitize_text_for_tts(response_content),
                        user_language=self._ctx.user_language,
                        max_sentences=settings.voice_chat_mode_max_sentences,
                    ):
                        chunk_count += 1
                        yield _format_voice_audio_chunk(audio_chunk)

                    # Commit TTS tokens (context already exited)
                    await self._tracker.commit()

                # === PATH 2B: Agent mode - Voice LLM + TTS ===
                # When there's a registry (tools were used), generate commentary
                else:
                    voice_source = "sync_fallback"

                    # Build voice context from registry or response
                    if voice_context_registry:
                        try:
                            voice_context = generate_text_summary_for_llm(
                                voice_context_registry, self._ctx.user_language
                            )
                        except Exception as summary_error:
                            logger.warning(
                                "voice_context_summary_failed",
                                run_id=self._ctx.run_id,
                                error=str(summary_error),
                            )
                            voice_context = _sanitize_and_truncate_for_tts(
                                response_content, settings.voice_context_max_chars
                            )
                    else:
                        # Fallback: use response content (chat mode with direct_tts disabled)
                        voice_context = _sanitize_and_truncate_for_tts(
                            response_content, settings.voice_context_max_chars
                        )

                    logger.info(
                        "voice_sync_fallback_generating",
                        run_id=self._ctx.run_id,
                        voice_context_length=len(voice_context) if voice_context else 0,
                        has_registry=voice_context_registry is not None,
                    )

                    # Create voice service for sync generation
                    voice_service = VoiceCommentService(
                        tracker=self._tracker,
                        run_id=self._ctx.run_id,
                        lia_gender=self._ctx.lia_gender,
                        user_id=self._ctx.user_id,
                    )
                    current_dt = now_in_timezone(self._ctx.user_timezone).isoformat()

                    async for audio_chunk in voice_service.stream_voice_comment(
                        context_summary=voice_context
                        or _sanitize_and_truncate_for_tts(
                            response_content, settings.voice_context_max_chars
                        ),
                        personality_instruction=self._ctx.personality_instruction or "",
                        user_language=self._ctx.user_language,
                        current_datetime=current_dt,
                        user_query=self._ctx.user_message,
                        user_timezone=self._ctx.user_timezone,
                    ):
                        chunk_count += 1
                        # DRY: use helper for audio chunk formatting
                        yield _format_voice_audio_chunk(audio_chunk)

                    # Commit TTS tokens (context already exited)
                    await self._tracker.commit()

            # Signal voice complete (only if we emitted voice_start)
            if self._voice_start_emitted and not self._voice_complete_emitted:
                yield ChatStreamChunk(
                    type="voice_complete",
                    content="",
                    metadata={
                        "run_id": self._ctx.run_id,
                        "chunk_count": chunk_count,
                        "source": voice_source,
                    },
                )
                self._voice_complete_emitted = True

                logger.info(
                    "voice_comment_completed",
                    run_id=self._ctx.run_id,
                    chunk_count=chunk_count,
                    source=voice_source,
                )

        except Exception as voice_error:
            logger.error(
                "voice_comment_failed",
                run_id=self._ctx.run_id,
                error=str(voice_error),
                error_type=type(voice_error).__name__,
            )
            yield ChatStreamChunk(
                type="voice_error",
                content="voice_synthesis_error",
                metadata={"error_type": "voice_error"},
            )

    async def backfill_tts_pass1(
        self,
        temp_tracker: "TrackingContext",
        conv_service: "ConversationService",
        archived_assistant_msg_id: uuid.UUID | None,
    ) -> None:
        """Backfill the assistant row with TTS attribution (first pass).

        Covers the parallel-progressive path where voice synthesis happens
        during streaming. MUST run before ``cleanup_run_records()`` — the
        cleanup wipes the module-level ``_run_tts_records`` bucket and the
        second aggregated summary in the done chunk would then read tts=0
        from in-memory. The captured snapshot survives the cleanup and feeds
        the done-chunk metadata.

        Args:
            temp_tracker: Post-run tracker used to read the TTS records.
            conv_service: Conversation service performing the row UPDATE.
            archived_assistant_msg_id: The archived assistant row id, or None
                (nothing to backfill).
        """
        if archived_assistant_msg_id is None:
            return
        await self._run_tts_backfill(
            temp_tracker, conv_service, archived_assistant_msg_id, extra_log_fields={}
        )

    async def backfill_tts_pass2(
        self,
        temp_tracker: "TrackingContext",
        conv_service: "ConversationService",
        archived_assistant_msg_id: uuid.UUID | None,
    ) -> None:
        """Backfill the assistant row with TTS attribution (sync-fallback pass).

        The sync fallback (PATH 2A direct_tts / PATH 2B voice_comment) runs
        only inside ``finalize()`` — i.e. AFTER the first backfill and AFTER
        ``cleanup_run_records()``. The voice service's ``tracker.commit()``
        re-populates ``_run_tts_records`` for this run_id, so this second
        pass picks them up. Skipped when finalization did not run or when
        the first pass already captured a snapshot.

        Args:
            temp_tracker: Post-run tracker used to read the TTS records.
            conv_service: Conversation service performing the row UPDATE.
            archived_assistant_msg_id: The archived assistant row id, or None.
        """
        if not (
            self._voice_needs_finalization
            and archived_assistant_msg_id is not None
            and self._tts_snapshot_for_done is None  # only if first pass found nothing
        ):
            return
        await self._run_tts_backfill(
            temp_tracker,
            conv_service,
            archived_assistant_msg_id,
            extra_log_fields={"pass_": "sync_fallback"},
        )

    async def _run_tts_backfill(
        self,
        temp_tracker: "TrackingContext",
        conv_service: "ConversationService",
        message_id: uuid.UUID,
        extra_log_fields: dict[str, Any],
    ) -> None:
        """Read TTS usage from the tracker and persist it onto the message row.

        Best-effort: a backfill failure is logged and never breaks the stream.

        Args:
            temp_tracker: Post-run tracker used to read the TTS records.
            conv_service: Conversation service performing the row UPDATE.
            message_id: The archived assistant row id.
            extra_log_fields: Extra structlog fields distinguishing the pass
                ({} for pass 1, {"pass_": "sync_fallback"} for pass 2).
        """
        from src.infrastructure.database import get_db_context

        try:
            tts_usage = temp_tracker.get_tts_usage_for_archive()
            if tts_usage:
                self._tts_snapshot_for_done = dict(tts_usage)
                async with get_db_context() as tts_db:
                    await conv_service.update_message_tts(
                        message_id,
                        tts_usage,
                        tts_db,
                    )
                    await tts_db.commit()
                logger.debug(
                    "tts_backfill_done",
                    run_id=self._ctx.run_id,
                    message_id=str(message_id),
                    tts_provider=tts_usage.get("tts_provider"),
                    tts_characters=tts_usage.get("tts_characters"),
                    **extra_log_fields,
                )
        except Exception as tts_archive_err:
            logger.warning(
                "tts_backfill_failed",
                run_id=self._ctx.run_id,
                message_id=str(message_id),
                error=str(tts_archive_err),
                error_type=type(tts_archive_err).__name__,
                **extra_log_fields,
            )

    async def cleanup_chat_pipeline(self) -> None:
        """Tear down the chat-mode voice pipeline only (GraphInterrupt path).

        The GraphInterrupt fallback exits the generator before the normal
        cleanup: without this, the LLM feeder + in-flight TTS tasks would
        leak when the generator returns (the tracker context exit does not
        propagate to background tasks). The parallel-mode service is NOT
        closed here — exactly the pre-extraction behavior.
        """
        await _cleanup_chat_voice_pipeline(
            self._chat_voice_streamer,
            self._chat_voice_drain_task,
            self._ctx.run_id,
            self._chat_voice_service,
        )

    async def cleanup(self, *, log_close_failure: bool = True) -> None:
        """Tear down every voice resource owned by this run.

        Voice services own a persistent httpx client (TTS) that must be
        closed deterministically — without this, the keep-alive pool leaks
        until process restart. Idempotent: if voice was never invoked the
        helpers are no-ops.

        Args:
            log_close_failure: True (nominal path) logs a warning when the
                parallel service close fails; False (generator except path)
                lets the exception propagate so the caller's
                ``contextlib.suppress`` keeps the exact pre-extraction
                semantics (remaining cleanup steps are then skipped).
        """
        await self.cleanup_chat_pipeline()
        # Parallel-mode (agent) voice service is closed via the task that
        # owns it — but we close defensively here too in case the task
        # already finished with an exception that bypassed the local cleanup.
        if self._voice_service_parallel is not None:
            if log_close_failure:
                try:
                    await self._voice_service_parallel.close()
                except Exception as voice_close_err:  # noqa: BLE001
                    logger.warning(
                        "voice_service_parallel_close_failed",
                        run_id=self._ctx.run_id,
                        error=str(voice_close_err),
                    )
            else:
                await self._voice_service_parallel.close()
