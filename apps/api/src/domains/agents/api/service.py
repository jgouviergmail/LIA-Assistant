"""
Agents domain service.
Orchestrates graph execution, streaming, and session management.

Phase 3.3: Service-oriented architecture with dependency injection.
Uses autonomous services: OrchestrationService, StreamingService,
HITLOrchestrator, ConversationOrchestrator.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from langgraph.errors import GraphInterrupt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.field_names import FIELD_ERROR_TYPE, FIELD_RUN_ID
from src.domains.agents.api.mixins import GraphManagementMixin, StreamingMixin
from src.domains.agents.api.schemas import BrowserContext, ChatStreamChunk
from src.domains.agents.dependencies import ToolDependencies
from src.domains.agents.utils import generate_run_id
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    pass

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

    Uses HITLOrchestrator service for HITL flow management (classification, validation, resumption).
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

    async def _stream_voice_chunks_to_queue(
        self,
        voice_service: Any,
        context_summary: str,
        personality_instruction: str,
        user_language: str,
        current_datetime: str,
        user_query: str,
        chunk_queue: asyncio.Queue,
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
            current_datetime: ISO datetime string
            user_query: Original user message
            chunk_queue: asyncio.Queue to put chunks into for progressive emission

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
            ):
                await chunk_queue.put(audio_chunk)
        finally:
            # Sentinel to signal completion
            await chunk_queue.put(None)

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

    async def stream_chat_response(
        self,
        user_message: str,
        user_id: uuid.UUID,
        session_id: str,
        user_timezone: str = "Europe/Paris",
        user_language: str = "fr",
        original_run_id: str | None = None,
        browser_context: BrowserContext | None = None,
        user_memory_enabled: bool = True,
        user_journals_enabled: bool = False,
        auto_approve_plan: bool = False,
        attachment_ids: list[uuid.UUID] | None = None,
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
            original_run_id: Optional run_id from HITL resumption (for token aggregation).
            browser_context: Browser context (geolocation, etc.) sent automatically by frontend.
            user_memory_enabled: User's preference for long-term memory (default: True).
            user_journals_enabled: User's preference for personal journals (default: False).
            auto_approve_plan: If True, bypass HITL plan approval gate (for scheduled actions).

        Yields:
            ChatStreamChunk: SSE chunks (router_decision, token, done, error).

        Example:
            >>> async for chunk in service.stream_chat_response(
            ...     "Hello", user_id, session_id,
            ...     user_timezone="America/New_York", user_language="en"
            ... ):
            >>>     print(chunk.type, chunk.content)
        """
        # === PHASE 3.3 - Service Architecture (Migration Complete Day 7) ===
        # Uses: OrchestrationService, StreamingService, ConversationOrchestrator, HITLOrchestrator
        async for chunk in self._stream_with_new_services(
            user_message,
            user_id,
            session_id,
            user_timezone,
            user_language,
            original_run_id,
            browser_context,
            user_memory_enabled,
            user_journals_enabled,
            auto_approve_plan,
            attachment_ids,
        ):
            yield chunk

    async def _stream_with_new_services(
        self,
        user_message: str,
        user_id: uuid.UUID,
        session_id: str,
        user_timezone: str,
        user_language: str,
        original_run_id: str | None = None,
        browser_context: BrowserContext | None = None,
        user_memory_enabled: bool = True,
        user_journals_enabled: bool = False,
        auto_approve_plan: bool = False,
        attachment_ids: list[uuid.UUID] | None = None,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Stream agent response using service-oriented architecture (Phase 3.3).

        Uses:
        - ConversationOrchestrator: Conversation lifecycle and setup
        - OrchestrationService: State loading + graph execution
        - StreamingService: SSE formatting and HITL detection
        - HITLOrchestrator: HITL flow management and classification

        Args:
            original_run_id: Optional run_id from HITL resumption for token aggregation.
                            When provided, reuses existing run_id to aggregate tokens
                            across HITL interrupt and resumption (critical for billing).
            browser_context: Browser context (geolocation, etc.) sent automatically by frontend.
                            Propagated to RunnableConfig.configurable for tools to access.
            user_memory_enabled: User's preference for long-term memory (extraction + injection).
            user_journals_enabled: User's preference for personal journals (extraction + injection).
            auto_approve_plan: If True, inject plan_approved=True into state to bypass HITL gate.
        """
        # CRITICAL: Reuse original_run_id for HITL token aggregation
        run_id = original_run_id or generate_run_id()
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

            # Warmup: ALWAYS preload contacts cache if Google Contacts is active
            # CRITICAL: The warmup MUST complete BEFORE the graph starts executing
            # Otherwise, first search will hit empty cache and return 0 results
            # This is a BLOCKING operation - we wait for it to complete
            logger.info(
                "warmup_starting",
                user_id=str(user_id),
                conversation_id=str(conversation_id),
            )
            await self._warmup_contacts_cache_if_active(user_id, tool_deps)
            logger.info(
                "warmup_completed",
                user_id=str(user_id),
                conversation_id=str(conversation_id),
            )

            logger.info(
                "conversation_setup_complete",
                run_id=run_id,
                conversation_id=str(conversation_id),
                oauth_scopes_count=len(oauth_scopes),
            )

            # Import MCP tools setup before try block to ensure cleanup is always accessible
            from src.core.context import active_skills_ctx, admin_mcp_disabled_ctx
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
            try:
                async with tracker:
                    # === Per-user MCP tools setup (evolution F2.1) ===
                    _user_mcp_token = await setup_user_mcp_tools(user_id, db)

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
                    voice_parallel_task: asyncio.Task | None = None
                    voice_chunk_queue: asyncio.Queue | None = None  # Queue for progressive emission
                    voice_start_emitted = False  # Track if voice_comment_start was emitted
                    voice_complete_emitted = False  # Track if voice_complete was emitted
                    voice_chunk_count = 0  # Count emitted chunks for voice_complete metadata

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
                    )

                    # === StreamingService handles everything: SSE formatting + HITL ===
                    try:
                        async for (
                            sse_chunk,
                            content_fragment,
                        ) in streaming_service.stream_sse_chunks(
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
                            ),
                            conversation_id=conversation_id,
                            run_id=run_id,
                        ):
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

                            # Track token count and first token time
                            if sse_chunk.type == "token":
                                if first_token_time is None:
                                    first_token_time = time.time()
                                token_count += 1

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
                                and streaming_service.voice_context_registry is not None
                                and user_obj is not None
                                and user_obj.voice_enabled
                            ):
                                # Import voice dependencies (lazy)
                                from datetime import datetime as dt_voice_parallel

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
                                            current_datetime=dt_voice_parallel.now().isoformat(),
                                            user_query=user_message,
                                            chunk_queue=voice_chunk_queue,
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

                    # === Build attachment metadata for archiving (evolution F4) ===
                    _attachment_meta: dict = {}
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

                    # === Archive messages BEFORE exiting tracker context ===
                    # Messages must be persisted to DB for frontend to load on page refresh
                    #
                    # HITL Archiving Logic:
                    # 1. HITL resumption (user responds "oui"/"non"):
                    #    Archive with {run_id, hitl_response: True, decision_type}
                    # 2. HITL interrupt (graph paused for user approval):
                    #    Archive with {run_id, hitl_interrupted: True}
                    # 3. Regular message (no HITL):
                    #    Archive with {run_id}

                    # Track number of messages archived for accurate stats
                    messages_archived = 0

                    async with get_db_context() as archive_db:
                        # Determine archiving mode based on HITL state
                        if is_hitl_resumption:
                            # Case 1: HITL resumption - user responded to HITL question
                            interrupt_resume_data = state.get("_interrupt_resume_data", {})
                            decision_type = interrupt_resume_data.get("decision", "UNKNOWN")

                            await conv_service.archive_message(
                                conversation_id,
                                "user",
                                user_message,
                                {
                                    FIELD_RUN_ID: run_id,
                                    "hitl_response": True,
                                    "decision_type": decision_type,
                                    **_attachment_meta,
                                },
                                archive_db,
                            )
                            messages_archived += 1

                            logger.info(
                                "hitl_user_response_archived",
                                run_id=run_id,
                                conversation_id=str(conversation_id),
                                decision_type=decision_type,
                                user_message_preview=user_message[:50] if user_message else "",
                            )

                        elif streaming_service.hitl_interrupt_detected:
                            # Case 2: HITL interrupt - graph paused, awaiting user response
                            await conv_service.archive_message(
                                conversation_id,
                                "user",
                                user_message,
                                {
                                    FIELD_RUN_ID: run_id,
                                    "hitl_interrupted": True,
                                    **_attachment_meta,
                                },
                                archive_db,
                            )
                            messages_archived += 1

                            logger.info(
                                "hitl_interrupted_message_archived",
                                run_id=run_id,
                                conversation_id=str(conversation_id),
                                user_message_preview=user_message[:50] if user_message else "",
                            )

                        else:
                            # Case 3: Regular message - no HITL involved
                            await conv_service.archive_message(
                                conversation_id,
                                "user",
                                user_message,
                                {FIELD_RUN_ID: run_id, **_attachment_meta},
                                archive_db,
                            )
                            messages_archived += 1

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

                            await conv_service.archive_message(
                                conversation_id,
                                "assistant",
                                response_content,
                                assistant_metadata,
                                archive_db,
                            )
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
                    user_obj is not None
                    and user_obj.voice_enabled
                    and response_content.strip()
                    and not streaming_service.hitl_interrupt_detected
                    and not voice_complete_emitted  # Skip if already completed during streaming
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
                        from datetime import datetime as dt_voice

                        from src.domains.agents.formatters.text_summary import (
                            generate_text_summary_for_llm,
                        )
                        from src.domains.voice.service import VoiceCommentService

                        chunk_count = voice_chunk_count  # Continue from progressive count
                        voice_source = "unknown"

                        # === PATH 1: Drain remaining chunks from queue if parallel task active ===
                        if voice_chunk_queue is not None and voice_parallel_task is not None:
                            try:
                                # Wait for parallel task with configurable timeout
                                # This ensures all chunks are in the queue
                                await asyncio.wait_for(
                                    voice_parallel_task,
                                    timeout=settings.voice_parallel_timeout_seconds,
                                )
                                voice_source = "parallel_drain"

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
                                voice_parallel_task.cancel()
                                try:
                                    await voice_parallel_task
                                except asyncio.CancelledError:
                                    pass
                                # Fall through to sync generation
                                voice_parallel_task = None
                                voice_chunk_queue = None

                            except Exception as parallel_error:
                                logger.warning(
                                    "voice_parallel_task_failed",
                                    run_id=run_id,
                                    error=str(parallel_error),
                                    error_type=type(parallel_error).__name__,
                                )
                                # Fall through to sync generation
                                voice_parallel_task = None
                                voice_chunk_queue = None

                        # === PATH 2: Sync fallback (chat mode or parallel failed) ===
                        if voice_parallel_task is None and chunk_count == 0:
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
                                )

                                # Direct TTS: skip voice LLM, synthesize response directly
                                async for audio_chunk in voice_service.stream_direct_tts(
                                    text=response_content,
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
                                        voice_context = response_content[
                                            : settings.voice_context_max_chars
                                        ]
                                else:
                                    # Fallback: use response content (chat mode with direct_tts disabled)
                                    voice_context = response_content[
                                        : settings.voice_context_max_chars
                                    ]

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
                                )
                                current_dt = dt_voice.now().isoformat()

                                async for audio_chunk in voice_service.stream_voice_comment(
                                    context_summary=voice_context
                                    or response_content[: settings.voice_context_max_chars],
                                    personality_instruction=personality_instruction or "",
                                    user_language=user_language,
                                    current_datetime=current_dt,
                                    user_query=user_message,
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
                            content=str(voice_error),
                            metadata={"error_type": type(voice_error).__name__},
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
                    if streaming_service.activated_skill_name:
                        done_metadata["skill_name"] = streaming_service.activated_skill_name

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

            except Exception as e:
                # Cleanup user MCP tools ContextVar on error (evolution F2.1)
                cleanup_user_mcp_tools(_user_mcp_token)
                # Cleanup admin MCP disabled ContextVar on error (evolution F2.5)
                if _admin_mcp_token is not None:
                    admin_mcp_disabled_ctx.reset(_admin_mcp_token)
                # Cleanup disabled skills ContextVar on error
                if _active_skills_token is not None:
                    active_skills_ctx.reset(_active_skills_token)

                logger.error(
                    "new_service_architecture_error",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                yield ChatStreamChunk(
                    type="error",
                    content=f"Error in new service architecture: {str(e)}",
                    metadata={
                        FIELD_ERROR_TYPE: type(e).__name__,
                    },
                )
                raise
