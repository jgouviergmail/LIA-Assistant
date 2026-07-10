"""
Agents domain service.
Orchestrates graph execution, streaming, and session management.

Phase 3.3: Service-oriented architecture with dependency injection.
Uses autonomous services: OrchestrationService, StreamingService,
ConversationOrchestrator.
"""

import asyncio
import re
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from langgraph.errors import GraphInterrupt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    USAGE_LIMIT_EXCEEDED_ERROR_CODE,
)
from src.core.field_names import FIELD_ERROR_TYPE, FIELD_RUN_ID
from src.core.time_utils import now_in_timezone
from src.domains.agents.api.mixins import GraphManagementMixin, StreamingMixin
from src.domains.agents.api.schemas import BrowserContext, ChatStreamChunk
from src.domains.agents.dependencies import ToolDependencies
from src.domains.agents.utils import generate_run_id
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.conversations.service import ConversationService
    from src.domains.voice.sentence_streamer import ProgressiveSentenceStreamer
    from src.domains.voice.service import VoiceCommentService

logger = get_logger(__name__)

# MAX_HITL_ACTIONS_PER_REQUEST defined in src.core.constants
# Phase 3.3: Centralized constant management

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


class AgentService(
    GraphManagementMixin,
    StreamingMixin,
):
    """
    Service for managing LangGraph agent executions.
    Handles graph building, streaming responses, and session management.

    Composed with mixins for:
    - GraphManagementMixin: Graph lifecycle and lazy initialization
    - StreamingMixin: SSE streaming and event conversion
    - TokenTrackingMixin: Token aggregation and metadata enrichment
    """

    def __init__(self) -> None:
        """Initialize service (lazy graph build via GraphManagementMixin)."""
        super().__init__()
        logger.info("agent_service_initialized")

    async def _get_user_oauth_scopes(self, user_id: uuid.UUID, db: AsyncSession) -> list[str]:
        """
        Fetch OAuth scopes from user's active connectors.

        Retrieves all scopes from connectors where:
        - user_id matches
        - is_active = True
        - Flattens and deduplicates scopes from all connectors

        Args:
            user_id: User UUID.
            db: Database session.

        Returns:
            List of unique OAuth scopes (e.g., ["https://www.googleapis.com/auth/contacts.readonly"]).
            Returns empty list if no active connectors or no scopes granted.

        Example:
            >>> scopes = await service._get_user_oauth_scopes(user_id, db)
            >>> print(scopes)
            ['https://www.googleapis.com/auth/contacts.readonly', 'https://www.googleapis.com/auth/userinfo.email']
        """
        from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

        from src.core.exceptions import DatabasePoolExhaustedError
        from src.domains.connectors.models import Connector

        try:
            # Import ConnectorStatus enum
            from src.domains.connectors.models import ConnectorStatus

            # Query active connectors for user
            stmt = select(Connector).where(
                Connector.user_id == user_id,
                Connector.status == ConnectorStatus.ACTIVE,
            )
            result = await db.execute(stmt)
            connectors = result.scalars().all()

            # Flatten and deduplicate scopes from all connectors
            all_scopes = set()
            for connector in connectors:
                if connector.scopes:  # scopes is JSONB list[str]
                    all_scopes.update(connector.scopes)

            scopes_list = sorted(all_scopes)  # Sort for determinism

            logger.debug(
                "oauth_scopes_fetched",
                user_id=str(user_id),
                connector_count=len(connectors),
                scope_count=len(scopes_list),
                scopes=scopes_list,
            )

            return scopes_list

        except SQLAlchemyTimeoutError as e:
            # CRITICAL: Do NOT fail-silent on pool exhaustion!
            # Returning [] would cause fake "missing scopes" errors and retry loops.
            # Instead, propagate the error with a clear message.
            logger.error(
                "oauth_scopes_fetch_pool_exhausted",
                user_id=str(user_id),
                error=str(e),
            )
            raise DatabasePoolExhaustedError(
                operation="oauth_scopes_fetch",
                user_id=str(user_id),
            ) from e

        except Exception as e:
            # For non-pool errors, log and re-raise (don't silently return [])
            logger.error(
                "oauth_scopes_fetch_failed",
                user_id=str(user_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    @staticmethod
    async def _interleave_side_channel(
        sse_stream: AsyncGenerator[tuple[Any, str], None],
        side_queue: asyncio.Queue,
        poll_interval: float = 0.3,
    ) -> AsyncGenerator[tuple[Any, str], None]:
        """Interleave SSE stream with side-channel queue polling.

        Ensures side-channel items (progressive screenshots, etc.) are yielded
        promptly even when the graph is blocked in a long node execution
        (e.g., ReAct browser loop). Polls the queue every poll_interval seconds.

        Args:
            sse_stream: The main SSE chunk stream from StreamingService.
            side_queue: Side-channel asyncio.Queue populated by tools.
            poll_interval: Seconds between queue polls when graph is idle.

        Yields:
            (chunk, content_fragment) tuples — either from the SSE stream
            or (side_chunk, "") for side-channel items.
        """
        sse_aiter = sse_stream.__aiter__()
        pending: asyncio.Task | None = None

        try:
            while True:
                # Start fetching next SSE chunk if not already pending
                if pending is None:
                    pending = asyncio.ensure_future(sse_aiter.__anext__())

                # Wait for SSE chunk OR timeout (to drain side-channel)
                done, _ = await asyncio.wait({pending}, timeout=poll_interval)

                # Drain any pending side-channel items
                while not side_queue.empty():
                    try:
                        yield side_queue.get_nowait(), ""
                    except asyncio.QueueEmpty:
                        break

                # If SSE chunk arrived, yield it
                if done:
                    try:
                        result = pending.result()
                        pending = None
                        yield result
                    except StopAsyncIteration:
                        break
                # Otherwise: timeout — loop back and poll again
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
            # Note: no yield in finally — avoids RuntimeError if exception propagating.
            # Final drain is done below (only reached on normal exit, not on exception).

        # Final drain after clean stream completion (unreachable on exception)
        while not side_queue.empty():
            try:
                yield side_queue.get_nowait(), ""
            except asyncio.QueueEmpty:
                break

    async def _stream_voice_chunks_to_queue(
        self,
        voice_service: Any,
        context_summary: str,
        personality_instruction: str,
        user_language: str,
        current_datetime: str,
        user_query: str,
        chunk_queue: asyncio.Queue,
        user_timezone: str | None = None,
    ) -> None:
        """
        Stream voice audio chunks to a queue for progressive emission.

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

    @staticmethod
    async def _cleanup_chat_voice_pipeline(
        streamer: "ProgressiveSentenceStreamer | None",
        drain_task: asyncio.Task[None] | None,
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

    @staticmethod
    def _format_voice_audio_chunk(audio_chunk: Any) -> "ChatStreamChunk":
        """
        Format a voice audio chunk for SSE emission (DRY helper).

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

    @staticmethod
    def _get_agents_bucket_label(agents_count: int) -> str:
        """
        Bucket agents_count into discrete labels for cardinality control.

        Prevents label explosion by grouping agent counts into buckets.
        This keeps the metric's cardinality manageable for Prometheus.

        Args:
            agents_count: Number of agents called in the execution.

        Returns:
            Bucket label: "0", "1", "2", "3", "4-5", "6+"
        """
        if agents_count == 0:
            return "0"
        elif agents_count == 1:
            return "1"
        elif agents_count == 2:
            return "2"
        elif agents_count == 3:
            return "3"
        elif agents_count <= 5:
            return "4-5"
        else:
            return "6+"

    async def _warmup_contacts_cache_if_active(
        self,
        user_id: uuid.UUID,
        tool_deps: "ToolDependencies",
    ) -> None:
        """
        Warmup contacts cache if a contacts provider is active (Google or Apple).

        This prevents the "first search returns 0 results" issue by preloading
        the contacts list into Redis cache.

        Args:
            user_id: User UUID
            tool_deps: ToolDependencies with shared DB session

        Note:
            - Runs asynchronously, non-blocking
            - Fails silently if connector not active or on error
            - Caches first 100 contacts with 5-minute TTL
        """
        try:
            # Import here to avoid circular dependency
            from src.core.config import get_settings
            from src.domains.connectors.clients.registry import ClientRegistry
            from src.domains.connectors.provider_resolver import resolve_active_connector

            settings = get_settings()

            # Dynamically resolve the active contacts provider (Google or Apple)
            connector_service = await tool_deps.get_connector_service()
            resolved_type = await resolve_active_connector(user_id, "contacts", connector_service)

            if resolved_type is None:
                # No contacts connector active, skip warmup
                return

            # Get credentials based on provider type
            if resolved_type.is_apple:
                credentials = await connector_service.get_apple_credentials(user_id, resolved_type)
            else:
                credentials = await connector_service.get_connector_credentials(
                    user_id, resolved_type
                )

            if not credentials:
                return

            # Create appropriate client via registry
            client_class = ClientRegistry.get_client_class(resolved_type)
            if client_class is None:
                return
            client = client_class(user_id, credentials, connector_service)

            # Use global security limit for warmup
            warmup_limit = settings.api_max_items_per_request

            logger.info(
                "contacts_cache_warmup_starting",
                user_id=str(user_id),
                provider=resolved_type.value,
                warmup_limit=warmup_limit,
            )

            # Preload contacts into cache with security limit
            await client.list_connections(
                page_size=warmup_limit,
                use_cache=True,  # Cache the results
            )

            logger.info(
                "contacts_cache_warmup_completed",
                user_id=str(user_id),
                provider=resolved_type.value,
            )

        except Exception as e:
            # Fail silently - warmup is optional optimization
            logger.warning(
                "contacts_cache_warmup_failed",
                user_id=str(user_id),
                error=str(e),
                error_type=type(e).__name__,
            )

    async def _warmup_contacts_cache_background(self, user_id: uuid.UUID) -> None:
        """Run the contacts cache warmup with its own DB session (background-safe).

        The warmup used to block the request path (300-800ms People API call on
        every cache expiry) before the graph could start. It is now fired in the
        background: the contacts clients fall back to the real API on cache miss
        (google_people_client cache-miss path), so an unfinished warmup can never
        produce empty results — worst case the first contacts tool call pays its
        own API latency, exactly like a cold cache did before.

        A dedicated session is required: the request's ToolDependencies session
        must not be used concurrently with the running graph (AsyncSession is
        not safe for concurrent use).
        """
        from src.infrastructure.database import get_db_context

        async with get_db_context() as warmup_db:
            warmup_deps = ToolDependencies(db_session=warmup_db)
            try:
                await self._warmup_contacts_cache_if_active(user_id, warmup_deps)
            finally:
                # Close the warmup's cached connector clients (pooled httpx).
                await warmup_deps.aclose()

    async def _archive_user_message_first(
        self,
        *,
        conv_service: "ConversationService",
        conversation_id: uuid.UUID,
        user_message: str,
        run_id: str,
        is_hitl_resumption: bool,
        attachment_meta: dict[str, Any],
        stt_kwargs: dict[str, Any],
    ) -> uuid.UUID | None:
        """Persist the user message BEFORE graph execution (archive-first).

        ADR-117 (Lot 1): the user turn must survive client disconnects,
        cancellations and crashes. End-of-run HITL flags (decision_type,
        hitl_interrupted) are patched onto this row during finalization.

        Args:
            conv_service: Conversation service used for archiving.
            conversation_id: Target conversation UUID.
            user_message: Raw user message content.
            run_id: Run identifier stored in the row metadata.
            is_hitl_resumption: True when this message answers a pending
                HITL interrupt (sets ``hitl_response`` immediately).
            attachment_meta: Attachment metadata block ({} when none).
            stt_kwargs: Per-message STT cost attribution kwargs.

        Returns:
            The archived row id, or None when archiving failed (best-effort:
            an archiving hiccup must never block the generation itself).
        """
        from src.core.field_names import FIELD_RUN_ID
        from src.infrastructure.database import get_db_context

        metadata: dict[str, Any] = {FIELD_RUN_ID: run_id, **attachment_meta}
        if is_hitl_resumption:
            metadata["hitl_response"] = True
        try:
            async with get_db_context() as archive_db:
                row = await conv_service.archive_message(
                    conversation_id,
                    "user",
                    user_message,
                    metadata,
                    archive_db,
                    **stt_kwargs,
                )
                return row.id
        except Exception as archive_err:  # noqa: BLE001 — must not kill the run
            logger.error(
                "archive_first_user_message_failed",
                run_id=run_id,
                conversation_id=str(conversation_id),
                error=str(archive_err),
                error_type=type(archive_err).__name__,
            )
            return None

    async def _patch_user_message_hitl_flags(
        self,
        *,
        conv_service: "ConversationService",
        db: AsyncSession,
        archived_user_msg_id: uuid.UUID | None,
        is_hitl_resumption: bool,
        hitl_interrupt_detected: bool,
        decision_type: str,
        run_id: str,
        conversation_id: uuid.UUID,
    ) -> None:
        """Patch end-of-run HITL flags onto the archive-first user row (ADR-117).

        The user row is archived BEFORE graph execution; the flags that are
        only known at end-of-run are merged here:
          - HITL resumption: ``decision_type`` (``hitl_response`` was already
            set at archive time)
          - HITL interrupt: ``hitl_interrupted: True``
          - Regular message (or missing row): nothing to patch

        Args:
            conv_service: Conversation service used for the metadata merge.
            db: Database session (caller manages commit via its context).
            archived_user_msg_id: Row id from archive-first, None if it failed.
            is_hitl_resumption: True when this turn answered a pending HITL.
            hitl_interrupt_detected: True when this turn raised a new HITL.
            decision_type: Parsed approval decision (resumption case).
            run_id: Run identifier (logging).
            conversation_id: Conversation UUID (logging).
        """
        if archived_user_msg_id is None:
            return
        if is_hitl_resumption:
            await conv_service.patch_message_metadata(
                archived_user_msg_id,
                {"decision_type": decision_type},
                db,
            )
            logger.info(
                "hitl_user_response_flag_patched",
                run_id=run_id,
                conversation_id=str(conversation_id),
                decision_type=decision_type,
            )
        elif hitl_interrupt_detected:
            await conv_service.patch_message_metadata(
                archived_user_msg_id,
                {"hitl_interrupted": True},
                db,
            )
            logger.info(
                "hitl_interrupted_flag_patched",
                run_id=run_id,
                conversation_id=str(conversation_id),
            )

    @staticmethod
    async def _should_start_voice(
        user_obj: Any,
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

    async def stream_chat_response(
        self,
        user_message: str,
        user_id: uuid.UUID,
        session_id: str,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
        user_language: str = "fr",
        user_display_name: str | None = None,
        original_run_id: str | None = None,
        run_id: str | None = None,
        archive_user_message: bool = True,
        has_listeners: ListenerProbe | None = None,
        browser_context: BrowserContext | None = None,
        user_memory_enabled: bool = True,
        user_journals_enabled: bool = False,
        user_psyche_enabled: bool = False,
        user_display_mode: str = "cards",
        user_execution_mode: str = "pipeline",
        is_automated_source: bool = False,
        auto_approve_plan: bool = False,
        attachment_ids: list[uuid.UUID] | None = None,
        stt_provider: str | None = None,
        stt_audio_duration_seconds: float | None = None,
        stt_cost_usd: float | None = None,
        stt_cost_eur: float | None = None,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Stream chat response with SSE chunks and conversation persistence.
        Executes graph and yields tokens, router decisions, and metadata in real-time.

        Args:
            user_message: User's message content.
            user_id: User UUID.
            session_id: Session identifier.
            user_timezone: User's IANA timezone for temporal context (default: "Europe/Paris").
            user_language: User's language code for localized responses (default: "fr").
            user_display_name: User's friendly first name for sender/signature context
                (default: None = unknown).
            original_run_id: Optional run_id from HITL resumption (for token aggregation).
            run_id: Optional externally-generated run identifier (ADR-117: the
                detached-producer path generates it up-front so the Redis run
                stream key is known before execution). Falls back to
                original_run_id, then to a fresh id.
            archive_user_message: When False, skips the archive-first user-row
                persistence (ADR-117) — used by scheduled-action retries whose
                first attempt already archived the row.
            browser_context: Browser context (geolocation, etc.) sent automatically by frontend.
            user_memory_enabled: User's preference for long-term memory (default: True).
            user_journals_enabled: User's preference for personal journals (default: False).
            user_psyche_enabled: User's preference for psyche engine (default: False).
            user_display_mode: Response display mode — 'cards', 'html', or 'markdown'.
            is_automated_source: If True, the run is automated (e.g. scheduled action) —
                response_node then skips memory/interest/journal/psyche extraction so
                only direct user inputs feed those subsystems (default: False).
            auto_approve_plan: If True, bypass HITL plan approval gate (for scheduled actions).
            attachment_ids: Optional list of attachment UUIDs for the current message.

        Yields:
            ChatStreamChunk: SSE chunks (router_decision, token, done, error).

        Example:
            >>> async for chunk in service.stream_chat_response(
            ...     "Hello", user_id, session_id,
            ...     user_timezone="America/New_York", user_language="en"
            ... ):
            >>>     print(chunk.type, chunk.content)
        """
        # === USAGE LIMIT CHECK (Layer 1: Service pre-check for scheduled actions) ===
        if getattr(settings, "usage_limits_enabled", False):
            from src.domains.usage_limits.service import UsageLimitService
            from src.infrastructure.observability.metrics_usage_limits import (
                usage_limit_enforcement_total,
            )

            _limit_check = await UsageLimitService.check_user_allowed(user_id)
            if not _limit_check.allowed:
                usage_limit_enforcement_total.labels(
                    layer="service", limit_type=_limit_check.exceeded_limit or "unknown"
                ).inc()
                yield ChatStreamChunk(
                    type="error",
                    content=_limit_check.blocked_reason or "Usage limit exceeded",
                    metadata={
                        "error_code": USAGE_LIMIT_EXCEEDED_ERROR_CODE,
                        "limit": _limit_check.exceeded_limit,
                    },
                )
                return
        # === END USAGE LIMIT CHECK ===

        # === LAST-KNOWN LOCATION CAPTURE (Phase 3) ===
        # Fire-and-forget: persist the browser geolocation for proactive
        # weather alerts when the user has opted in. Opt-in and throttle
        # are enforced inside the service. Failures are swallowed to
        # never break the chat UX. Uses safe_fire_and_forget to keep a
        # strong reference (avoids GC while the task runs).
        if browser_context is not None and browser_context.geolocation is not None:
            from src.domains.auth.user_location_service import (
                update_user_location_fire_and_forget,
            )
            from src.infrastructure.async_utils import safe_fire_and_forget

            safe_fire_and_forget(
                update_user_location_fire_and_forget(
                    user_id,
                    browser_context.geolocation.lat,
                    browser_context.geolocation.lon,
                    browser_context.geolocation.accuracy,
                ),
                name="last_known_location_update",
            )
        # === END LAST-KNOWN LOCATION CAPTURE ===

        # === PHASE 3.3 - Service Architecture (Migration Complete Day 7) ===
        # Uses: OrchestrationService, StreamingService, ConversationOrchestrator
        async for chunk in self._stream_with_new_services(
            user_message,
            user_id,
            session_id,
            user_timezone,
            user_language,
            user_display_name,
            original_run_id,
            browser_context,
            user_memory_enabled,
            user_journals_enabled,
            user_psyche_enabled,
            user_display_mode,
            user_execution_mode,
            is_automated_source,
            auto_approve_plan,
            attachment_ids,
            run_id=run_id,
            archive_user_message=archive_user_message,
            has_listeners=has_listeners,
            stt_provider=stt_provider,
            stt_audio_duration_seconds=stt_audio_duration_seconds,
            stt_cost_usd=stt_cost_usd,
            stt_cost_eur=stt_cost_eur,
        ):
            yield chunk

    async def _stream_with_new_services(
        self,
        user_message: str,
        user_id: uuid.UUID,
        session_id: str,
        user_timezone: str,
        user_language: str,
        user_display_name: str | None = None,
        original_run_id: str | None = None,
        browser_context: BrowserContext | None = None,
        user_memory_enabled: bool = True,
        user_journals_enabled: bool = False,
        user_psyche_enabled: bool = False,
        user_display_mode: str = "cards",
        user_execution_mode: str = "pipeline",
        is_automated_source: bool = False,
        auto_approve_plan: bool = False,
        attachment_ids: list[uuid.UUID] | None = None,
        *,
        run_id: str | None = None,
        archive_user_message: bool = True,
        has_listeners: ListenerProbe | None = None,
        stt_provider: str | None = None,
        stt_audio_duration_seconds: float | None = None,
        stt_cost_usd: float | None = None,
        stt_cost_eur: float | None = None,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Stream agent response using service-oriented architecture (Phase 3.3).

        Uses:
        - ConversationOrchestrator: Conversation lifecycle and setup
        - OrchestrationService: State loading + graph execution
        - StreamingService: SSE formatting and HITL detection

        Args:
            user_message: User's message content.
            user_id: User UUID.
            session_id: Session identifier.
            user_timezone: User's IANA timezone for temporal context.
            user_language: User's language code for localized responses.
            original_run_id: Optional run_id from HITL resumption for token aggregation.
                            When provided, reuses existing run_id to aggregate tokens
                            across HITL interrupt and resumption (critical for billing).
            browser_context: Browser context (geolocation, etc.) sent automatically by frontend.
                            Propagated to RunnableConfig.configurable for tools to access.
            user_memory_enabled: User's preference for long-term memory (extraction + injection).
            user_journals_enabled: User's preference for personal journals (extraction + injection).
            user_psyche_enabled: User's preference for psyche engine (default: False).
            user_display_mode: Response display mode — 'cards', 'html', or 'markdown'.
            is_automated_source: If True, the run is automated (e.g. scheduled action) —
                propagated to RunnableConfig.configurable so response_node skips
                memory/interest/journal/psyche extraction (default: False).
            auto_approve_plan: If True, inject plan_approved=True into state to bypass HITL gate.
            attachment_ids: Optional list of attachment UUIDs for the current message.
            run_id: Optional externally-generated run identifier (ADR-117 detached
                producer path). Falls back to original_run_id, then to a fresh id.
            archive_user_message: When False, skips the archive-first user-row
                persistence (scheduled-action retries — attempt 1 archived it).
        """
        # CRITICAL: Reuse original_run_id for HITL token aggregation.
        # ADR-117: an externally-supplied run_id (detached producer) wins so
        # the Redis stream key is known before execution starts.
        run_id = run_id or original_run_id or generate_run_id()
        # Detect HITL resumption early (needed for message counting logic)
        is_hitl_resumption = original_run_id is not None
        start_time = time.time()
        first_token_time = None
        intention_label = "unknown"
        token_count = 0

        logger.info(
            "new_service_architecture_starting",
            run_id=run_id,
            user_id=str(user_id),
            session_id=session_id,
            is_hitl_resumption=is_hitl_resumption,
        )

        # === NEW: Ensure graph is built with checkpointer ===
        await self._ensure_graph_built()

        # === NEW: Get or create conversation using ConversationOrchestrator ===
        from src.domains.agents.dependencies import ToolDependencies
        from src.domains.agents.services.conversation_orchestrator import ConversationOrchestrator
        from src.domains.agents.services.orchestration.service import OrchestrationService
        from src.domains.conversations.service import ConversationService
        from src.infrastructure.database import get_db_context

        conversation_orchestrator = ConversationOrchestrator()
        orchestration_service = OrchestrationService()
        conv_service = ConversationService()

        # Extended DB session scope: covers entire graph execution for tool reuse
        async with get_db_context() as db:
            # === Step 1: Setup conversation (get/create, tracking, OAuth scopes) ===
            context = await conversation_orchestrator.setup_conversation(
                user_id, session_id, run_id, db
            )

            conversation_id = context.conversation_id
            tracker = context.tracking_context
            oauth_scopes = context.oauth_scopes

            # === Load user's personality instruction (if set) ===
            personality_instruction = None
            try:
                from src.domains.personalities.service import PersonalityService

                personality_service = PersonalityService(db)
                personality_instruction = await personality_service.get_prompt_instruction_for_user(
                    user_id
                )
            except Exception as e:
                logger.warning(
                    "personality_load_failed_using_default",
                    user_id=str(user_id),
                    error=str(e),
                )

            # === Load user object for voice preference check ===
            user_obj = None
            try:
                from src.domains.users.service import UserService

                user_service = UserService(db)
                user_obj = await user_service.get_user_by_id(user_id)
            except Exception as e:
                logger.warning(
                    "user_load_failed_for_voice_check",
                    user_id=str(user_id),
                    error=str(e),
                )

            # Create dependencies container for tools (shared DB session, services, clients)
            tool_deps = ToolDependencies(db_session=db)

            # Warmup: preload contacts cache if a contacts provider is active.
            # Non-blocking (TTFT optimization): the contacts clients fall back to
            # the real API on cache miss, so the graph does not need to wait for
            # the warmup — see _warmup_contacts_cache_background docstring.
            from src.infrastructure.async_utils import safe_fire_and_forget

            safe_fire_and_forget(
                self._warmup_contacts_cache_background(user_id),
                name="contacts_cache_warmup",
            )

            logger.info(
                "conversation_setup_complete",
                run_id=run_id,
                conversation_id=str(conversation_id),
                oauth_scopes_count=len(oauth_scopes),
            )

            # Import MCP tools setup before try block to ensure cleanup is always accessible
            from src.core.context import (
                active_skills_ctx,
                admin_mcp_disabled_ctx,
                build_request_tool_manifests,
                request_tool_manifests_ctx,
            )
            from src.infrastructure.mcp.user_context import (
                cleanup_user_mcp_tools,
                setup_user_mcp_tools,
            )

            _admin_mcp_token = None
            _active_skills_token = None
            if user_obj:
                _admin_mcp_token = admin_mcp_disabled_ctx.set(
                    set(getattr(user_obj, "admin_mcp_disabled_servers", None) or [])
                )
                from src.domains.skills.preference_service import SkillPreferenceService

                _skill_svc = SkillPreferenceService(db)
                _active_skills = await _skill_svc.get_active_skills_for_user(user_obj.id)
                _active_skills_token = active_skills_ctx.set(_active_skills)

            _user_mcp_token = None  # Initialized before try for safe cleanup in except
            _manifests_token = None  # Initialized before try for safe cleanup in except
            # Voice services initialised here (instead of inside ``async with tracker``)
            # so the outer ``except`` cleanup branch can reference them even
            # when the exception fires before the inner block's declarations.
            chat_voice_streamer: ProgressiveSentenceStreamer | None = None
            chat_voice_drain_task: asyncio.Task[None] | None = None
            chat_voice_service: VoiceCommentService | None = None
            voice_service_parallel: VoiceCommentService | None = None
            try:
                async with tracker:
                    # === Per-user MCP tools setup (evolution F2.1) ===
                    _user_mcp_token = await setup_user_mcp_tools(user_id, db)

                    # === Build per-request filtered tool manifests (centralized) ===
                    from src.domains.agents.registry import get_global_registry

                    _manifests_token = request_tool_manifests_ctx.set(
                        build_request_tool_manifests(get_global_registry())
                    )

                    # === Step 2: Load or create state using OrchestrationService ===
                    state = await orchestration_service.load_or_create_state(
                        graph=self.graph,
                        conversation_id=conversation_id,
                        user_message=user_message,
                        user_id=user_id,
                        session_id=session_id,
                        run_id=run_id,
                        user_timezone=user_timezone,
                        user_language=user_language,
                        oauth_scopes=oauth_scopes,
                        personality_instruction=personality_instruction,
                        is_hitl_resumption=is_hitl_resumption,
                        user_display_name=user_display_name,
                    )

                    # === ATTACHMENT INJECTION (evolution F4) ===
                    # Load attachments and inject metadata + hint into state
                    # AFTER load_or_create_state, BEFORE graph execution
                    if attachment_ids and getattr(settings, "attachments_enabled", False):
                        from src.domains.attachments.llm_content import (
                            build_attachment_hint,
                        )
                        from src.domains.attachments.service import AttachmentService

                        attachment_service = AttachmentService(db)
                        attachments = await attachment_service.get_batch(attachment_ids, user_id)

                        if attachments:
                            # Annotate last HumanMessage for Router/Planner awareness
                            hint = build_attachment_hint(
                                [
                                    {
                                        "content_type": a.content_type,
                                        "original_filename": a.original_filename,
                                        "mime_type": a.mime_type,
                                    }
                                    for a in attachments
                                ],
                                user_language=user_language,
                            )
                            from langchain_core.messages import HumanMessage

                            for i in range(len(state["messages"]) - 1, -1, -1):
                                if isinstance(state["messages"][i], HumanMessage):
                                    state["messages"][i] = HumanMessage(
                                        content=f"{state['messages'][i].content}\n\n{hint}",
                                        id=state["messages"][i].id,
                                    )
                                    break

                            # Store lightweight metadata for response_node late resolution
                            state["metadata"]["current_turn_attachments"] = [
                                {
                                    "id": str(a.id),
                                    "mime_type": a.mime_type,
                                    "content_type": a.content_type,
                                    "file_path": a.file_path,
                                    "file_size": a.file_size,
                                    "original_filename": a.original_filename,
                                    "extracted_text": a.extracted_text,
                                }
                                for a in attachments
                            ]

                            logger.info(
                                "attachments_injected_into_state",
                                run_id=run_id,
                                attachment_count=len(attachments),
                                content_types=[a.content_type for a in attachments],
                            )

                    # === AUTO-APPROVE: Bypass HITL plan approval gate ===
                    # Used by scheduled actions executor to skip human approval
                    if auto_approve_plan:
                        state["plan_approved"] = True  # type: ignore[literal-required]
                        logger.info(
                            "auto_approve_plan_injected",
                            run_id=run_id,
                            user_id=str(user_id),
                        )

                    # === ARCHIVE-FIRST (ADR-117): persist the user turn NOW ===
                    # The user message must survive client disconnects,
                    # cancellations and crashes. End-of-run HITL flags
                    # (decision_type, hitl_interrupted) are patched onto this
                    # row during finalization below.
                    stt_kwargs = {
                        "stt_provider": stt_provider,
                        "stt_audio_duration_seconds": stt_audio_duration_seconds,
                        "stt_cost_usd": stt_cost_usd,
                        "stt_cost_eur": stt_cost_eur,
                    }
                    _attachment_meta: dict[str, Any] = {}
                    if attachment_ids and getattr(settings, "attachments_enabled", False):
                        _turn_attachments = state.get("metadata", {}).get(
                            "current_turn_attachments", []
                        )
                        if _turn_attachments:
                            _attachment_meta = {
                                "attachments": [
                                    {
                                        "id": a["id"],
                                        "filename": a["original_filename"],
                                        "mime_type": a["mime_type"],
                                        "size": a.get("file_size", 0),
                                        "content_type": a["content_type"],
                                    }
                                    for a in _turn_attachments
                                ]
                            }
                    archived_user_msg_id: uuid.UUID | None = None
                    if archive_user_message:
                        archived_user_msg_id = await self._archive_user_message_first(
                            conv_service=conv_service,
                            conversation_id=conversation_id,
                            user_message=user_message,
                            run_id=run_id,
                            is_hitl_resumption=is_hitl_resumption,
                            attachment_meta=_attachment_meta,
                            stt_kwargs=stt_kwargs,
                        )

                    # === TRACKING: Count user message ===
                    # Count ALL user messages (initial AND HITL responses)
                    # Each user message is a distinct interaction that should be counted:
                    # - Initial message: "recherche jean" → count=1
                    # - HITL response: "oui" → count=1
                    # This ensures accurate message_count in user_statistics for billing/analytics.
                    await tracker.increment_message_count()

                    # === Step 3: Execute graph stream using OrchestrationService + StreamingService ===
                    # Content tracking for archiving and metrics
                    response_content = ""
                    intention_label = "unknown"
                    token_count = 0
                    first_token_time = None

                    # Import StreamingService and HITL dependencies
                    from src.domains.agents.services.streaming.service import StreamingService
                    from src.domains.agents.utils.hitl_store import HITLStore
                    from src.infrastructure.cache.redis import get_redis_cache

                    # Parallel voice generation: task starts when registry available
                    # This runs voice LLM + TTS in parallel with response_node streaming
                    # Uses asyncio.Queue for PROGRESSIVE chunk emission (not wait for all)
                    # NOTE: voice_service_parallel is initialised at the outer
                    # try/except level (above) so it stays accessible from
                    # the cleanup branch even when an early exception fires.
                    voice_parallel_task: asyncio.Task | None = None
                    voice_chunk_queue: asyncio.Queue | None = None  # Queue for progressive emission
                    voice_start_emitted = False  # Track if voice_comment_start was emitted
                    voice_complete_emitted = False  # Track if voice_complete was emitted
                    voice_chunk_count = 0  # Count emitted chunks for voice_complete metadata

                    # Sentence streaming for chat-mode (intention=conversation):
                    # spun up on the FIRST router_decision and fed token-by-token
                    # so the user hears audio as soon as the first sentence is ready
                    # — bypasses "wait full response then split + TTS" sync path.
                    # NOTE: actual variables (``chat_voice_streamer`` /
                    # ``chat_voice_drain_task`` / ``chat_voice_service``) are
                    # declared at the outer ``try/except`` level for cleanup
                    # symmetry — see comment in the outer scope.

                    # Extract LIA gender once for both parallel and sync voice paths
                    # (DRY: avoid duplicating this extraction in multiple code paths)
                    voice_lia_gender = (
                        browser_context.lia_gender
                        if browser_context and browser_context.lia_gender
                        else "female"
                    )

                    # Initialize HITL dependencies
                    redis = await get_redis_cache()
                    hitl_store = HITLStore(
                        redis_client=redis,
                        ttl_seconds=settings.hitl_pending_data_ttl_seconds,
                    )

                    # Pre-compute debug panel flag for this user (zero-overhead when disabled)
                    # Admin: system_setting.debug_panel_enabled
                    # Non-admin: system_setting.debug_panel_user_access_enabled AND user.debug_panel_enabled
                    debug_panel_for_user = False
                    try:
                        from src.domains.system_settings.service import (
                            get_debug_panel_enabled,
                            get_debug_panel_user_access_enabled,
                        )

                        if user_obj and user_obj.is_superuser:
                            debug_panel_for_user = await get_debug_panel_enabled()
                        elif user_obj:
                            user_access = await get_debug_panel_user_access_enabled()
                            debug_panel_for_user = user_access and user_obj.debug_panel_enabled
                    except Exception as e:
                        logger.debug("debug_panel_pre_compute_failed", error=str(e))

                    # Create StreamingService with HITL dependencies
                    streaming_service = StreamingService(
                        conv_service=conv_service,
                        hitl_store=hitl_store,
                        tracker=tracker,
                        user_message=user_message,
                        user_id=str(user_id),
                        debug_panel_enabled=debug_panel_for_user,
                        is_hitl_resumption=is_hitl_resumption,
                    )

                    # Side-channel queue: generic mechanism for tools to emit SSE chunks
                    # directly to the frontend (bypasses LLM, not persisted).
                    # Created unconditionally — tools decide individually whether to emit.
                    side_channel_queue: asyncio.Queue = asyncio.Queue()

                    # === StreamingService handles everything: SSE formatting + HITL ===
                    try:
                        sse_stream = streaming_service.stream_sse_chunks(
                            graph_stream=orchestration_service.execute_graph_stream(
                                graph=self.graph,
                                state=state,
                                conversation_id=conversation_id,
                                user_id=user_id,
                                session_id=session_id,
                                run_id=run_id,
                                tool_deps=tool_deps,
                                tracker=tracker,
                                browser_context=browser_context,
                                user_message=user_message,  # For location phrase detection
                                user_memory_enabled=user_memory_enabled,  # User memory preference
                                user_journals_enabled=user_journals_enabled,  # User journals preference
                                user_psyche_enabled=user_psyche_enabled,  # User psyche preference
                                user_display_mode=user_display_mode,  # User display mode (cards/html/markdown)
                                user_execution_mode=user_execution_mode,  # Execution mode (pipeline/react)
                                is_automated_source=is_automated_source,  # True for scheduled actions (skips extraction)
                                side_channel_queue=side_channel_queue,  # SSE side-channel
                            ),
                            conversation_id=conversation_id,
                            run_id=run_id,
                        )

                        # Wrap SSE stream to interleave side-channel queue items
                        # (screenshots, etc.) even when the graph is busy in a long
                        # node execution like the ReAct browser loop.
                        async for (
                            sse_chunk,
                            content_fragment,
                        ) in self._interleave_side_channel(sse_stream, side_channel_queue):
                            # Track response content for archiving
                            # ✅ CRITICAL FIX: content_replacement should REPLACE, not append
                            # When photos are injected via post-processing, StreamingService emits
                            # a content_replacement chunk with the FULL final content (including photos).
                            # We must REPLACE the streamed content, not append it, to avoid duplication.
                            # See: Message duplication bug on history reload
                            if sse_chunk.type == "content_replacement":
                                response_content = content_fragment  # REPLACE with final content
                            else:
                                response_content += content_fragment  # APPEND for regular tokens

                            # Track intention from router decisions
                            if sse_chunk.type == "router_decision":
                                intention_label = sse_chunk.metadata.get("intention", "unknown")

                                # === CHAT-MODE PROGRESSIVE TTS ===
                                # When the router classifies the turn as
                                # ``conversation`` (chat mode, no tools), the
                                # voice context registry will stay None and the
                                # legacy path would wait for response completion
                                # before starting TTS. Spin up a sentence
                                # streamer NOW so each sentence is synthesised
                                # as soon as it's complete in the chat LLM
                                # stream — first audio lands within ~1 s.
                                if (
                                    chat_voice_streamer is None
                                    and voice_parallel_task is None
                                    and intention_label == "conversation"
                                    and await self._should_start_voice(
                                        user_obj, has_listeners, run_id, "chat_progressive"
                                    )
                                ):
                                    try:
                                        from src.domains.voice.service import (
                                            VoiceCommentService,
                                        )

                                        chat_voice_service = VoiceCommentService(
                                            tracker=tracker,
                                            run_id=run_id,
                                            lia_gender=voice_lia_gender,
                                            user_id=str(user_id),
                                        )
                                        if voice_chunk_queue is None:
                                            voice_chunk_queue = asyncio.Queue()
                                        (
                                            chat_voice_streamer,
                                            chat_voice_drain_task,
                                        ) = await chat_voice_service.start_progressive_chat_stream(
                                            user_language=user_language,
                                            chunk_queue=voice_chunk_queue,
                                        )
                                        logger.info(
                                            "chat_voice_progressive_started",
                                            run_id=run_id,
                                            elapsed_since_start_ms=int(
                                                (time.time() - start_time) * 1000
                                            ),
                                        )
                                    except Exception as chat_voice_err:
                                        logger.warning(
                                            "chat_voice_progressive_start_failed",
                                            run_id=run_id,
                                            error=str(chat_voice_err),
                                            error_type=type(chat_voice_err).__name__,
                                        )
                                        chat_voice_streamer = None
                                        chat_voice_drain_task = None

                            # Track token count and first token time
                            if sse_chunk.type == "token":
                                if first_token_time is None:
                                    first_token_time = time.time()
                                token_count += 1
                                # Feed the chat-mode streamer with each new
                                # response token so sentences are extracted
                                # and TTS-dispatched as they complete.
                                if chat_voice_streamer is not None and content_fragment:
                                    chat_voice_streamer.feed(content_fragment)

                            # === PARALLEL VOICE: Start when registry becomes available ===
                            # Registry is populated after task_orchestrator completes tools
                            # We can start voice generation before response_node finishes
                            #
                            # DIAGNOSTIC: Log when conditions are first met to debug first-message timing
                            if (
                                voice_parallel_task is None
                                and streaming_service.voice_context_registry is not None
                            ):
                                logger.debug(
                                    "voice_parallel_conditions_check",
                                    run_id=run_id,
                                    chunk_type=sse_chunk.type,
                                    has_registry=True,
                                    voice_enabled=user_obj.voice_enabled if user_obj else None,
                                    will_start=bool(user_obj and user_obj.voice_enabled),
                                )

                            if (
                                voice_parallel_task is None
                                and chat_voice_drain_task is None
                                # If a chat-mode sentence streamer is already
                                # running (router said ``conversation``) we
                                # must NOT spawn the agent-mode parallel
                                # voice — both producers would race on
                                # ``voice_chunk_queue`` and the chat audio
                                # would silently disappear when the parallel
                                # path overwrites the queue reference below.
                                and streaming_service.voice_context_registry is not None
                                and await self._should_start_voice(
                                    user_obj, has_listeners, run_id, "agent_parallel"
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
                                        streaming_service.voice_context_registry,
                                        user_language,
                                    )

                                    # Create voice service for parallel generation
                                    # (uses voice_lia_gender extracted once before streaming loop)
                                    voice_service_parallel = VoiceCommentService(
                                        tracker=tracker,
                                        run_id=run_id,
                                        lia_gender=voice_lia_gender,
                                        user_id=str(user_id),
                                    )

                                    # Create queue for PROGRESSIVE chunk emission
                                    # Each audio chunk is put in queue as soon as it's ready
                                    voice_chunk_queue = asyncio.Queue()

                                    # Start parallel voice generation task (streams to queue)
                                    voice_parallel_task = asyncio.create_task(
                                        self._stream_voice_chunks_to_queue(
                                            voice_service=voice_service_parallel,
                                            context_summary=voice_context,
                                            personality_instruction=personality_instruction or "",
                                            user_language=user_language,
                                            current_datetime=now_in_timezone(
                                                user_timezone
                                            ).isoformat(),
                                            user_query=user_message,
                                            chunk_queue=voice_chunk_queue,
                                            user_timezone=user_timezone,
                                        )
                                    )

                                    logger.info(
                                        "voice_parallel_task_started",
                                        run_id=run_id,
                                        voice_context_length=(
                                            len(voice_context) if voice_context else 0
                                        ),
                                        registry_items_count=len(
                                            streaming_service.voice_context_registry
                                        ),
                                        elapsed_since_start_ms=int(
                                            (time.time() - start_time) * 1000
                                        ),
                                        mode="progressive_queue",
                                    )

                                except Exception as parallel_start_error:
                                    # Non-fatal: Log and continue, will fallback to sync
                                    logger.warning(
                                        "voice_parallel_task_start_failed",
                                        run_id=run_id,
                                        error=str(parallel_start_error),
                                        error_type=type(parallel_start_error).__name__,
                                    )
                                    # voice_parallel_task stays None, fallback to sync later

                            # Yield SSE chunk to client
                            yield sse_chunk

                            # === PROGRESSIVE VOICE EMISSION: Emit chunks as they become available ===
                            # Check queue for available chunks (non-blocking via get_nowait)
                            # This emits audio chunks PROGRESSIVELY during streaming
                            if voice_chunk_queue is not None and not voice_complete_emitted:
                                try:
                                    # Drain all available chunks from queue (non-blocking)
                                    while True:
                                        try:
                                            audio_chunk = voice_chunk_queue.get_nowait()

                                            # None is sentinel = generation complete
                                            if audio_chunk is None:
                                                # Emit voice_complete only if we started
                                                if voice_start_emitted:
                                                    yield ChatStreamChunk(
                                                        type="voice_complete",
                                                        content="",
                                                        metadata={
                                                            "run_id": run_id,
                                                            "chunk_count": voice_chunk_count,
                                                            "source": "parallel_progressive",
                                                        },
                                                    )
                                                    voice_complete_emitted = True
                                                    logger.info(
                                                        "voice_progressive_complete",
                                                        run_id=run_id,
                                                        chunk_count=voice_chunk_count,
                                                    )
                                                break

                                            # First chunk: emit voice_comment_start
                                            if not voice_start_emitted:
                                                yield ChatStreamChunk(
                                                    type="voice_comment_start",
                                                    content="",
                                                    metadata={"run_id": run_id},
                                                )
                                                voice_start_emitted = True
                                                logger.info(
                                                    "voice_progressive_started",
                                                    run_id=run_id,
                                                    elapsed_since_start_ms=int(
                                                        (time.time() - start_time) * 1000
                                                    ),
                                                )

                                            # Emit audio chunk (DRY: use helper)
                                            yield self._format_voice_audio_chunk(audio_chunk)
                                            voice_chunk_count += 1

                                            logger.debug(
                                                "voice_progressive_chunk_emitted",
                                                run_id=run_id,
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
                                        run_id=run_id,
                                        error=str(progressive_emit_error),
                                        error_type=type(progressive_emit_error).__name__,
                                    )

                    except GraphInterrupt:
                        # === HITL INTERRUPT FALLBACK: Handle if not caught in stream ===
                        # This should rarely happen since __interrupt__ is detected in mode="values"
                        # But kept as safety net for edge cases
                        logger.warning(
                            "graph_interrupt_caught_outside_stream",
                            run_id=run_id,
                            conversation_id=str(conversation_id),
                        )

                        # Commit tracking data BEFORE generator exits
                        await tracker.commit()

                        # Cancel the chat-mode sentence streamer if it was
                        # spun up — otherwise the LLM feeder + in-flight TTS
                        # tasks would leak when this generator returns
                        # (the tracker context exit does not propagate
                        # to background tasks).
                        await self._cleanup_chat_voice_pipeline(
                            chat_voice_streamer,
                            chat_voice_drain_task,
                            run_id,
                            chat_voice_service,
                        )

                        logger.info(
                            "tracking_committed_on_graph_interrupt_fallback",
                            run_id=run_id,
                            conversation_id=str(conversation_id),
                        )

                        # Exit generator cleanly - HITL will resume on next user message
                        # Do NOT re-raise - this is expected behavior for HITL flow
                        return

                    # === Step 5: Finalize conversation ===
                    # Compute metrics
                    duration = time.time() - start_time
                    ttft = first_token_time - start_time if first_token_time else None

                    # NOTE (ADR-117): attachment metadata and STT kwargs are now
                    # built BEFORE graph execution (archive-first block above).

                    # Signal end-of-input to the chat-mode sentence streamer
                    # so its trailing buffer (last sentence — likely without
                    # a punctuation terminator) is flushed and the drain task
                    # can finalise once every TTS call resolves.
                    if chat_voice_streamer is not None:
                        try:
                            chat_voice_streamer.close_input()
                        except Exception as close_err:
                            logger.warning(
                                "chat_voice_streamer_close_failed",
                                run_id=run_id,
                                error=str(close_err),
                            )

                    # === Finalize archived rows BEFORE exiting tracker context ===
                    # ADR-117 (archive-first): the user row was persisted BEFORE
                    # graph execution. Here we only patch the HITL flags that are
                    # first known at end-of-run:
                    # 1. HITL resumption: patch {decision_type} (hitl_response was
                    #    already set at archive time)
                    # 2. HITL interrupt: patch {hitl_interrupted: True}
                    # 3. Regular message: nothing to patch
                    # The assistant row (response OR HITL question) is archived
                    # here as before.

                    # Track number of messages archived for accurate stats
                    # (user row was archived up-front — count it if it exists)
                    messages_archived = 1 if archived_user_msg_id is not None else 0
                    archived_assistant_msg_id: uuid.UUID | None = None

                    async with get_db_context() as archive_db:
                        _interrupt_resume_data = state.get("_interrupt_resume_data", {})
                        await self._patch_user_message_hitl_flags(
                            conv_service=conv_service,
                            db=archive_db,
                            archived_user_msg_id=archived_user_msg_id,
                            is_hitl_resumption=is_hitl_resumption,
                            hitl_interrupt_detected=streaming_service.hitl_interrupt_detected,
                            decision_type=_interrupt_resume_data.get("decision", "UNKNOWN"),
                            run_id=run_id,
                            conversation_id=conversation_id,
                        )

                        # Archive assistant message (response OR HITL question)
                        if streaming_service.hitl_interrupt_detected:
                            # HITL interrupt: Archive the HITL question for history persistence
                            # This ensures the question appears on page reload
                            if streaming_service.hitl_generated_question:
                                await conv_service.archive_message(
                                    conversation_id,
                                    "assistant",
                                    streaming_service.hitl_generated_question,
                                    {
                                        FIELD_RUN_ID: run_id,
                                        "hitl_question": True,
                                        "intention": intention_label,
                                    },
                                    archive_db,
                                )
                                messages_archived += 1
                                logger.info(
                                    "hitl_question_archived",
                                    run_id=run_id,
                                    conversation_id=str(conversation_id),
                                    question_length=len(streaming_service.hitl_generated_question),
                                )
                        elif response_content.strip():
                            # Regular response: Archive the assistant response
                            assistant_metadata = {
                                FIELD_RUN_ID: run_id,
                                "intention": intention_label,
                            }
                            if is_hitl_resumption:
                                assistant_metadata["hitl_approved"] = True

                            # Persist generated image URLs in message metadata
                            # so they survive page reload (frontend reads them back)
                            if getattr(settings, "image_generation_enabled", False):
                                from src.domains.image_generation.image_store import (
                                    peek_pending_images,
                                )

                                peeked = peek_pending_images(str(conversation_id))
                                if peeked:
                                    assistant_metadata["generated_images"] = [
                                        {"url": img.url, "alt": img.alt_text} for img in peeked
                                    ]

                            # Persist last browser screenshot as Attachment for card display
                            browser_screenshot_card_url: str | None = None
                            if getattr(settings, "browser_progressive_screenshots", False):
                                from src.domains.agents.tools.browser_screenshot_store import (
                                    get_and_clear_last_screenshot,
                                )

                                last_screenshot_bytes = get_and_clear_last_screenshot(
                                    str(conversation_id)
                                )
                                if last_screenshot_bytes:
                                    try:
                                        from datetime import UTC, datetime, timedelta
                                        from pathlib import Path

                                        from src.domains.attachments.models import (
                                            AttachmentContentType,
                                            AttachmentStatus,
                                        )
                                        from src.domains.attachments.repository import (
                                            AttachmentRepository,
                                        )
                                        from src.infrastructure.database.session import (
                                            get_db_context,
                                        )

                                        stored_fn = f"browser_{uuid.uuid4()}.jpg"
                                        rel_path = f"{user_id}/{stored_fn}"
                                        abs_path = (
                                            Path(settings.attachments_storage_path) / rel_path
                                        )
                                        abs_path.parent.mkdir(parents=True, exist_ok=True)
                                        abs_path.write_bytes(last_screenshot_bytes)

                                        async with get_db_context() as attach_db:
                                            attach_repo = AttachmentRepository(attach_db)
                                            attachment = await attach_repo.create(
                                                {
                                                    "user_id": user_id,
                                                    "original_filename": stored_fn,
                                                    "stored_filename": stored_fn,
                                                    "mime_type": "image/jpeg",
                                                    "file_size": len(last_screenshot_bytes),
                                                    "file_path": rel_path,
                                                    "content_type": AttachmentContentType.IMAGE,
                                                    "status": AttachmentStatus.READY,
                                                    "expires_at": datetime.now(UTC)
                                                    + timedelta(
                                                        hours=settings.attachments_ttl_hours,
                                                    ),
                                                }
                                            )
                                            await attach_db.commit()

                                        browser_screenshot_card_url = (
                                            f"/api/v1/attachments/{attachment.id}"
                                        )
                                        assistant_metadata["browser_screenshot"] = {
                                            "url": browser_screenshot_card_url,
                                            "alt": "Browser screenshot",
                                        }

                                        logger.debug(
                                            "browser_screenshot_card_saved",
                                            run_id=run_id,
                                            attachment_id=str(attachment.id),
                                        )
                                    except Exception as bsc_err:
                                        logger.warning(
                                            "browser_screenshot_card_save_failed",
                                            run_id=run_id,
                                            error=str(bsc_err),
                                            error_type=type(bsc_err).__name__,
                                        )

                            archived_msg = await conv_service.archive_message(
                                conversation_id,
                                "assistant",
                                response_content,
                                assistant_metadata,
                                archive_db,
                            )
                            archived_assistant_msg_id = archived_msg.id
                            messages_archived += 1

                    logger.info(
                        "new_service_architecture_stream_completed",
                        run_id=run_id,
                        duration=duration,
                        ttft=ttft,
                        token_count=token_count,
                    )

                # === CRITICAL: TrackingContext exits here via __aexit__() ===
                # This commits token data to database with UPSERT aggregation
                # In HITL flows, multiple TrackingContext instances with same run_id
                # will be automatically aggregated by the UPSERT logic

                # === Wait for background extraction tasks before querying tokens ===
                # Memory and interest extraction run as background asyncio tasks
                # (scheduled in response_node via safe_fire_and_forget).
                # They UPSERT their tokens into the same MessageTokenSummary record.
                # We must await them here so the aggregated query below includes
                # the complete cost (pipeline + memory + interest extraction).
                from src.infrastructure.async_utils import await_run_id_tasks

                await await_run_id_tasks(run_id, timeout=15.0)

                # === Persist psyche_state into archived assistant message metadata ===
                # The psyche background task (fire-and-forget) has completed by now.
                # We peek the summary and patch it into the message so that on page
                # reload, each message carries its own historical psyche snapshot
                # instead of falling back to the current (latest) store state.
                if (
                    archived_assistant_msg_id
                    and getattr(settings, "psyche_enabled", False)
                    and user_psyche_enabled
                ):
                    try:
                        from src.domains.psyche.service import peek_psyche_summary

                        _ps = peek_psyche_summary(run_id)
                        if _ps:
                            async with get_db_context() as psyche_patch_db:
                                await conv_service.patch_message_metadata(
                                    archived_assistant_msg_id,
                                    {"psyche_state": _ps},
                                    psyche_patch_db,
                                )
                                await psyche_patch_db.commit()
                            logger.debug(
                                "psyche_state_persisted_to_message",
                                run_id=run_id,
                                message_id=str(archived_assistant_msg_id),
                            )
                    except Exception as ps_err:
                        logger.warning(
                            "psyche_state_persist_failed",
                            run_id=run_id,
                            error=str(ps_err),
                            error_type=type(ps_err).__name__,
                        )

                # === PHASE 3.3 DAY 3: Retrieve aggregated tokens AFTER tracker exit ===
                # Pattern from LEGACY (lines 1520-1543): Create temp tracker to query DB
                # This ensures we get the COMPLETE aggregated token count including:
                # - First invocation (router + planner + interrupt): e.g., 2,704 tokens
                # - Second invocation (agents + response after approval): e.g., 6,459 tokens
                # - Background extraction (memory + interests): e.g., 3,500 tokens
                # - Total aggregated by DB UPSERT
                from src.domains.chat.service import TrackingContext

                temp_tracker = TrackingContext(
                    run_id=run_id,
                    user_id=user_id,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    auto_commit=False,  # Don't commit, just query
                )
                aggregated_summary_dto = await temp_tracker.get_aggregated_summary_dto_from_db()
                total_tokens = aggregated_summary_dto.tokens_in + aggregated_summary_dto.tokens_out

                logger.info(
                    "aggregated_summary_retrieved_for_sse",
                    run_id=run_id,
                    aggregated_tokens_in=aggregated_summary_dto.tokens_in,
                    aggregated_tokens_out=aggregated_summary_dto.tokens_out,
                    aggregated_tokens_cache=aggregated_summary_dto.tokens_cache,
                    aggregated_cost_eur=aggregated_summary_dto.cost_eur,
                    message_count=aggregated_summary_dto.message_count,
                )

                # Update conversation stats with FINAL aggregated token count
                # Pass actual number of messages archived for accurate counting
                async with get_db_context() as stats_db:
                    await conv_service.increment_conversation_stats(
                        conversation_id,
                        total_tokens,
                        stats_db,
                        message_increment=messages_archived,
                    )

                # === Backfill the assistant row with TTS attribution ===
                # The voice synthesis (parallel progressive OR sync fallback)
                # has had its calls recorded by tracker.record_tts_call(); the
                # tracker context already exited and pushed the records to the
                # module-level _run_tts_records bucket. We MUST run this UPDATE
                # before cleanup_run_records() below — the cleanup wipes that
                # bucket and the second aggregated_summary in the done chunk
                # would then read tts=0 from in-memory.
                #
                # The captured snapshot survives the cleanup and feeds the
                # done chunk metadata so the live frontend badge can render
                # immediately without waiting for a page reload.
                tts_snapshot_for_done: dict[str, Any] | None = None
                if archived_assistant_msg_id is not None:
                    try:
                        tts_usage = temp_tracker.get_tts_usage_for_archive()
                        if tts_usage:
                            tts_snapshot_for_done = dict(tts_usage)
                            async with get_db_context() as tts_db:
                                await conv_service.update_message_tts(
                                    archived_assistant_msg_id,
                                    tts_usage,
                                    tts_db,
                                )
                                await tts_db.commit()
                            logger.debug(
                                "tts_backfill_done",
                                run_id=run_id,
                                message_id=str(archived_assistant_msg_id),
                                tts_provider=tts_usage.get("tts_provider"),
                                tts_characters=tts_usage.get("tts_characters"),
                            )
                    except Exception as tts_archive_err:
                        logger.warning(
                            "tts_backfill_failed",
                            run_id=run_id,
                            message_id=str(archived_assistant_msg_id),
                            error=str(tts_archive_err),
                            error_type=type(tts_archive_err).__name__,
                        )

                # Cleanup run-level record collector (prevents memory leak)
                TrackingContext.cleanup_run_records(run_id)

                # === PHASE 3.3 DAY 3: Cleanup pending_hitl after successful HITL completion ===
                # If this was a HITL resumption (original_run_id provided), check if we need
                # to cleanup the pending_hitl data from Redis to prevent it from being
                # detected on the next user message.
                #
                # Why cleanup here:
                # 1. Graph completed successfully without new interrupt
                # 2. User's next message should be treated as NEW conversation, not HITL response
                # 3. Prevents bug where "recherche jean" after "recherche jean + HITL" is
                #    misinterpreted as HITL response
                #
                # CRITICAL FIX: Only clear if NO new interrupt was generated during resumption.
                # Multi-step clarification flows (e.g., email: to -> subject/body) generate
                # MULTIPLE interrupts. We must NOT clear the new interrupt data!
                # Example bug before fix:
                #   1. User responds to clarif #1 (provides email "to")
                #   2. Graph resumes, generates clarif #2 (asks for subject/body)
                #   3. OLD CODE: Cleared interrupt data here (BUG!)
                #   4. User responds to clarif #2, but data is gone -> HITL classifier fails
                #
                # Safety: This is Layer 1 defense. Layer 2 (router expiry check) provides
                # additional protection if this cleanup fails due to exception or crash.
                if original_run_id and not streaming_service.hitl_interrupt_detected:
                    # This was a HITL resumption AND no new interrupt was generated
                    # Safe to cleanup pending_hitl
                    try:
                        from src.domains.agents.utils.hitl_store import HITLStore
                        from src.infrastructure.cache.redis import get_redis_cache

                        redis = await get_redis_cache()
                        hitl_store = HITLStore(
                            redis_client=redis,
                            ttl_seconds=settings.hitl_pending_data_ttl_seconds,
                        )

                        # Clear pending_hitl since graph completed without re-interrupting
                        await hitl_store.clear_interrupt(thread_id=str(conversation_id))

                        # Invalidate in-memory cache to prevent stale data on next request
                        from src.domains.agents.api.router import invalidate_hitl_cache

                        invalidate_hitl_cache(str(conversation_id))

                        logger.info(
                            "pending_hitl_cleared_after_completion",
                            run_id=run_id,
                            original_run_id=original_run_id,
                            conversation_id=str(conversation_id),
                            reason="HITL flow completed successfully, no new interrupt",
                        )
                    except Exception as cleanup_error:
                        # Non-fatal: Log error but continue (Layer 2 will handle expiry)
                        logger.error(
                            "pending_hitl_cleanup_failed",
                            run_id=run_id,
                            original_run_id=original_run_id,
                            conversation_id=str(conversation_id),
                            error=str(cleanup_error),
                            fallback="Layer 2 router expiry check will handle",
                        )
                elif original_run_id and streaming_service.hitl_interrupt_detected:
                    # HITL resumption with NEW interrupt - don't clear, just log
                    logger.info(
                        "pending_hitl_preserved_for_new_interrupt",
                        run_id=run_id,
                        original_run_id=original_run_id,
                        conversation_id=str(conversation_id),
                        reason="New interrupt generated during HITL resumption",
                    )

                # === VOICE TTS: Emit remaining chunks or sync fallback ===
                # Priority: 1) Progressive emission during streaming (may be complete)
                #           2) Drain remaining queue chunks at end of stream
                #           3) Sync fallback if no parallel task
                # Skip if voice_complete was already emitted during streaming loop
                voice_needs_finalization = (
                    bool(response_content.strip())
                    and not streaming_service.hitl_interrupt_detected
                    and not voice_complete_emitted  # Skip if already completed during streaming
                    # Listener gating last (may hit Redis) — cheap checks first
                    and await self._should_start_voice(
                        user_obj, has_listeners, run_id, "sync_fallback"
                    )
                )

                # DIAGNOSTIC: Track parallel task state at end of streaming
                parallel_task_done = (
                    voice_parallel_task.done() if voice_parallel_task is not None else None
                )
                logger.debug(
                    "voice_feature_check",
                    run_id=run_id,
                    voice_needs_finalization=voice_needs_finalization,
                    has_parallel_task=voice_parallel_task is not None,
                    parallel_task_done=parallel_task_done,
                    voice_start_emitted=voice_start_emitted,
                    voice_complete_emitted=voice_complete_emitted,
                    voice_chunk_count=voice_chunk_count,
                    response_content_length=len(response_content) if response_content else 0,
                )

                # DIAGNOSTIC: Log if progressive emission started but not completed
                if voice_start_emitted and not voice_complete_emitted:
                    logger.info(
                        "voice_progressive_incomplete_will_drain",
                        run_id=run_id,
                        reason="Progressive emission started but not all chunks emitted",
                        chunks_emitted_so_far=voice_chunk_count,
                        parallel_task_done=parallel_task_done,
                    )

                if voice_needs_finalization:
                    try:

                        from src.domains.agents.formatters.text_summary import (
                            generate_text_summary_for_llm,
                        )
                        from src.domains.voice.service import VoiceCommentService

                        chunk_count = voice_chunk_count  # Continue from progressive count
                        voice_source = "unknown"

                        # === PATH 1: Drain remaining chunks from queue ===
                        # Two queue producers can populate voice_chunk_queue:
                        # - voice_parallel_task (agent mode, registry-driven)
                        # - chat_voice_drain_task (chat mode, sentence streamer)
                        # Both push the same VoiceAudioChunk shape and end with
                        # a None sentinel — the drain loop is identical.
                        active_voice_task = voice_parallel_task or chat_voice_drain_task
                        if voice_chunk_queue is not None and active_voice_task is not None:
                            try:
                                # Wait for the producer task with configurable timeout
                                # This ensures all chunks are in the queue
                                await asyncio.wait_for(
                                    active_voice_task,
                                    timeout=settings.voice_parallel_timeout_seconds,
                                )
                                voice_source = (
                                    "parallel_drain"
                                    if voice_parallel_task is not None
                                    else "chat_progressive_drain"
                                )

                                # Drain remaining chunks from queue
                                while True:
                                    try:
                                        audio_chunk = voice_chunk_queue.get_nowait()

                                        # None is sentinel = generation complete
                                        if audio_chunk is None:
                                            break

                                        # First chunk: emit voice_comment_start if not yet emitted
                                        if not voice_start_emitted:
                                            yield ChatStreamChunk(
                                                type="voice_comment_start",
                                                content="",
                                                metadata={"run_id": run_id},
                                            )
                                            voice_start_emitted = True

                                        # Emit audio chunk (DRY: use helper)
                                        yield self._format_voice_audio_chunk(audio_chunk)
                                        chunk_count += 1

                                    except asyncio.QueueEmpty:
                                        break

                                logger.info(
                                    "voice_queue_drained_at_end",
                                    run_id=run_id,
                                    total_chunk_count=chunk_count,
                                    progressive_count=voice_chunk_count,
                                    drained_count=chunk_count - voice_chunk_count,
                                )

                                # Commit TTS tokens tracked during voice generation
                                # TrackingContext already exited, but tracker instance persists
                                # TTS records were added to _node_records by _track_tts_cost()
                                # This incremental commit persists them to DB via UPSERT
                                await tracker.commit()

                            except TimeoutError:
                                logger.warning(
                                    "voice_parallel_task_timeout",
                                    run_id=run_id,
                                    timeout_seconds=settings.voice_parallel_timeout_seconds,
                                )
                                # Cancel and await for proper cleanup (asyncio best practice)
                                active_voice_task.cancel()
                                with suppress(asyncio.CancelledError):
                                    await active_voice_task
                                # Fall through to sync generation
                                # (voice_chunk_queue needs no reset: never
                                # read again on this path)
                                voice_parallel_task = None
                                chat_voice_drain_task = None

                            except Exception as parallel_error:
                                logger.warning(
                                    "voice_parallel_task_failed",
                                    run_id=run_id,
                                    error=str(parallel_error),
                                    error_type=type(parallel_error).__name__,
                                )
                                # Fall through to sync generation
                                # (voice_chunk_queue needs no reset: never
                                # read again on this path)
                                voice_parallel_task = None
                                chat_voice_drain_task = None

                        # === PATH 2: Sync fallback (chat mode or parallel failed) ===
                        # Skip if a chat-mode progressive streamer already
                        # synthesised the audio (its drain task above is the
                        # producer, voice_complete_emitted will be True).
                        if (
                            voice_parallel_task is None
                            and chat_voice_drain_task is None
                            and chunk_count == 0
                        ):
                            # Emit voice_comment_start for sync path
                            yield ChatStreamChunk(
                                type="voice_comment_start",
                                content="",
                                metadata={"run_id": run_id},
                            )
                            voice_start_emitted = True

                            # Determine voice generation mode
                            voice_context_registry = streaming_service.voice_context_registry
                            is_chat_mode = voice_context_registry is None

                            # === PATH 2A: Chat mode - Direct TTS (skip Voice LLM) ===
                            # When there's no registry (pure chat), TTS the response directly
                            # This is faster and more natural for conversational responses
                            if is_chat_mode:
                                voice_source = "direct_tts_chat_mode"

                                logger.info(
                                    "voice_direct_tts_chat_mode",
                                    run_id=run_id,
                                    response_length=len(response_content),
                                    max_sentences=settings.voice_chat_mode_max_sentences,
                                )

                                # Create voice service for direct TTS
                                voice_service = VoiceCommentService(
                                    tracker=tracker,
                                    run_id=run_id,
                                    lia_gender=voice_lia_gender,
                                    user_id=str(user_id),
                                )

                                # Direct TTS: skip voice LLM, synthesize response directly
                                async for audio_chunk in voice_service.stream_direct_tts(
                                    text=_sanitize_text_for_tts(response_content),
                                    user_language=user_language,
                                    max_sentences=settings.voice_chat_mode_max_sentences,
                                ):
                                    chunk_count += 1
                                    yield self._format_voice_audio_chunk(audio_chunk)

                                # Commit TTS tokens (context already exited)
                                await tracker.commit()

                            # === PATH 2B: Agent mode - Voice LLM + TTS ===
                            # When there's a registry (tools were used), generate commentary
                            else:
                                voice_source = "sync_fallback"

                                # Build voice context from registry or response
                                if voice_context_registry:
                                    try:
                                        voice_context = generate_text_summary_for_llm(
                                            voice_context_registry, user_language
                                        )
                                    except Exception as summary_error:
                                        logger.warning(
                                            "voice_context_summary_failed",
                                            run_id=run_id,
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
                                    run_id=run_id,
                                    voice_context_length=len(voice_context) if voice_context else 0,
                                    has_registry=voice_context_registry is not None,
                                )

                                # Create voice service for sync generation
                                # (uses voice_lia_gender extracted once before streaming loop)
                                voice_service = VoiceCommentService(
                                    tracker=tracker,
                                    run_id=run_id,
                                    lia_gender=voice_lia_gender,
                                    user_id=str(user_id),
                                )
                                current_dt = now_in_timezone(user_timezone).isoformat()

                                async for audio_chunk in voice_service.stream_voice_comment(
                                    context_summary=voice_context
                                    or _sanitize_and_truncate_for_tts(
                                        response_content, settings.voice_context_max_chars
                                    ),
                                    personality_instruction=personality_instruction or "",
                                    user_language=user_language,
                                    current_datetime=current_dt,
                                    user_query=user_message,
                                    user_timezone=user_timezone,
                                ):
                                    chunk_count += 1
                                    # DRY: use helper for audio chunk formatting
                                    yield self._format_voice_audio_chunk(audio_chunk)

                                # Commit TTS tokens (context already exited)
                                await tracker.commit()

                        # Signal voice complete (only if we emitted voice_start)
                        if voice_start_emitted and not voice_complete_emitted:
                            yield ChatStreamChunk(
                                type="voice_complete",
                                content="",
                                metadata={
                                    "run_id": run_id,
                                    "chunk_count": chunk_count,
                                    "source": voice_source,
                                },
                            )
                            voice_complete_emitted = True

                            logger.info(
                                "voice_comment_completed",
                                run_id=run_id,
                                chunk_count=chunk_count,
                                source=voice_source,
                            )

                    except Exception as voice_error:
                        logger.error(
                            "voice_comment_failed",
                            run_id=run_id,
                            error=str(voice_error),
                            error_type=type(voice_error).__name__,
                        )
                        yield ChatStreamChunk(
                            type="voice_error",
                            content="voice_synthesis_error",
                            metadata={"error_type": "voice_error"},
                        )

                # === Second TTS backfill pass (sync fallback path) ===
                # The first backfill (above, before cleanup_run_records) covers
                # the parallel-progressive path where voice synthesis happens
                # during streaming. The sync fallback (PATH 2A direct_tts /
                # PATH 2B voice_comment) runs only INSIDE the
                # voice_needs_finalization block above — i.e. AFTER the first
                # backfill and AFTER cleanup_run_records. The voice service's
                # ``await tracker.commit()`` re-populates _run_tts_records
                # for this run_id, so a second backfill picks them up here.
                # The done chunk's tts_snapshot_for_done is also refreshed
                # so the live frontend badge sees the data.
                if (
                    voice_needs_finalization
                    and archived_assistant_msg_id is not None
                    and tts_snapshot_for_done is None  # only if first pass found nothing
                ):
                    try:
                        late_tts_usage = temp_tracker.get_tts_usage_for_archive()
                        if late_tts_usage:
                            tts_snapshot_for_done = dict(late_tts_usage)
                            async with get_db_context() as late_tts_db:
                                await conv_service.update_message_tts(
                                    archived_assistant_msg_id,
                                    late_tts_usage,
                                    late_tts_db,
                                )
                                await late_tts_db.commit()
                            logger.debug(
                                "tts_backfill_done",
                                run_id=run_id,
                                message_id=str(archived_assistant_msg_id),
                                tts_provider=late_tts_usage.get("tts_provider"),
                                tts_characters=late_tts_usage.get("tts_characters"),
                                pass_="sync_fallback",
                            )
                    except Exception as late_tts_err:
                        logger.warning(
                            "tts_backfill_failed",
                            run_id=run_id,
                            message_id=str(archived_assistant_msg_id),
                            error=str(late_tts_err),
                            error_type=type(late_tts_err).__name__,
                            pass_="sync_fallback",
                        )

                # =============================================================
                # Debug Panel: Emit journal extraction results (post-background)
                # =============================================================
                # Journal extraction runs as fire-and-forget in response_node.
                # By this point, await_run_id_tasks has completed so extraction
                # results are available. Emit as debug_metrics_update for merge.
                if debug_panel_for_user:
                    try:
                        from src.domains.journals.extraction_service import (
                            pop_extraction_debug,
                        )

                        extraction_debug = pop_extraction_debug(run_id)
                        if extraction_debug is not None:
                            yield ChatStreamChunk(
                                type="debug_metrics_update",
                                content="",
                                metadata={"journal_extraction": extraction_debug},
                            )
                    except Exception as extr_dbg_err:
                        logger.debug(
                            "debug_metrics_journal_extraction_failed",
                            run_id=run_id,
                            error=str(extr_dbg_err),
                        )

                # Yield done chunk with complete aggregated token metadata
                # CRITICAL: Skip done chunk if HITL interrupt was emitted
                # hitl_interrupt_complete already sent tokens to frontend
                # Emitting done would cause double-counting in frontend totals
                if not streaming_service.hitl_interrupt_detected:
                    # Re-query aggregated summary to include TTS + background extraction costs
                    # Background tasks were already awaited above (await_run_id_tasks)
                    final_summary_dto = await temp_tracker.get_aggregated_summary_dto_from_db()
                    final_total_tokens = final_summary_dto.tokens_in + final_summary_dto.tokens_out

                    done_metadata: dict[str, Any] = {
                        "duration_ms": int(duration * 1000),
                        "total_tokens": final_total_tokens,
                        **final_summary_dto.to_metadata(),  # tokens_in/out/cache, cost_eur (includes TTS)
                    }
                    # Resolve includes the Route 3 fallback (activate_skill_tool
                    # called directly by the response LLM, no planner involved)
                    resolved_skill_name = streaming_service.resolve_activated_skill_name()
                    if resolved_skill_name:
                        done_metadata["skill_name"] = resolved_skill_name

                    # Context-usage pill (2026-05): expose the current token
                    # footprint of the conversation plus the dynamic compaction
                    # threshold so the frontend can render a small progress
                    # indicator in the chat header bar. Best-effort — a counting
                    # failure leaves done_metadata otherwise untouched.
                    context_usage = streaming_service.compute_context_usage()
                    if context_usage:
                        done_metadata.update(context_usage)

                    # Per-message TTS attribution for the live badge — sourced
                    # from the snapshot captured before cleanup_run_records()
                    # wiped the in-memory bucket. Mirror of STT: provider /
                    # model / characters surface the 🔊 badge under the
                    # assistant bubble immediately, without waiting for a
                    # page reload.
                    if tts_snapshot_for_done:
                        done_metadata["tts_provider"] = tts_snapshot_for_done.get("tts_provider")
                        done_metadata["tts_model"] = tts_snapshot_for_done.get("tts_model")
                        done_metadata["tts_characters"] = tts_snapshot_for_done.get(
                            "tts_characters"
                        )
                        if tts_snapshot_for_done.get("tts_cost_eur") is not None:
                            done_metadata["tts_cost_eur"] = float(
                                tts_snapshot_for_done["tts_cost_eur"]
                            )

                    # === IMAGE GENERATION: Include image URLs in done metadata ===
                    # Images are saved as Attachments by the tool. We pass the
                    # URLs in done metadata so the frontend renders them as
                    # dedicated cards (not inside markdown, avoiding proxy/hydration issues).
                    if getattr(settings, "image_generation_enabled", False):
                        from src.domains.image_generation.image_store import (
                            get_and_clear_pending_images,
                        )

                        pending_images = get_and_clear_pending_images(str(conversation_id))
                        if pending_images:
                            done_metadata["generated_images"] = [
                                {"url": img.url, "alt": img.alt_text} for img in pending_images
                            ]

                    # Browser screenshot card: reuse URL computed at archive time
                    if browser_screenshot_card_url:
                        done_metadata["browser_screenshot"] = {
                            "url": browser_screenshot_card_url,
                            "alt": "Browser screenshot",
                        }

                    # Psyche Engine: include psyche state summary in done metadata
                    if getattr(settings, "psyche_enabled", False) and user_psyche_enabled:
                        try:
                            from src.domains.psyche.service import pop_psyche_summary

                            psyche_summary = pop_psyche_summary(run_id)
                            if psyche_summary:
                                done_metadata["psyche_state"] = psyche_summary
                        except Exception as psyche_err:
                            logger.debug(
                                "psyche_done_metadata_failed",
                                run_id=run_id,
                                error=str(psyche_err),
                            )

                    yield ChatStreamChunk(
                        type="done",
                        content="",
                        metadata=done_metadata,
                    )

                # Cleanup user MCP tools ContextVar (evolution F2.1)
                # MUST be outside the if block — cleanup is required even on HITL interrupt
                cleanup_user_mcp_tools(_user_mcp_token)
                _user_mcp_token = None

                # Cleanup admin MCP disabled ContextVar (evolution F2.5)
                if _admin_mcp_token is not None:
                    admin_mcp_disabled_ctx.reset(_admin_mcp_token)
                # Cleanup disabled skills ContextVar
                if _active_skills_token is not None:
                    active_skills_ctx.reset(_active_skills_token)
                # Cleanup per-request tool manifests ContextVar
                if _manifests_token is not None:
                    request_tool_manifests_ctx.reset(_manifests_token)

                # Voice services own a persistent httpx client (TTS) that
                # must be closed deterministically — without this, the
                # keep-alive pool leaks until process restart. Cleanup is
                # idempotent: if voice was never invoked the helpers are
                # no-ops and ``service.close()`` short-circuits on the
                # already-released httpx client.
                await self._cleanup_chat_voice_pipeline(
                    chat_voice_streamer,
                    chat_voice_drain_task,
                    run_id,
                    chat_voice_service,
                )
                # Parallel-mode (agent) voice service is closed via the
                # task that owns it — but we close defensively here too in
                # case the task already finished with an exception that
                # bypassed the local cleanup.
                if voice_service_parallel is not None:
                    try:
                        await voice_service_parallel.close()
                    except Exception as voice_close_err:  # noqa: BLE001
                        logger.warning(
                            "voice_service_parallel_close_failed",
                            run_id=run_id,
                            error=str(voice_close_err),
                        )

                # Connector clients cached by ToolDependencies hold pooled
                # httpx clients — close them deterministically at end of run
                # (same rationale as the voice-service cleanup above).
                await tool_deps.aclose()

            except Exception as e:
                # Cleanup user MCP tools ContextVar on error (evolution F2.1)
                cleanup_user_mcp_tools(_user_mcp_token)
                # Cleanup admin MCP disabled ContextVar on error (evolution F2.5)
                if _admin_mcp_token is not None:
                    admin_mcp_disabled_ctx.reset(_admin_mcp_token)
                # Cleanup disabled skills ContextVar on error
                if _active_skills_token is not None:
                    active_skills_ctx.reset(_active_skills_token)
                # Cleanup per-request tool manifests ContextVar on error
                if _manifests_token is not None:
                    request_tool_manifests_ctx.reset(_manifests_token)

                # Voice services owned by this generator must be torn down
                # so their persistent httpx clients aren't leaked when the
                # exception propagates upwards.
                # best-effort
                with suppress(Exception):
                    await self._cleanup_chat_voice_pipeline(
                        chat_voice_streamer,
                        chat_voice_drain_task,
                        run_id,
                        chat_voice_service,
                    )
                    if voice_service_parallel is not None:
                        await voice_service_parallel.close()
                    # Close connector clients cached by ToolDependencies
                    # (aclose is itself best-effort per client).
                    await tool_deps.aclose()

                logger.error(
                    "new_service_architecture_error",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                # User-friendly error message (never expose raw API errors)
                from src.domains.agents.api.error_messages import SSEErrorMessages

                error_message = SSEErrorMessages.stream_error(
                    e, language=user_language  # type: ignore[arg-type]
                )
                yield ChatStreamChunk(
                    type="error",
                    content=error_message,
                    metadata={
                        FIELD_ERROR_TYPE: "stream_error",
                    },
                )
                raise
