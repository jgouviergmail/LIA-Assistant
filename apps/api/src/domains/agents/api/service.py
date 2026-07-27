"""
Agents domain service.
Orchestrates graph execution, streaming, and session management.

Phase 3.3: Service-oriented architecture with dependency injection.
Uses autonomous services: OrchestrationService, StreamingService,
ConversationOrchestrator.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from langgraph.errors import GraphInterrupt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    RESPONSE_FEEDBACK_JOURNAL_IDS_MAX,
    USAGE_LIMIT_EXCEEDED_ERROR_CODE,
)
from src.core.field_names import (
    FIELD_ERROR_TYPE,
    FIELD_FOLLOWUP_SUGGESTIONS,
    FIELD_INJECTED_JOURNAL_IDS,
    FIELD_RUN_ID,
)
from src.core.i18n import normalize_language
from src.domains.agents.api.attachments_injection import inject_attachments_into_state
from src.domains.agents.api.error_messages import SSEErrorMessages
from src.domains.agents.api.hitl_pending import extract_decision_type, hitl_stale_chunks
from src.domains.agents.api.mixins import GraphManagementMixin, StreamingMixin
from src.domains.agents.api.schemas import BrowserContext, ChatStreamChunk
from src.domains.agents.data_registry.message_widgets import with_persisted_widgets
from src.domains.agents.dependencies import ToolDependencies
from src.domains.agents.services.orchestration.approval_decision import (
    HitlDecisionStaleError,
)
from src.domains.agents.services.streaming.followup_metadata import (
    pop_followups,
    with_followup_suggestions,
)
from src.domains.agents.services.streaming.trace_capture import with_persisted_trace
from src.domains.agents.services.streaming.voice_coordinator import (
    VoiceStreamContext,
    VoiceStreamCoordinator,
)
from src.domains.agents.services.streaming.voice_stream_helpers import ListenerProbe
from src.domains.agents.utils import generate_run_id
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.conversations.service import ConversationService

logger = get_logger(__name__)

# MAX_HITL_ACTIONS_PER_REQUEST defined in src.core.constants
# Phase 3.3: Centralized constant management


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
        hitl_decision: dict[str, Any] | None = None,
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
            from src.domains.users.user_location_service import (
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
            hitl_decision=hitl_decision,
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
        hitl_decision: dict[str, Any] | None = None,
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
                user_id, session_id, run_id, db, language=user_language
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
            # Voice coordination initialised here (instead of inside
            # ``async with tracker``) so the outer ``except`` cleanup branch
            # can reference it even when the exception fires before the inner
            # block's declarations. Owns the full voice/TTS state machine —
            # progressive chat TTS, parallel voice, finalization paths and
            # TTS backfills (B2 extraction #1, ADR-122).
            voice_coordinator = VoiceStreamCoordinator(
                VoiceStreamContext(
                    run_id=run_id,
                    user_id=str(user_id),
                    user_language=user_language,
                    user_timezone=user_timezone,
                    user_message=user_message,
                    # Extract LIA gender once for all voice paths (DRY)
                    lia_gender=(
                        browser_context.lia_gender
                        if browser_context and browser_context.lia_gender
                        else "female"
                    ),
                    personality_instruction=personality_instruction,
                    user_obj=user_obj,
                    has_listeners=has_listeners,
                    start_time=start_time,
                ),
                tracker=tracker,
            )
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
                    try:
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
                            hitl_decision=hitl_decision,
                        )
                    except HitlDecisionStaleError as stale_err:
                        # Lot 1 option B, fail-closed: a one-click decision that
                        # no longer matches the pending interrupt is NEVER
                        # processed as a new turn — typed error + done so the
                        # frontend card flips to its "expired" state.
                        logger.warning(
                            "hitl_decision_stale_rejected",
                            run_id=run_id,
                            conversation_id=str(conversation_id),
                            reason=str(stale_err),
                        )
                        for chunk in hitl_stale_chunks(user_language):
                            yield chunk
                        return

                    # === ATTACHMENT INJECTION (evolution F4) ===
                    # Load attachments and inject metadata + hint into state
                    # AFTER load_or_create_state, BEFORE graph execution
                    if attachment_ids and getattr(settings, "attachments_enabled", False):
                        await inject_attachments_into_state(
                            state=state,
                            attachment_ids=attachment_ids,
                            user_id=user_id,
                            user_language=user_language,
                            run_id=run_id,
                            db=db,
                        )

                    # === AUTO-APPROVE: Bypass HITL plan approval gate ===
                    # Used by scheduled actions executor to skip human approval
                    if auto_approve_plan:
                        state["plan_approved"] = True
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

                    # Voice/TTS state (progressive chat streamer, parallel
                    # voice task, emission flags) is owned by
                    # ``voice_coordinator`` — created at the outer try/except
                    # level so the cleanup branches can always reference it.

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

                                # Chat-mode progressive TTS: on the first
                                # ``conversation`` decision the coordinator
                                # spins up a sentence streamer so first audio
                                # lands within ~1 s of streaming.
                                await voice_coordinator.on_router_decision(intention_label)

                            # Track token count and first token time
                            if sse_chunk.type == "token":
                                if first_token_time is None:
                                    first_token_time = time.time()
                                token_count += 1
                                # Feed the chat-mode streamer with each new
                                # response token so sentences are extracted
                                # and TTS-dispatched as they complete.
                                voice_coordinator.feed_token(content_fragment)

                            # === PARALLEL VOICE: Start when registry becomes available ===
                            # Registry is populated after task_orchestrator completes tools
                            # We can start voice generation before response_node finishes
                            await voice_coordinator.maybe_start_parallel(
                                streaming_service.voice_context_registry, sse_chunk.type
                            )

                            # Yield SSE chunk to client
                            yield sse_chunk

                            # === PROGRESSIVE VOICE EMISSION: Emit chunks as they become available ===
                            # Non-blocking queue drain — audio chunks are
                            # emitted PROGRESSIVELY during streaming.
                            for voice_chunk in voice_coordinator.drain_progressive_nowait():
                                yield voice_chunk

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
                        await voice_coordinator.cleanup_chat_pipeline()

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

                    # UXR Lot 4 (A2): pop this run's follow-up chips ONCE —
                    # consumed by both the archived metadata and the done
                    # chunk below. Empty when the initiative did not emit any.
                    followup_suggestions = pop_followups(run_id)

                    # NOTE (ADR-117): attachment metadata and STT kwargs are now
                    # built BEFORE graph execution (archive-first block above).

                    # Signal end-of-input to the chat-mode sentence streamer
                    # so its trailing buffer (last sentence — likely without
                    # a punctuation terminator) is flushed and the drain task
                    # can finalise once every TTS call resolves.
                    voice_coordinator.close_input()

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
                    # Declared at the level it is READ from (the done-metadata block
                    # below), not inside the archive branch that computes it: an empty
                    # assistant response skips that branch entirely, and reading an
                    # unbound local here would raise UnboundLocalError right before the
                    # `done` chunk — killing the SSE stream at its very last step.
                    browser_screenshot_card_url: str | None = None

                    async with get_db_context() as archive_db:
                        _interrupt_resume_data = state.get("_interrupt_resume_data", {})
                        _decision_type = extract_decision_type(_interrupt_resume_data)
                        await self._patch_user_message_hitl_flags(
                            conv_service=conv_service,
                            db=archive_db,
                            archived_user_msg_id=archived_user_msg_id,
                            is_hitl_resumption=is_hitl_resumption,
                            hitl_interrupt_detected=streaming_service.hitl_interrupt_detected,
                            decision_type=_decision_type,
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
                            assistant_metadata: dict[str, Any] = {
                                FIELD_RUN_ID: run_id,
                                "intention": intention_label,
                            }
                            if is_hitl_resumption:
                                assistant_metadata["hitl_approved"] = True

                            # QW-5 (ADR-138): archive the IDs of the journal
                            # entries injected into this turn (IDs only — no
                            # content) so a later 👍/👎 can feed exactly those
                            # entries' evidence/contradiction counters.
                            _injected_journal_ids = state.get("injected_journal_ids")
                            if _injected_journal_ids:
                                assistant_metadata[FIELD_INJECTED_JOURNAL_IDS] = [
                                    str(_jid) for _jid in _injected_journal_ids
                                ][:RESPONSE_FEEDBACK_JOURNAL_IDS_MAX]

                            # Persist generated image URLs in message metadata
                            # so they survive page reload (frontend reads them back)
                            if getattr(settings, "image_generation_enabled", False):
                                from src.domains.image_generation.image_store import (
                                    peek_pending_images,
                                    to_wire_metadata,
                                )

                                peeked = peek_pending_images(str(conversation_id))
                                if peeked:
                                    # Same serializer as the done chunk below: the
                                    # reloaded card must be the live one, purge
                                    # deadline (N2) included.
                                    assistant_metadata["generated_images"] = to_wire_metadata(
                                        peeked
                                    )

                            # Persist last browser screenshot as Attachment for card display
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

                            # Persist interactive-widget payloads with the message
                            # so they survive a page reload. Without this the
                            # payload lived ONLY in the browser's React state,
                            # fed by the live SSE stream: any session that had
                            # not received it (another device, an F5, a
                            # conversation reopened later) resolved the sentinel
                            # to nothing and rendered an error box. Branch-free
                            # by design — see data_registry/message_widgets.py.
                            assistant_metadata = with_persisted_widgets(
                                assistant_metadata,
                                streaming_service.persistable_widgets,
                                run_id=run_id,
                            )

                            # Persist the ⚙ execution trace with the message so
                            # it survives a page reload (ADR-133 V2). i18n keys
                            # only — labels are re-resolved client-side. Branch-
                            # free by design — see streaming/trace_capture.py.
                            assistant_metadata = with_persisted_trace(
                                assistant_metadata,
                                streaming_service.trace_capture.snapshot(),
                                duration_ms=int(duration * 1000),
                                run_id=run_id,
                            )

                            # UXR Lot 4 (A2): persist the follow-up chips so
                            # they survive a reload while the answer stays the
                            # latest. Branch-free enricher (new-dict).
                            assistant_metadata = with_followup_suggestions(
                                assistant_metadata,
                                followup_suggestions,
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
                # The voice synthesis (parallel progressive) has had its calls
                # recorded by tracker.record_tts_call(); this UPDATE MUST run
                # before cleanup_run_records() below — the cleanup wipes the
                # module-level _run_tts_records bucket. The captured snapshot
                # survives the cleanup and feeds the done chunk metadata so
                # the live frontend badge renders without a page reload.
                await voice_coordinator.backfill_tts_pass1(
                    temp_tracker, conv_service, archived_assistant_msg_id
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

                        # Clear pending_hitl since graph completed without
                        # re-interrupting. The store invalidates the in-memory
                        # detection cache itself (Lot 1 Phase 0) — no router
                        # hook needed anymore.
                        await hitl_store.clear_interrupt(thread_id=str(conversation_id))

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
                #           2) PATH 1 — drain remaining queue chunks at end of stream
                #           3) PATH 2 — sync fallback if no parallel task
                #              (2A direct TTS chat mode / 2B Voice-LLM agent mode)
                # The coordinator picks the path and yields the voice chunks.
                async for voice_chunk in voice_coordinator.finalize(
                    response_content=response_content,
                    hitl_interrupted=streaming_service.hitl_interrupt_detected,
                    voice_context_registry=streaming_service.voice_context_registry,
                ):
                    yield voice_chunk

                # === Second TTS backfill pass (sync fallback path) ===
                # The first backfill (above, before cleanup_run_records) covers
                # the parallel-progressive path. The sync fallback (PATH 2A /
                # PATH 2B) runs only inside finalize() — i.e. AFTER the first
                # backfill and AFTER cleanup_run_records; the voice service's
                # ``tracker.commit()`` re-populated _run_tts_records, so this
                # second pass picks them up (skipped if pass 1 found data).
                await voice_coordinator.backfill_tts_pass2(
                    temp_tracker, conv_service, archived_assistant_msg_id
                )

                # =============================================================
                # Debug Panel: Emit background-extraction results (post-await)
                # =============================================================
                # The post-response extractions (journals, open loops) run
                # fire-and-forget; await_run_id_tasks has completed here so
                # their pop-once debug caches are populated. One merge chunk
                # per populated family (see streaming/extraction_debug.py).
                if debug_panel_for_user:
                    try:
                        from src.domains.agents.services.streaming.extraction_debug import (
                            pop_background_extraction_debug,
                        )

                        for dbg_key, dbg_payload in pop_background_extraction_debug(run_id):
                            yield ChatStreamChunk(
                                type="debug_metrics_update",
                                content="",
                                metadata={dbg_key: dbg_payload},
                            )
                    except Exception as extr_dbg_err:
                        logger.debug(
                            "debug_metrics_extraction_emit_failed",
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
                    # QW-5 (ADR-138): DB id of the archived assistant row so the
                    # live bubble can target the feedback endpoint immediately
                    # (history rows already carry their DB id).
                    if archived_assistant_msg_id is not None:
                        done_metadata["archived_message_id"] = str(archived_assistant_msg_id)
                    # UXR Lot 4 (A2): follow-up chips of this run (ADR-117:
                    # mirrored in BOTH frontend DoneMetadata types).
                    if followup_suggestions:
                        done_metadata[FIELD_FOLLOWUP_SUGGESTIONS] = followup_suggestions
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
                    tts_snapshot_for_done = voice_coordinator.tts_snapshot_for_done
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
                            to_wire_metadata,
                        )

                        pending_images = get_and_clear_pending_images(str(conversation_id))
                        if pending_images:
                            done_metadata["generated_images"] = to_wire_metadata(pending_images)

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
                # idempotent: no-op when voice was never invoked.
                await voice_coordinator.cleanup()

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
                    await voice_coordinator.cleanup(log_close_failure=False)
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
                error_message = SSEErrorMessages.stream_error(
                    e, language=normalize_language(user_language)
                )
                yield ChatStreamChunk(
                    type="error",
                    content=error_message,
                    metadata={
                        FIELD_ERROR_TYPE: "stream_error",
                    },
                )
                raise
