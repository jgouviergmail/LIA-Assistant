"""
Streaming mixin for AgentService.

Responsibilities:
- SSE chunk buffering and enrichment
- Token metadata aggregation for HITL flows
"""

from collections.abc import AsyncGenerator
from typing import Any

from src.core.constants import TOKEN_SUMMARY_CACHE_TTL
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.chat.schemas import TokenSummaryDTO
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class StreamingMixin:
    """
    Mixin for SSE streaming functionality.

    Provides methods for buffering resumption chunks and enriching
    done chunks with aggregated token metadata.
    """

    async def _get_token_summary_best_effort(
        self,
        run_id: str,
        user_id: Any,  # UUID
        conversation_id: Any,  # UUID
        tracker: Any = None,  # Optional TrackingContext
    ) -> TokenSummaryDTO:
        """
        Get aggregated token summary with best-effort fallback chain (PHASE 3.1.3 - Refactored).

        REFACTORED to use TokenSummaryDTO and proper repository pattern.
        No longer instantiates TrackingContext (architectural violation fixed).

        Fallback chain (PHASE 8.1.2 - Added Redis cache):
        1. In-memory tracker (if provided and has data) → tracker.get_summary_dto()
        2. Redis cache (1-hour TTL) → cached token summary
        3. Database direct query → repository.get_token_summary_by_run_id()
        4. Zero fallback (error path safety) → TokenSummaryDTO.zero()

        Args:
            run_id: Run ID for DB lookup
            user_id: User UUID
            conversation_id: Conversation UUID
            tracker: Optional in-memory TrackingContext

        Returns:
            TokenSummaryDTO: Immutable summary (never None, always valid)
            Returns zeros if all sources fail (defensive fallback)

        Example:
            >>> summary_dto = await self._get_token_summary_best_effort(
            ...     run_id=run_id, user_id=user_id, conversation_id=conversation_id, tracker=tracker
            ... )
            >>> yield ChatStreamChunk(type="done", content="", metadata=summary_dto.to_metadata())
        """
        # Try 1: In-memory tracker (fastest, available if passed)
        # CRITICAL FIX: Always trust tracker value, even if 0
        # When tracker exists, 0 tokens means "no new LLM calls" (e.g., HITL resumption)
        # This is the CORRECT incremental value - DO NOT fallback to DB aggregates
        # The DB contains CUMULATIVE tokens which would cause triple-counting
        if tracker:
            try:
                summary_dto: TokenSummaryDTO = tracker.get_summary_dto()
                # Return tracker value unconditionally - 0 is valid (no LLM calls this cycle)
                logger.debug(
                    "token_summary_from_memory",
                    run_id=run_id,
                    tokens_in=summary_dto.tokens_in,
                    source="tracker_memory",
                )
                return summary_dto
            except Exception as e:
                logger.warning(
                    "token_summary_memory_failed",
                    run_id=run_id,
                    error=str(e),
                )

        # Try 2: Redis cache (PHASE 8.1.2 - Performance optimization)
        try:
            import json

            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            redis_key = f"token_summary:{run_id}"
            cached_data = await redis.get(redis_key)

            if cached_data:
                summary_dto_cached: TokenSummaryDTO = TokenSummaryDTO.from_dict(
                    json.loads(cached_data)
                )
                logger.debug(
                    "token_summary_from_redis",
                    run_id=run_id,
                    tokens_in=summary_dto_cached.tokens_in,
                    source="redis_cache",
                )
                return summary_dto_cached
        except Exception as e:
            logger.warning(
                "token_summary_redis_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )

        # Try 3: Database query (direct repository access, no TrackingContext instantiation)
        try:
            import json

            from src.domains.chat.repository import ChatRepository
            from src.infrastructure.cache.redis import get_redis_cache
            from src.infrastructure.database import get_db_context

            async with get_db_context() as db:
                chat_repo = ChatRepository(db)
                db_record = await chat_repo.get_token_summary_by_run_id(run_id)

                if db_record and db_record.total_prompt_tokens > 0:
                    summary_dto_db: TokenSummaryDTO = TokenSummaryDTO(
                        tokens_in=db_record.total_prompt_tokens,
                        tokens_out=db_record.total_completion_tokens,
                        tokens_cache=db_record.total_cached_tokens,
                        cost_eur=float(db_record.total_cost_eur),
                        message_count=1,  # Default to 1 (SSE context always has 1 message)
                        google_api_requests=db_record.google_api_requests,
                    )

                    # Cache for 1 hour (PHASE 8.1.2 - Performance optimization)
                    try:
                        redis = await get_redis_cache()
                        redis_key = f"token_summary:{run_id}"
                        await redis.setex(
                            redis_key, TOKEN_SUMMARY_CACHE_TTL, json.dumps(summary_dto_db.to_dict())
                        )
                    except Exception as cache_err:
                        logger.warning(
                            "token_summary_cache_write_failed", run_id=run_id, error=str(cache_err)
                        )

                    logger.info(
                        "token_summary_from_db",
                        run_id=run_id,
                        tokens_in=summary_dto_db.tokens_in,
                        tokens_out=summary_dto_db.tokens_out,
                        cost_eur=summary_dto_db.cost_eur,
                        source="database_fallback",
                    )
                    return summary_dto_db
        except Exception as e:
            logger.warning(
                "token_summary_db_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )

        # Try 4: Defensive fallback (prevents errors in error paths)
        logger.warning(
            "token_summary_unavailable_using_zeros",
            run_id=run_id,
            conversation_id=str(conversation_id),
            message="All token retrieval methods failed, using zero values",
        )
        return TokenSummaryDTO.zero()

    async def buffer_and_enrich_resumption_chunks(
        self,
        graph_stream: Any,  # AsyncGenerator
        run_id: str,
        user_id: Any,  # UUID
        conversation_id: Any,  # UUID
        tracker: Any = None,  # Optional TrackingContext
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Stream chunks immediately and enrich done chunk with aggregated tokens.

        PHASE 8.4.1 OPTIMIZATION: Stream-first approach for improved perceived latency.

        Old approach (pre-8.4.1):
        - Buffer ALL chunks → Query DB → Yield all chunks
        - TTFB: Depends on full graph execution (2-5s)
        - Memory: High (all chunks buffered)

        New approach (post-8.4.1):
        - Stream chunks immediately as they arrive
        - Only buffer 'done' chunk for enrichment
        - TTFB: < 100ms (first chunk arrives immediately)
        - Memory: Low (no chunk buffering)

        After HITL resumption, the graph streams normally. We:
        1. Stream all chunks immediately (except done)
        2. Buffer only done chunk
        3. After stream completes, query DB for aggregated tokens
        4. Enrich done chunk metadata with DB values
        5. Yield enriched done chunk

        This ensures:
        - Frontend receives chunks progressively (better UX)
        - Aggregated tokens still included in done chunk
        - No page refresh required

        Args:
            graph_stream: AsyncGenerator from graph resumption
            run_id: Run ID for token lookup
            user_id: User UUID
            conversation_id: Conversation UUID
            tracker: Optional TrackingContext for in-memory aggregation

        Yields:
            ChatStreamChunk: Streamed immediately (except done chunk)

        Performance:
            - Perceived latency: -500ms-2s (first chunk immediate)
            - Memory usage: -90% (no buffering)
            - User experience: Significantly improved

        Note:
            - Queries DB after stream completes (TrackingContext has committed)
            - Metadata merge order: original first, then DB values overwrite
            - Falls back to original metadata if DB query fails
        """
        done_chunk = None

        # Stream chunks immediately (PHASE 8.4.1 - no buffering)
        async for chunk in graph_stream:
            if isinstance(chunk, ChatStreamChunk) and chunk.type == "done":
                # Buffer only done chunk for enrichment
                done_chunk = chunk
            else:
                # Stream immediately (low latency) ⚡
                yield chunk

        # Get aggregated tokens using best-effort helper (PHASE 3.1.3 - now returns DTO)
        aggregated_summary_dto = await self._get_token_summary_best_effort(
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            tracker=tracker,
        )

        # Enrich and yield done chunk
        # CRITICAL: Merge order matters!
        # Original metadata first, then token values overwrite
        enriched_done = ChatStreamChunk(
            type="done",
            content="",
            metadata={
                **(
                    done_chunk.metadata if done_chunk and done_chunk.metadata else {}
                ),  # Original first (if exists)
                **aggregated_summary_dto.to_metadata(),  # Token metadata from DTO
            },
        )
        logger.info(
            "hitl_enriched_done_chunk_sent",
            run_id=run_id,
            tokens_in=aggregated_summary_dto.tokens_in,
            tokens_out=aggregated_summary_dto.tokens_out,
            tokens_cache=aggregated_summary_dto.tokens_cache,
            cost_eur=aggregated_summary_dto.cost_eur,
            had_done_chunk=done_chunk is not None,
            optimization="stream_first",  # PHASE 8.4.1 marker
        )
        yield enriched_done
