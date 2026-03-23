"""
Service layer for chat domain - token tracking and statistics.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import UUID

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.context import current_tracker
from src.core.field_names import (
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_COST_EUR,
    FIELD_GOOGLE_API_REQUESTS,
    FIELD_MESSAGE_COUNT,
    FIELD_MODEL_NAME,
    FIELD_NODE_NAME,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
)
from src.domains.chat.models import (
    UserStatistics,
)
from src.domains.chat.schemas import TokenSummaryDTO, UserStatisticsResponse
from src.infrastructure.database import get_db_context

logger = structlog.get_logger(__name__)


class TokenUsageRecord(NamedTuple):
    """
    In-memory record of token usage for a single LLM node call.

    Used by TrackingContext to aggregate tokens before DB persistence.
    """

    node_name: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    cost_eur: float
    usd_to_eur_rate: Decimal
    # Duration tracking for debug panel (v3.2)
    duration_ms: float = 0.0
    # Call type for debug panel pipeline reconciliation (v3.3)
    call_type: str = "chat"  # "chat" | "embedding"
    # Monotonic sequence counter for chronological ordering (v3.3)
    sequence: int = 0


class GoogleApiRecord(NamedTuple):
    """
    In-memory record of a Google API call (immutable).

    Used by TrackingContext to aggregate Google API usage before DB persistence.
    Mirrors TokenUsageRecord pattern for consistency.
    """

    api_name: str
    endpoint: str
    cost_usd: Decimal
    cost_eur: Decimal
    usd_to_eur_rate: Decimal
    cached: bool = False


class TrackingContext:
    """
    Context manager for tracking tokens and messages per LangGraph execution.

    Modern approach (2025): Tokens are extracted from AIMessage.usage_metadata
    after graph execution completes. TrackingContext serves as a DTO to aggregate
    and persist token usage to the database.

    Usage:
        async with TrackingContext(run_id, user_id, session_id, conversation_id) as tracker:
            # LangGraph execution
            # After execution, extract usage_metadata from AIMessage(s)
            # Call tracker.record_node_tokens() for each LLM call
            # Auto-commit to database on context exit

    Attributes:
        run_id: LangGraph run identifier (unique per message)
        user_id: User UUID
        session_id: Chat session identifier
    """

    def __init__(
        self,
        run_id: str,
        user_id: UUID,
        session_id: str,
        conversation_id: UUID | None,
        auto_commit: bool = True,
        db: AsyncSession | None = None,
    ) -> None:
        """
        Initialize TrackingContext.

        Args:
            run_id: LangGraph run identifier
            user_id: User UUID
            session_id: Chat session identifier
            conversation_id: Conversation UUID for linking token summaries
            auto_commit: Whether to auto-commit to database on exit (default: True)
                        Set to False when this tracker is managed by a parent context.
            db: Optional external database session for transaction composition.
                When provided, uses this session instead of creating a new one
                and delegates commit responsibility to the caller.
        """
        self.run_id = run_id
        self.user_id = user_id
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.auto_commit = auto_commit
        self._external_db = db

        # In-memory aggregation (avoids N database queries)
        self._node_records: list[TokenUsageRecord] = []
        self._message_count = 0
        # Track total committed records for incremental commit support
        # Allows multiple commits (e.g., LLM tokens first, then TTS tokens after voice generation)
        self._total_committed_records = 0
        self._message_count_committed = False  # Track if message count was already persisted

        # Google API tracking (Places, Routes, Geocoding, Static Maps)
        self._google_api_records: list[GoogleApiRecord] = []

        # Debug Panel: Keep a copy of records after commit for debug metrics
        # This allows get_llm_calls_breakdown() to return data even after commit()
        # clears _node_records (timing issue: commit happens before debug metrics are built)
        self._committed_records_copy: list[TokenUsageRecord] = []
        self._committed_google_api_copy: list[GoogleApiRecord] = []

        # v3.3: Monotonic counter for chronological ordering of LLM calls in debug panel
        self._sequence_counter: int = 0

        # Phase 5.2B: Thread safety for parallel execution
        # Protect _node_records mutations when multiple workers call record_node_tokens() concurrently
        import asyncio

        self._lock = asyncio.Lock()

        # ContextVar token for cleanup in __aexit__
        self._context_token: Any = None

        logger.debug(
            "tracking_context_initialized",
            run_id=run_id,
            user_id=str(user_id),
            session_id=session_id,
            conversation_id=str(conversation_id),
            auto_commit=auto_commit,
        )

    async def __aenter__(self) -> "TrackingContext":
        """Enter context manager - set ContextVar for implicit access from Google API clients."""
        # Set context var for implicit access from anywhere in the async call stack
        # This enables Google API clients to record usage without explicit tracker parameter
        self._context_token = current_tracker.set(self)

        logger.debug(
            "tracking_context_entered",
            run_id=self.run_id,
        )
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
    ) -> None:
        """Exit context manager - persist to database if auto_commit is True."""
        # Clear context var (must be done regardless of exception)
        if self._context_token is not None:
            current_tracker.reset(self._context_token)
            self._context_token = None

        # Check if there are NEW records to commit (supports incremental commits)
        # Records are cleared after each commit, so _node_records only contains pending ones
        pending_records = len(self._node_records)
        if pending_records == 0:
            logger.debug(
                "tracking_context_no_pending_records",
                run_id=self.run_id,
                total_committed=self._total_committed_records,
                message_count=self._message_count,
            )
            return

        # Only persist if auto_commit is enabled, no exception, and we have pending data
        if self.auto_commit and exc_type is None:
            try:
                await self._persist_to_database()
                logger.info(
                    "tracking_context_persisted",
                    run_id=self.run_id,
                    node_records_count=pending_records,
                    total_committed=self._total_committed_records,
                    message_count=self._message_count,
                )
            except Exception as e:
                logger.error(
                    "tracking_context_persistence_failed",
                    run_id=self.run_id,
                    error=str(e),
                    exc_info=True,
                )
                # Don't re-raise - tracking failure shouldn't break chat
        elif not self.auto_commit:
            logger.debug(
                "tracking_context_skipped_auto_commit",
                run_id=self.run_id,
                node_records_count=len(self._node_records),
                message_count=self._message_count,
            )

        logger.debug(
            "tracking_context_exited",
            run_id=self.run_id,
        )

    async def record_node_tokens(
        self,
        node_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
        cost_usd: float | None = None,
        cost_eur: float | None = None,
        usd_to_eur_rate: Decimal | None = None,
        duration_ms: float = 0.0,
        call_type: str = "chat",
    ) -> None:
        """
        Record token usage for a single LLM node call.

        Unified method for recording token usage with automatic cost calculation
        if costs are not provided. Called by both legacy code (with costs) and
        modern TokenTrackingCallback (without costs - calculates automatically).

        Args:
            node_name: LangGraph node name (router, response, contacts_agent, etc.)
            model_name: LLM model used (gpt-4.1-mini, gpt-4-turbo, etc.)
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            cached_tokens: Number of cached input tokens
            cost_usd: Estimated cost in USD (auto-calculated if None)
            cost_eur: Estimated cost in EUR (auto-calculated if None)
            usd_to_eur_rate: Exchange rate used (auto-fetched if None)
            duration_ms: LLM call duration in milliseconds (v3.2 debug panel)
            call_type: Type of LLM call ("chat" for completions, "embedding" for
                vector embeddings). Used by debug panel to distinguish call categories.
        """
        # Auto-calculate costs if not provided (modern callback path)
        # Use sync-safe pricing cache to avoid event loop issues in LangChain callbacks
        # See: ADR-039-Cost-Optimization-Token-Management.md
        if cost_usd is None or cost_eur is None or usd_to_eur_rate is None:
            from src.infrastructure.cache.pricing_cache import (
                get_cached_cost_usd_eur,
                get_cached_usd_eur_rate,
            )

            # get_cached_cost_usd_eur returns (cost_usd, cost_eur) tuple
            # Mirrors AsyncPricingService.calculate_token_cost() return signature
            # Reads from in-memory cache (populated from Redis at startup)
            # Returns (0.0, 0.0) if cache not initialized or model not found
            cost_usd, cost_eur = get_cached_cost_usd_eur(
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
            )

            # Get USD/EUR rate from cache (with built-in fallback to settings)
            usd_to_eur_rate = Decimal(str(get_cached_usd_eur_rate()))

        # Phase 5.2B: Thread-safe append for parallel execution
        # v3.3: Sequence counter incremented under lock for chronological ordering
        async with self._lock:
            self._sequence_counter += 1
            record = TokenUsageRecord(
                node_name=node_name,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                cost_usd=float(cost_usd),
                cost_eur=float(cost_eur),
                usd_to_eur_rate=usd_to_eur_rate,
                duration_ms=duration_ms,
                call_type=call_type,
                sequence=self._sequence_counter,
            )
            self._node_records.append(record)

        logger.debug(
            "token_usage_recorded",
            run_id=self.run_id,
            node_name=node_name,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cost_eur=cost_eur,
        )

    async def increment_message_count(self) -> None:
        """
        Increment user message counter.

        Called once per user message (SSE request).

        Phase 5.2B: Made async for thread-safe lock acquisition.
        """
        async with self._lock:
            self._message_count += 1

        logger.debug(
            "message_count_incremented",
            run_id=self.run_id,
            message_count=self._message_count,
        )

    def record_google_api_call(
        self,
        api_name: str,
        endpoint: str,
        cached: bool = False,
    ) -> None:
        """
        Record a Google API call (synchronous - uses pre-loaded pricing cache).

        Called by Google API clients (Places, Routes, Geocoding) to track usage.
        Uses ContextVar for implicit access - no need to pass tracker explicitly.

        Args:
            api_name: API identifier (places, routes, geocoding, static_maps)
            endpoint: Endpoint path (e.g., /places:searchText)
            cached: Whether result was served from cache (no cost if True)
        """
        from src.domains.google_api.pricing_service import GoogleApiPricingService

        if cached:
            # Cache hit - record for stats but zero cost
            record = GoogleApiRecord(
                api_name=api_name,
                endpoint=endpoint,
                cost_usd=Decimal("0"),
                cost_eur=Decimal("0"),
                usd_to_eur_rate=GoogleApiPricingService.get_usd_eur_rate(),
                cached=True,
            )
        else:
            # Real API call - calculate cost
            cost_usd, cost_eur, usd_to_eur_rate = GoogleApiPricingService.get_cost_per_request(
                api_name, endpoint
            )
            record = GoogleApiRecord(
                api_name=api_name,
                endpoint=endpoint,
                cost_usd=cost_usd,
                cost_eur=cost_eur,
                usd_to_eur_rate=usd_to_eur_rate,
                cached=False,
            )

        # Thread-safe append (sync method, but list is protected)
        # Note: This is synchronous as called from sync clients using cached pricing
        self._google_api_records.append(record)

        logger.debug(
            "google_api_call_recorded",
            run_id=self.run_id,
            api_name=api_name,
            endpoint=endpoint,
            cost_eur=float(record.cost_eur),
            cached=cached,
        )

    def get_summary(self) -> dict:
        """
        Get aggregated summary for SSE metadata.

        Returns dict with totals across all nodes:
            - tokens_in: Total prompt tokens
            - tokens_out: Total completion tokens
            - tokens_cache: Total cached tokens
            - cost_eur: Total cost in EUR (LLM only)
            - message_count: Number of user messages
            - google_api_requests: Number of Google API calls (non-cached)
            - google_api_cost_eur: Total Google API cost in EUR

        Returns:
            dict: Aggregated summary
        """
        # For incremental commits, message_count should only be counted once
        # After first commit, _message_count_committed is True → return 0 for subsequent commits
        message_count_for_commit = 0 if self._message_count_committed else self._message_count

        # Google API: count only non-cached calls for requests, sum all costs (0 for cached)
        google_api_requests = len([r for r in self._google_api_records if not r.cached])
        google_api_cost_eur = sum(float(r.cost_eur) for r in self._google_api_records)

        summary = {
            FIELD_TOKENS_IN: sum(r.prompt_tokens for r in self._node_records),
            FIELD_TOKENS_OUT: sum(r.completion_tokens for r in self._node_records),
            FIELD_TOKENS_CACHE: sum(r.cached_tokens for r in self._node_records),
            FIELD_COST_EUR: sum(r.cost_eur for r in self._node_records),
            FIELD_MESSAGE_COUNT: message_count_for_commit,
            # Google API tracking
            FIELD_GOOGLE_API_REQUESTS: google_api_requests,
            FIELD_GOOGLE_API_COST_EUR: google_api_cost_eur,
        }

        # DEBUG: Log detailed breakdown by node for token verification
        node_breakdown = {
            r.node_name: {
                "prompt": r.prompt_tokens,
                "completion": r.completion_tokens,
                "cached": r.cached_tokens,
                "total": r.prompt_tokens + r.completion_tokens + r.cached_tokens,
            }
            for r in self._node_records
        }

        logger.debug(
            "tracking_summary_generated",
            run_id=self.run_id,
            summary=summary,
            node_breakdown=node_breakdown,
            nodes_included=list(node_breakdown.keys()),
            has_semantic_validator="semantic_validator" in node_breakdown,
            google_api_records=len(self._google_api_records),
        )

        return summary

    def get_llm_calls_breakdown(self) -> list[dict]:
        """
        Get detailed LLM calls for debug panel display.

        Returns a list of dictionaries, one per LLM call recorded,
        containing token usage, cost, and duration details per node.

        Note:
            Uses _committed_records_copy as fallback when _node_records is empty.
            This handles the timing issue where commit() is called in
            execute_graph_stream() finally block before debug metrics are built.

        Returns:
            List of dicts with per-call metrics:
                - node_name: LangGraph node name (router, planner, response, etc.)
                - model_name: LLM model used
                - tokens_in: Prompt tokens
                - tokens_out: Completion tokens
                - tokens_cache: Cached tokens
                - cost_eur: Cost in EUR for this call
                - duration_ms: LLM call duration in milliseconds (v3.2)
                - call_type: "chat" or "embedding" (v3.3)
                - sequence: Chronological order number (v3.3)
        """
        # Use pending records if available, otherwise use committed copy
        # This handles timing: commit() clears _node_records but debug metrics
        # are built later and need access to the LLM call breakdown
        records = self._node_records if self._node_records else self._committed_records_copy

        return [
            {
                "node_name": r.node_name,
                "model_name": r.model_name,
                "tokens_in": r.prompt_tokens,
                "tokens_out": r.completion_tokens,
                "tokens_cache": r.cached_tokens,
                "cost_eur": float(r.cost_eur),
                "duration_ms": r.duration_ms,
                "call_type": r.call_type,
                "sequence": r.sequence,
            }
            for r in records
        ]

    def get_cumulative_tokens(self) -> int:
        """Get total tokens consumed (prompt + completion) across all recorded nodes.

        Public API for SubAgentTokenGuard and other consumers that need to check
        cumulative token usage without accessing internal _node_records directly.

        Returns:
            Total tokens (prompt + completion) across all LLM calls in this context.
        """
        records = self._node_records if self._node_records else self._committed_records_copy
        return sum(r.prompt_tokens + r.completion_tokens for r in records)

    def get_google_api_calls_breakdown(self) -> list[dict]:
        """
        Get detailed Google API calls for debug panel display.

        Returns a list of dictionaries, one per Google API call recorded,
        containing endpoint, cost, and cache status.

        Note:
            Uses _committed_google_api_copy as fallback when _google_api_records is empty.
            This handles the timing issue where commit() is called before debug metrics.

        Returns:
            List of dicts with per-call metrics:
                - api_name: API identifier (places, routes, geocoding, etc.)
                - endpoint: Endpoint path (e.g., /places:searchText)
                - cost_usd: Cost in USD for this call
                - cost_eur: Cost in EUR for this call
                - cached: Whether result was served from cache
        """
        # Use pending records if available, otherwise use committed copy
        records = (
            self._google_api_records
            if self._google_api_records
            else getattr(self, "_committed_google_api_copy", [])
        )

        return [
            {
                "api_name": r.api_name,
                "endpoint": r.endpoint,
                "cost_usd": float(r.cost_usd),
                "cost_eur": float(r.cost_eur),
                "cached": r.cached,
            }
            for r in records
        ]

    async def get_aggregated_summary_from_db(self) -> dict:
        """
        Get aggregated token summary from database after persistence.

        Used to retrieve post-UPSERT values for SSE metadata.
        Ensures frontend receives aggregated tokens when multiple
        TrackingContext instances use the same run_id (e.g., HITL flow).

        This method queries the database using the repository pattern to get
        the final aggregated values after all UPSERT operations have completed.

        Returns:
            dict: Aggregated summary with DB values:
                - tokens_in: Total prompt tokens (post-aggregation)
                - tokens_out: Total completion tokens (post-aggregation)
                - tokens_cache: Total cached tokens (post-aggregation)
                - cost_eur: Total cost EUR (post-aggregation)
                - message_count: Message count

        Example:
            >>> async with TrackingContext(...) as tracker:
            ...     # ... track tokens ...
            ...     # After context exit, persistence completes
            ...     aggregated = await tracker.get_aggregated_summary_from_db()
        """
        async with get_db_context() as db:
            from src.domains.chat.repository import ChatRepository

            chat_repo = ChatRepository(db)
            summary = await chat_repo.get_token_summary_by_run_id(self.run_id)

            if summary:
                logger.debug(
                    "aggregated_summary_retrieved_from_db",
                    run_id=self.run_id,
                    tokens_in=summary.total_prompt_tokens,
                    tokens_out=summary.total_completion_tokens,
                    tokens_cache=summary.total_cached_tokens,
                    cost_eur=float(summary.total_cost_eur),
                    google_api_requests=summary.google_api_requests,
                )
                # Include Google API costs in total cost for accurate billing display
                total_cost = float(summary.total_cost_eur) + float(summary.google_api_cost_eur or 0)
                return {
                    FIELD_TOKENS_IN: summary.total_prompt_tokens,
                    FIELD_TOKENS_OUT: summary.total_completion_tokens,
                    FIELD_TOKENS_CACHE: summary.total_cached_tokens,
                    FIELD_COST_EUR: total_cost,
                    FIELD_MESSAGE_COUNT: self._message_count,
                    FIELD_GOOGLE_API_REQUESTS: summary.google_api_requests,
                    FIELD_GOOGLE_API_COST_EUR: float(summary.google_api_cost_eur or 0),
                }
            else:
                # Fallback to in-memory if DB not yet updated (should not happen normally)
                logger.warning(
                    "aggregated_summary_not_found_in_db_using_fallback",
                    run_id=self.run_id,
                )
                return self.get_summary()

    # PHASE 3.1.2: DTO-based methods (replaces dictionary-based methods above)
    # These methods provide type-safe abstraction and eliminate duplicate dict constructions

    def get_summary_dto(self) -> TokenSummaryDTO:
        """
        Get aggregated token summary as DTO (PHASE 3.1.2 - Type-safe refactoring).

        Replaces dictionary-based get_summary() with immutable, type-safe DTO.
        Eliminates manual dictionary construction and provides compile-time safety.

        Returns:
            TokenSummaryDTO: Immutable summary with aggregated values from in-memory records

        Example:
            >>> tracker = TrackingContext(...)
            >>> tracker.track_node_tokens(...)
            >>> summary = tracker.get_summary_dto()
            >>> assert isinstance(summary, TokenSummaryDTO)
            >>> metadata = summary.to_metadata()  # Convert to dict for SSE
        """
        return TokenSummaryDTO.from_tracker(self)

    async def get_aggregated_summary_dto_from_db(self) -> TokenSummaryDTO:
        """
        Get aggregated token summary from DB as DTO (PHASE 3.1.2 - Type-safe refactoring).

        Replaces dictionary-based get_aggregated_summary_from_db() with type-safe DTO.
        Queries database for post-UPSERT aggregated values (handles HITL multi-context flows).

        Returns:
            TokenSummaryDTO: Summary with DB values (aggregated across all TrackingContexts with same run_id)
            Falls back to in-memory summary if DB query fails

        Example:
            >>> async with TrackingContext(...) as tracker:
            ...     # ... graph execution ...
            ...
            >>> # After context exit, persistence completes
            >>> summary_dto = await tracker.get_aggregated_summary_dto_from_db()
            >>> yield ChatStreamChunk(type="done", content="", metadata=summary_dto.to_metadata())
        """
        # Reuse existing DB query logic, wrap result in DTO
        summary_dict = await self.get_aggregated_summary_from_db()
        return TokenSummaryDTO.from_dict(summary_dict)

    async def commit(self) -> None:
        """
        Manually commit tracking data to database.

        Supports incremental commits: records are cleared after each commit,
        allowing new records (e.g., TTS costs) to be added and committed later.
        This is essential for voice HD mode where TTS costs are tracked AFTER
        the initial LLM token commit.

        Example:
            >>> async with TrackingContext(...) as tracker:
            >>>     # LLM tokens tracked here...
            >>>     await tracker.commit()  # First commit: LLM tokens
            >>>     # TTS synthesis happens here...
            >>>     # TTS tokens tracked via record_node_tokens()
            >>>     # __aexit__ commits remaining TTS tokens
        """
        # Check for pending records (not yet committed)
        pending_records = len(self._node_records)
        pending_message = self._message_count > 0 and not self._message_count_committed

        if pending_records == 0 and not pending_message:
            logger.debug(
                "tracking_context_commit_skipped_no_pending",
                run_id=self.run_id,
                total_committed=self._total_committed_records,
            )
            return

        # Persist pending records — don't let tracking failure break the chat flow
        try:
            await self._persist_to_database()
            logger.info(
                "tracking_context_manually_committed",
                run_id=self.run_id,
                node_records_count=pending_records,
                total_committed=self._total_committed_records,
                message_count=self._message_count,
            )
        except Exception as e:
            logger.error(
                "tracking_context_manual_commit_failed",
                run_id=self.run_id,
                error=str(e),
                exc_info=True,
            )

    async def _persist_to_database(self) -> None:
        """
        Persist token usage to database (atomic transaction).

        Creates:
        1. token_usage_logs (detail per node)
        2. message_token_summary (aggregated per message)
        3. Updates user_statistics (lifetime + cycle)

        When external session provided (self._external_db), uses that session
        and does NOT commit - caller is responsible for transaction management.
        This enables participation in larger transactions (e.g., proactive tasks).
        """
        # Use external session if provided, otherwise create new one
        if self._external_db is not None:
            await self._do_persist(self._external_db, commit=False)
        else:
            async with get_db_context() as db:
                await self._do_persist(db, commit=True)

    async def _do_persist(self, db: AsyncSession, *, commit: bool) -> None:
        """
        Internal persistence logic.

        Args:
            db: Database session to use
            commit: Whether to commit the transaction (False when using external session)
        """
        from src.domains.chat.repository import ChatRepository

        chat_repo = ChatRepository(db)

        # DEBUG: Log what's in _node_records before persistence (Phase 2.1.7 - Planner diagnostic)
        logger.info(
            "persist_to_database_node_records_snapshot",
            run_id=self.run_id,
            node_records_count=len(self._node_records),
            node_names=[record.node_name for record in self._node_records],
            total_tokens=sum(
                record.prompt_tokens + record.completion_tokens + record.cached_tokens
                for record in self._node_records
            ),
        )

        # 1. Create detailed logs for each node call using bulk operation
        logs_data = [
            {
                FIELD_NODE_NAME: record.node_name,
                FIELD_MODEL_NAME: record.model_name,
                "prompt_tokens": record.prompt_tokens,
                "completion_tokens": record.completion_tokens,
                "cached_tokens": record.cached_tokens,
                "cost_usd": record.cost_usd,
                FIELD_COST_EUR: record.cost_eur,
                "usd_to_eur_rate": record.usd_to_eur_rate,
            }
            for record in self._node_records
        ]
        await chat_repo.bulk_create_token_logs(
            run_id=self.run_id,
            user_id=self.user_id,
            logs=logs_data,
        )

        # 1b. Create Google API usage logs (only non-cached)
        google_api_billable = [r for r in self._google_api_records if not r.cached]
        if google_api_billable:
            from src.domains.google_api.repository import GoogleApiUsageRepository

            google_api_repo = GoogleApiUsageRepository(db)
            google_api_logs = [
                {
                    "user_id": self.user_id,
                    "run_id": self.run_id,
                    "api_name": record.api_name,
                    "endpoint": record.endpoint,
                    "cost_usd": float(record.cost_usd),
                    "cost_eur": float(record.cost_eur),
                    "usd_to_eur_rate": float(record.usd_to_eur_rate),
                    "cached": False,
                }
                for record in google_api_billable
            ]
            await google_api_repo.bulk_create_logs(google_api_logs)

        # 2. Create or update aggregated message summary (UPSERT)
        summary = self.get_summary()
        await chat_repo.create_or_update_token_summary(
            run_id=self.run_id,
            user_id=self.user_id,
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            summary_data=summary,
        )

        # 3. Update user statistics (upsert)
        await self._update_user_statistics(db, summary)

        # Only commit if not using external session
        if commit:
            await db.commit()

        # Track committed records count BEFORE clearing (for logging and incremental support)
        records_committed_count = len(self._node_records)

        # Phase 2.1.7: Comprehensive token logging with breakdown
        # Log includes all 3 token types for transparency and debugging
        logger.info(
            "token_usage_persisted",
            run_id=self.run_id,
            user_id=str(self.user_id),
            node_count=records_committed_count,
            # Token breakdown (explicit for debugging)
            prompt_tokens=summary[FIELD_TOKENS_IN],
            completion_tokens=summary[FIELD_TOKENS_OUT],
            cached_tokens=summary[FIELD_TOKENS_CACHE],
            # Total (prompt + completion + cached)
            total_tokens=summary[FIELD_TOKENS_IN]
            + summary[FIELD_TOKENS_OUT]
            + summary[FIELD_TOKENS_CACHE],
            cost_eur=summary[FIELD_COST_EUR],
            # Google API tracking
            google_api_requests=summary.get(FIELD_GOOGLE_API_REQUESTS, 0),
            google_api_cost_eur=summary.get(FIELD_GOOGLE_API_COST_EUR, 0),
            # Incremental commit tracking
            total_committed_so_far=self._total_committed_records + records_committed_count,
            external_session=self._external_db is not None,
        )

        # Incremental commit support: clear records after persistence
        # This allows new records (e.g., TTS costs) to be added and committed later
        # Essential for voice HD mode where TTS costs are tracked AFTER initial LLM commit
        self._total_committed_records += records_committed_count
        self._message_count_committed = True

        # Debug Panel: Preserve copy of records for debug metrics
        # get_llm_calls_breakdown() and get_google_api_calls_breakdown() need access after commit
        # Timing: commit happens in execute_graph_stream() finally block,
        # but _add_debug_metrics_sections() is called later in stream_sse_chunks()
        self._committed_records_copy.extend(self._node_records)
        self._committed_google_api_copy.extend(self._google_api_records)

        self._node_records.clear()
        self._google_api_records.clear()

    async def _update_user_statistics(self, db: AsyncSession, summary: dict) -> None:
        """
        Update user statistics (atomic upsert).

        Creates or updates user_statistics record with:
        - Incremented lifetime totals
        - Incremented cycle totals (auto-reset if cycle changed)

        Args:
            db: Database session
            summary: Aggregated summary from get_summary()
        """
        from src.domains.chat.repository import UserStatisticsRepository
        from src.domains.users.repository import UserRepository

        # Get user for cycle calculation using repository
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(self.user_id)
        if not user:
            logger.error(
                "user_not_found_for_statistics",
                user_id=str(self.user_id),
            )
            return

        # Calculate current cycle start date
        current_cycle_start = StatisticsService.calculate_cycle_start(user.created_at)

        # Get existing statistics to check cycle
        stats_repo = UserStatisticsRepository(db)
        stats = await stats_repo.get_by_user_id(self.user_id)

        # Check if cycle changed (determine is_new_cycle flag)
        is_new_cycle = False
        if stats and stats.current_cycle_start < current_cycle_start:
            is_new_cycle = True

        # Create or update using repository (handles both INSERT and UPDATE)
        await stats_repo.create_or_update(
            user_id=self.user_id,
            current_cycle_start=current_cycle_start,
            summary_data=summary,
            is_new_cycle=is_new_cycle,
        )

        # Invalidate usage limit cache after stats update
        if getattr(settings, "usage_limits_enabled", False):
            try:
                from src.domains.usage_limits.service import UsageLimitService

                await UsageLimitService.invalidate_cache_static(self.user_id)
            except Exception:
                pass  # Cache invalidation failure must not break token tracking


class StatisticsService:
    """Service for calculating and retrieving user statistics."""

    @staticmethod
    def calculate_cycle_start(user_created_at: datetime) -> datetime:
        """
        Calculate the start of the current billing cycle.

        Billing cycle is monthly, aligned with user signup date.
        Example: User signed up on 15/01 -> cycle is 15/10 to 15/11

        Args:
            user_created_at: User signup timestamp

        Returns:
            datetime: Start of current billing cycle
        """
        now = datetime.now(UTC)
        signup_day = user_created_at.day

        # Start with same day of current month
        cycle_start = now.replace(
            day=min(signup_day, 28),  # Handle short months (Feb, etc.)
            hour=user_created_at.hour,
            minute=user_created_at.minute,
            second=0,
            microsecond=0,
            tzinfo=UTC,
        )

        # If we're before the signup day this month, go back one month
        if now.day < signup_day or (now.day == signup_day and now.time() < user_created_at.time()):
            cycle_start = cycle_start - relativedelta(months=1)

        return cycle_start

    @staticmethod
    def reset_cycle_if_needed(
        stats: UserStatistics,
        current_cycle_start: datetime,
        user_id: UUID,
    ) -> bool:
        """
        Reset billing cycle counters if cycle has changed.

        Checks if current_cycle_start is newer than stats.current_cycle_start
        and resets all cycle-specific counters (tokens, cost, messages).

        Args:
            stats: UserStatistics object to potentially reset
            current_cycle_start: Expected start of current billing cycle
            user_id: User UUID for logging

        Returns:
            bool: True if cycle was reset, False otherwise
        """
        if stats.current_cycle_start < current_cycle_start:
            stats.current_cycle_start = current_cycle_start
            stats.cycle_prompt_tokens = 0
            stats.cycle_completion_tokens = 0
            stats.cycle_cached_tokens = 0
            stats.cycle_cost_eur = Decimal("0.00")
            stats.cycle_messages = 0
            # Google API cycle counters
            stats.cycle_google_api_requests = 0
            stats.cycle_google_api_cost_eur = Decimal("0.00")

            logger.info(
                "billing_cycle_reset",
                user_id=str(user_id),
                new_cycle_start=current_cycle_start.isoformat(),
            )
            return True

        return False

    @staticmethod
    async def get_user_statistics(user_id: UUID, db: AsyncSession) -> UserStatisticsResponse:
        """
        Get user statistics for dashboard.

        Retrieves pre-calculated statistics from user_statistics table.
        Auto-resets cycle if current cycle has expired.

        Args:
            user_id: User UUID
            db: Database session

        Returns:
            UserStatisticsResponse: User statistics

        Raises:
            ValueError: If user not found
        """
        from src.domains.chat.repository import UserStatisticsRepository
        from src.domains.users.repository import UserRepository

        # Get user for cycle calculation using repository
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Calculate current cycle start
        current_cycle_start = StatisticsService.calculate_cycle_start(user.created_at)

        # Get or create user statistics using repository
        stats_repo = UserStatisticsRepository(db)
        stats = await stats_repo.get_by_user_id(user_id)

        if not stats:
            # Create empty statistics for first-time user using repository
            summary_data = {
                FIELD_TOKENS_IN: 0,
                FIELD_TOKENS_OUT: 0,
                FIELD_TOKENS_CACHE: 0,
                FIELD_COST_EUR: Decimal("0.00"),
                FIELD_MESSAGE_COUNT: 0,
            }
            stats = await stats_repo.create_or_update(
                user_id=user_id,
                current_cycle_start=current_cycle_start,
                summary_data=summary_data,
                is_new_cycle=False,
            )
            await db.commit()
            await db.refresh(stats)

            logger.info(
                "user_statistics_created",
                user_id=str(user_id),
            )

        # Check if cycle needs reset
        elif StatisticsService.reset_cycle_if_needed(stats, current_cycle_start, user_id):
            await db.commit()
            await db.refresh(stats)

        response = UserStatisticsResponse.model_validate(stats)

        # Include Google API costs in total cost fields for accurate billing display.
        # DB stores LLM and Google API costs separately for traceability.
        # We combine them here (service layer) so the frontend shows the real total.
        response.total_cost_eur = response.total_cost_eur + response.total_google_api_cost_eur
        response.cycle_cost_eur = response.cycle_cost_eur + response.cycle_google_api_cost_eur

        return response
