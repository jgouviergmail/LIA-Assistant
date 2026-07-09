"""
StreamingService: SSE event formatting and token streaming.

Responsibilities:
- Convert OrchestrationService (mode, chunk) tuples to SSE chunks
- Extract router decisions from routing_history
- Emit execution_step events for node transitions
- Filter tokens to response node only
- Track streaming metrics (TTFT, tokens generated, duration)
- Handle HITL interrupts (emit HITL chunks, archive messages, store in Redis)
"""

import asyncio
import re
import time
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessageChunk
from structlog import get_logger

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.field_names import (
    FIELD_CONVERSATION_ID,
    FIELD_METADATA,
    FIELD_RUN_ID,
    FIELD_STATUS,
)
from src.domains.agents.api.schemas import ChatStreamChunk
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.metrics_agents import (
    sse_streaming_duration_seconds,
    sse_time_to_first_token_seconds,
    sse_tokens_generated_total,
)
from src.infrastructure.observability.metrics_langgraph import (
    langgraph_streaming_chunks_total,
)

if TYPE_CHECKING:
    from src.domains.agents.utils.hitl_store import HITLStore
    from src.domains.chat.service import TrackingContext
    from src.domains.conversations.service import ConversationService

logger = get_logger(__name__)

# Default id of langgraph.types.Interrupt when no real interrupt id was
# assigned — treated as "no id" for the per-interrupt SSE message_id.
_LANGGRAPH_INTERRUPT_PLACEHOLDER_ID = "placeholder-id"

# Phase 1 HITL Streaming imports - lazy loaded to avoid circular imports
_hitl_registry = None
_hitl_question_generator = None


def _get_hitl_registry():
    """Lazy load HitlInteractionRegistry to avoid circular imports."""
    global _hitl_registry
    if _hitl_registry is None:
        from src.domains.agents.services.hitl.registry import HitlInteractionRegistry

        _hitl_registry = HitlInteractionRegistry
    return _hitl_registry


def _get_hitl_question_generator():
    """Lazy load HitlQuestionGenerator to avoid circular imports."""
    global _hitl_question_generator
    if _hitl_question_generator is None:
        from src.domains.agents.services.hitl.question_generator import (
            HitlQuestionGenerator,
        )

        _hitl_question_generator = HitlQuestionGenerator()
    return _hitl_question_generator


def _get_chunk_event_type(chunk_type: str) -> str:
    """
    Map ChatStreamChunk type to Prometheus event_type for metrics.

    PHASE 2.5 - P5: Streaming events tracking.

    Maps specific chunk types to generic event categories for cardinality control.

    Args:
        chunk_type: ChatStreamChunk.type (e.g., "token", "router_decision", etc.)

    Returns:
        Generic event_type for Prometheus label

    Mapping:
        - token → STREAM_TOKEN
        - content_replacement → STREAM_TOKEN (final content is also token-like)
        - router_decision, execution_step → STREAM_METADATA
        - registry_update → STREAM_REGISTRY (Data Registry side-channel data)
        - hitl_* → STREAM_INTERRUPT
        - error → STREAM_ERROR
        - done → STREAM_COMPLETE
    """
    if chunk_type == "token":
        return "STREAM_TOKEN"
    elif chunk_type == "content_replacement":
        return "STREAM_TOKEN"  # Final content is token-like
    elif chunk_type in ("router_decision", "execution_step"):
        return "STREAM_METADATA"
    elif chunk_type == "registry_update":
        return "STREAM_REGISTRY"  # Data Registry: Side-channel registry data
    elif chunk_type == "debug_metrics":
        return "STREAM_DEBUG"  # Debug Panel: Scoring metrics (DEBUG=true only)
    elif chunk_type.startswith("hitl_"):
        return "STREAM_INTERRUPT"
    elif chunk_type == "error":
        return "STREAM_ERROR"
    elif chunk_type == "done":
        return "STREAM_COMPLETE"
    else:
        # Unknown types (future additions) → generic category
        return "STREAM_OTHER"


def _serialize_registry_items(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Serialize registry items for voice context and SSE.

    Handles both RegistryItem Pydantic objects and raw dicts.
    Preserves item IDs as keys for O(1) lookup.

    Args:
        registry: Dict mapping item_id to RegistryItem or raw dict

    Returns:
        Dict mapping item_id to serialized dict (JSON-compatible)

    Note:
        Uses mode="json" for Pydantic objects to ensure datetime serialization.
        Raw dicts are passed through unchanged.
    """
    serialized: dict[str, dict[str, Any]] = {}
    for item_id, item in registry.items():
        if hasattr(item, "model_dump"):
            serialized[item_id] = item.model_dump(mode="json")
        else:
            serialized[item_id] = item
    return serialized


class StreamingService:
    """
    Service for SSE event formatting and streaming.

    Responsibilities:
    - Convert OrchestrationService (mode, chunk) tuples to SSE chunks
    - Extract router decisions from routing_history
    - Emit execution_step events for node transitions
    - Filter tokens to response node only
    - Track streaming metrics (TTFT, duration, token count)
    - Handle HITL interrupts (emit chunks, archive, store in Redis)
    """

    def __init__(
        self,
        conv_service: "ConversationService | None" = None,
        hitl_store: "HITLStore | None" = None,
        tracker: "TrackingContext | None" = None,
        user_message: str | None = None,
        user_id: str | None = None,
        debug_panel_enabled: bool = False,
    ):
        """
        Initialize StreamingService with optional HITL dependencies.

        Args:
            conv_service: For archiving messages during HITL
            hitl_store: For storing pending HITL data in Redis
            tracker: For committing token tracking on HITL
            user_message: Original user message for archiving
            user_id: User ID for interest extraction debug metrics
            debug_panel_enabled: Pre-computed flag for debug metrics emission
        """
        self.conv_service = conv_service
        self.hitl_store = hitl_store
        self.tracker = tracker
        self.user_message = user_message
        self.user_id = user_id
        # Flag to track if HITL interrupt occurred during streaming
        # Used by service.py to determine appropriate archiving metadata
        self.hitl_interrupt_detected = False
        # Duplicate-display fix: track whether the response node streamed token deltas
        # (AIMessageChunk). LangGraph "messages" mode also emits the complete AIMessage the
        # node returns to the ``messages`` channel; emitting it after the deltas duplicates
        # the whole reply on screen. We skip that complete message only once deltas were
        # seen — preserving the non-streaming path where the complete message is all we get.
        self._response_deltas_streamed = False
        # Store the generated HITL question for archiving by service.py
        # This ensures the question appears in conversation history on reload
        self.hitl_generated_question: str | None = None
        # Cache query_intelligence, filtered_catalogue, and tool_scores for debug_metrics
        # Emitted once in the stream but needed for all debug_metrics chunks
        self._cached_query_intelligence: Any | None = None
        self._cached_filtered_catalogue: Any | None = None
        self._cached_tool_scores: dict[str, Any] | None = None
        # Debug panel enabled flag (pre-computed by api/service.py based on user role)
        # Controls ALL debug processing: caching, building, and emitting debug_metrics
        self._debug_panel_enabled: bool = debug_panel_enabled
        # Voice context: Registry data for parallel voice generation
        # Captured EARLY in _process_values_chunk when current_turn_registry appears
        # (task_orchestrator just completed). This enables true parallel voice generation
        # DURING response_node streaming, not after.
        self.voice_context_registry: dict[str, Any] | None = None
        # Latest snapshot of state.messages from the "values" stream mode. Updated
        # on every values chunk so api/service.py can compute the context-usage
        # indicator (tokens / threshold) for the SSE `done` chunk metadata.
        # Context-usage pill — 2026-05.
        self.latest_state_messages: list[Any] | None = None
        # Skill name activated during this turn (from plan metadata)
        # Used by service.py to include in done SSE metadata for frontend badge
        self.activated_skill_name: str | None = None
        # Track checkpoint agent_results to detect when task_orchestrator has run
        # CRITICAL: current_turn_registry persists in state from previous turn until
        # task_orchestrator updates it. task_orchestrator ALSO updates agent_results.
        # By detecting when agent_results CHANGES from the checkpoint value, we know
        # task_orchestrator has run and current_turn_registry contains FRESH data.
        #
        # This correctly handles:
        # - Turn 1: agent_results {} → {data} (capture)
        # - Turn N: agent_results {prev} → {current} (capture)
        # - Chat mode: agent_results never changes (don't capture → fallback to response_content)
        self._checkpoint_agent_results_ids: frozenset[str] | None = None
        # Track checkpoint routing_history signature to detect when router_node has
        # run in the CURRENT turn. Symmetric to _checkpoint_agent_results_ids.
        #
        # LangGraph "values" stream emits the checkpoint state at turn start, BEFORE
        # router_node runs. routing_history[-1] then carries the PREVIOUS turn's
        # RouterOutput. Emitting a router_decision SSE based on that stale entry
        # triggered chat_voice_streamer (direct TTS) whenever the previous turn was
        # intention="conversation" — forcing the voice path to read the displayed
        # text instead of going through the Voice Comment LLM once the real router
        # resolved a different intention (e.g. action with tools).
        #
        # We capture the initial signature and suppress router_decision emission
        # until the signature changes (router_node has appended a fresh RouterOutput
        # in the current turn).
        self._checkpoint_routing_signature: tuple[Any, ...] | None = None

    async def stream_sse_chunks(
        self,
        graph_stream: AsyncGenerator[tuple[str, Any], None],
        conversation_id: uuid.UUID,
        run_id: str,
    ) -> AsyncGenerator[tuple[ChatStreamChunk, str], None]:
        """
        Convert OrchestrationService stream to SSE chunks.

        Args:
            graph_stream: Raw (mode, chunk) tuples from execute_graph_stream()
            conversation_id: For logging/tracking context
            run_id: Unique run identifier for metrics

        Yields:
            tuple[ChatStreamChunk, str]: (SSE chunk, accumulated content)
            - SSE chunk: Formatted for streaming
            - Accumulated content: Response content collected so far (for archiving)

        Example:
            >>> async for sse_chunk, content in service.stream_sse_chunks(stream, conv_id, run_id):
            ...     yield sse_chunk  # Send to client
            ...     response_content += content  # Track for archiving
        """
        start_time = time.time()
        first_token_time = None
        token_count = 0

        # Debug panel flag is pre-computed by api/service.py (passed via __init__)
        # No async fetch needed here - zero overhead when disabled

        # State tracking across chunks
        state: dict[Any, Any] = {}
        last_sent_routing = None
        last_emitted_node = None
        response_content = ""
        intention_label = "unknown"  # Will be updated when router decision is received

        # Data Registry: Track registry IDs already sent to avoid duplicates
        sent_registry_ids: set[str] = set()

        try:
            async for mode, chunk in graph_stream:
                # Guard: Validate chunk type for robustness
                if not isinstance(chunk, dict | tuple):
                    logger.warning(
                        "unexpected_chunk_type",
                        mode=mode,
                        chunk_type=type(chunk).__name__,
                        run_id=run_id,
                    )
                    continue

                # Process based on stream mode
                if mode == "values":
                    # State update - extract router decisions AND check for HITL
                    # Type narrowing: LangGraph "values" mode always emits dict
                    if not isinstance(chunk, dict):
                        logger.warning(
                            "values_mode_non_dict_chunk",
                            mode=mode,
                            chunk_type=type(chunk).__name__,
                            run_id=run_id,
                        )
                        continue

                    state = chunk

                    # === HITL DETECTION ===
                    if "__interrupt__" in chunk:
                        # HITL interrupt detected - set flag for service.py archiving
                        self.hitl_interrupt_detected = True
                        # Handle HITL and exit
                        async for hitl_chunk in self._handle_hitl_interrupt(
                            chunk, conversation_id, run_id
                        ):
                            yield (hitl_chunk, "")  # HITL chunks have no content
                        return  # Exit generator after HITL

                    # NO HITL - process normally. Registry updates are NOT
                    # emitted here: they are emitted once, post-stream, by
                    # _emit_post_stream_registry (final state, deduplicated
                    # via the generator-scoped sent_registry_ids).
                    sse_chunks = self._process_values_chunk(chunk, last_sent_routing)

                    for sse_chunk, content_fragment in sse_chunks:
                        # PHASE 2.5 - P5: Track streaming chunk emission
                        event_type = _get_chunk_event_type(sse_chunk.type)
                        langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

                        # Track if we sent a router decision
                        if sse_chunk.type == "router_decision":
                            routing_history = chunk.get("routing_history", [])
                            if routing_history:
                                last_sent_routing = routing_history[-1]
                            # Update intention_label for metrics
                            if sse_chunk.metadata:
                                intention_label = sse_chunk.metadata.get("intention", "unknown")

                        yield (sse_chunk, content_fragment)

                elif mode == "messages":
                    # Message tuple - extract tokens (node detection via "updates")
                    # Type narrowing: LangGraph "messages" mode always emits tuple
                    if not isinstance(chunk, tuple):
                        logger.warning(
                            "messages_mode_non_tuple_chunk",
                            mode=mode,
                            chunk_type=type(chunk).__name__,
                            run_id=run_id,
                        )
                        continue

                    sse_chunks = self._process_messages_chunk(chunk, state, first_token_time)

                    for sse_chunk, content_fragment in sse_chunks:
                        # PHASE 2.5 - P5: Track streaming chunk emission
                        event_type = _get_chunk_event_type(sse_chunk.type)
                        langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

                        # Track first token time
                        if sse_chunk.type == "token" and first_token_time is None:
                            first_token_time = time.time()
                            ttft = first_token_time - start_time
                            sse_time_to_first_token_seconds.labels(
                                intention=intention_label
                            ).observe(ttft)
                            logger.debug(
                                "first_token_received",
                                run_id=run_id,
                                ttft_seconds=ttft,
                                intention=intention_label,
                            )

                        # Track token count and emit
                        if sse_chunk.type == "token":
                            token_count += 1
                            response_content += content_fragment

                        yield (sse_chunk, content_fragment)

                elif mode == "updates":
                    # Node completion — emit execution_step for all nodes
                    # "updates" yields {node_name: state_delta} after each node
                    if not isinstance(chunk, dict):
                        logger.warning(
                            "updates_mode_non_dict_chunk",
                            mode=mode,
                            chunk_type=type(chunk).__name__,
                            run_id=run_id,
                        )
                        continue

                    sse_chunks = self._process_updates_chunk(chunk, state)

                    for sse_chunk, content_fragment in sse_chunks:
                        event_type = _get_chunk_event_type(sse_chunk.type)
                        langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

                        # Track node transitions for diagnostic logging
                        if sse_chunk.type == "execution_step" and sse_chunk.metadata:
                            step_name = sse_chunk.metadata.get("step_name")
                            if step_name:
                                last_emitted_node = step_name

                        yield (sse_chunk, content_fragment)

                elif mode == "custom":
                    # Node-emitted custom events (Day 2 — Task 2.1).
                    # Nodes call langgraph.config.get_stream_writer() and push a
                    # dict shaped like {type, step_type, step_label, metadata}.
                    # We translate that to a ChatStreamChunk and forward it.
                    sse_chunks = self._process_custom_chunk(chunk)

                    for sse_chunk, content_fragment in sse_chunks:
                        event_type = _get_chunk_event_type(sse_chunk.type)
                        langgraph_streaming_chunks_total.labels(event_type=event_type).inc()
                        yield (sse_chunk, content_fragment)

            # =========================================================================
            # DIAGNOSTIC: Log state summary after streaming loop for debugging
            # =========================================================================
            # Helps diagnose when response_node doesn't generate tokens
            if token_count == 0 and state:
                # Extract key state info for diagnostics
                routing_history = state.get("routing_history", [])
                messages = state.get("messages", [])
                last_routing = routing_history[-1] if routing_history else None

                # Check for response node messages
                response_messages = [
                    m for m in messages if hasattr(m, "__class__") and "AI" in m.__class__.__name__
                ]

                logger.warning(
                    "streaming_zero_tokens_diagnostic",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                    intention=intention_label,
                    routing_count=len(routing_history),
                    last_routing_next_node=(
                        getattr(last_routing, "next_node", None) if last_routing else None
                    ),
                    last_routing_intention=(
                        getattr(last_routing, "intention", None) if last_routing else None
                    ),
                    messages_count=len(messages),
                    ai_messages_count=len(response_messages),
                    last_emitted_node=last_emitted_node,
                    state_keys=list(state.keys())[:15],  # Limit for readability
                    has_agent_results="agent_results" in state and bool(state.get("agent_results")),
                    has_query_intelligence="query_intelligence" in state,
                )

            # Data Registry: emit registry_update AFTER the streaming loop (final state).
            async for _reg_chunk in self._emit_post_stream_registry(
                state, sent_registry_ids, run_id
            ):
                yield _reg_chunk

            # PHASE 5.5: Emit final content replacement if post-processing occurred
            # When response_node performs post-processing (e.g., photo HTML injection),
            # it signals via "content_final_replacement" in state. We need to emit a
            # STREAM_REPLACE chunk so frontend replaces the streamed content with the
            # complete post-processed version.
            # ✅ CRITICAL FIX: Check value is truthy, not just key presence
            # Root cause: Key can exist with None value from previous cleanup
            # See: ROOT_CAUSE_NONETYPE_LEN_ERROR.md
            if state and state.get("content_final_replacement"):
                final_content = state["content_final_replacement"]
                logger.info(
                    "emitting_final_content_replacement",
                    run_id=run_id,
                    final_content_length=len(final_content),
                    original_streamed_length=len(response_content),
                    diff_bytes=len(final_content) - len(response_content),
                )

                # Emit content_replacement chunk (Phase 5.5: Post-processing streaming)
                # Frontend will handle this by replacing entire message content
                replacement_chunk = ChatStreamChunk(
                    type="content_replacement",
                    content=final_content,
                )

                # PHASE 2.5 - P5: Track content replacement chunk
                event_type = _get_chunk_event_type(replacement_chunk.type)
                langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

                yield (replacement_chunk, final_content)

                # Update response_content and token_count for metrics/archiving
                # Setting token_count > 0 prevents fallback generation (line 529)
                response_content = final_content
                token_count = len(final_content.split())  # Approximate token count

            # Debug Panel: emit debug_metrics ONCE at the end (all data available).
            async for _dbg_chunk in self._emit_debug_metrics(state, run_id):
                yield _dbg_chunk

            # =================================================================
            # SAFETY NET: Fallback for chat when response_node didn't stream
            # =================================================================
            # Bug detected 2026-01: When routing directly to response (conversation intent,
            # domains=[]), the graph stream may complete before response_node generates tokens.
            # This causes the frontend to stay stuck on "Generating response...".
            # Emit an elegant LLM-generated fallback to ensure the user sees a helpful response.
            if (
                token_count == 0
                and intention_label == "conversation"
                and not self.hitl_interrupt_detected
            ):
                from src.domains.agents.services.fallback_response import generate_fallback_response

                logger.warning(
                    "streaming_fallback_no_tokens_conversation",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                    intention=intention_label,
                    user_query_preview=self.user_message[:50] if self.user_message else "empty",
                    reason="Graph stream completed without response tokens - generating LLM fallback",
                )

                # Generate elegant fallback via LLM
                # Build config with TokenTrackingCallback for billing tracking
                fallback_config = None
                if self.tracker:
                    from src.infrastructure.observability.callbacks import TokenTrackingCallback

                    fallback_config = {
                        "callbacks": [TokenTrackingCallback(self.tracker, run_id)],
                        "metadata": {"langgraph_node": "fallback_response"},
                    }

                async for fallback_chunk, content_fragment in generate_fallback_response(
                    user_query=self.user_message or "",
                    run_id=run_id,
                    format_chunk_fn=self.format_token_chunk,
                    config=fallback_config,
                    user_id=str(self.user_id) if self.user_id else None,
                    language=state.get("user_language") if state else None,
                ):
                    response_content += content_fragment
                    token_count += 1
                    yield (fallback_chunk, content_fragment)

            # Track total duration and tokens
            duration = time.time() - start_time
            sse_streaming_duration_seconds.labels(intention=intention_label).observe(duration)
            sse_tokens_generated_total.labels(intention=intention_label, node_name="response").inc(
                token_count
            )

            logger.info(
                "streaming_complete",
                run_id=run_id,
                conversation_id=str(conversation_id),
                duration_seconds=duration,
                tokens_generated=token_count,
                content_length=len(response_content),
            )

        except asyncio.CancelledError:
            # Client disconnected during streaming — graceful termination
            logger.info(
                "streaming_cancelled",
                run_id=run_id,
                conversation_id=str(conversation_id),
            )
            raise

        except (TimeoutError, RuntimeError, ValueError, OSError) as e:
            logger.error(
                "streaming_error",
                exc_info=True,
                run_id=run_id,
                conversation_id=str(conversation_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def _emit_debug_metrics(
        self, state: dict[Any, Any], run_id: str
    ) -> AsyncGenerator[tuple[ChatStreamChunk, str], None]:
        """Yield the debug-panel ``debug_metrics`` chunk at end of stream (if enabled).

        Extracted verbatim from ``stream_sse_chunks`` (behavior-preserving): gated on
        ``_debug_panel_enabled`` + cached query intelligence, it builds the base
        metrics, awaits background tasks, adds the builder sections plus the
        interest/memory detections, then yields a single ``debug_metrics`` chunk.
        """
        if self._debug_panel_enabled:
            try:
                if self._cached_query_intelligence:
                    logger.debug(
                        "debug_metrics_building_start",
                        run_id=run_id,
                    )

                    query_intelligence = self._cached_query_intelligence
                    debug_metrics = query_intelligence.to_debug_metrics()

                    logger.debug(
                        "debug_metrics_base_built",
                        run_id=run_id,
                        has_domain_selection="domain_selection" in debug_metrics,
                        has_routing_decision="routing_decision" in debug_metrics,
                    )

                    # Wait for background tasks (memory, interest, journal extraction)
                    # so their token costs are persisted before we read the DB totals.
                    # This ensures the debug panel shows the same cost as the bubble.
                    if run_id:
                        from src.infrastructure.async_utils import await_run_id_tasks

                        awaited = await await_run_id_tasks(run_id, timeout=15.0)
                        if awaited:
                            logger.info(
                                "debug_panel_awaited_background_tasks",
                                run_id=run_id,
                                tasks_awaited=awaited,
                            )

                    # Fetch DB-aggregated totals (now includes background task costs)
                    db_aggregated = None
                    if self.tracker and hasattr(self.tracker, "get_aggregated_summary_dto_from_db"):
                        try:
                            db_aggregated = await self.tracker.get_aggregated_summary_dto_from_db()
                            logger.info(
                                "debug_panel_db_aggregated_fetched",
                                run_id=run_id,
                                db_tokens_in=getattr(db_aggregated, "tokens_in", 0),
                                db_tokens_out=getattr(db_aggregated, "tokens_out", 0),
                                db_cost_eur=float(getattr(db_aggregated, "cost_eur", 0)),
                            )
                        except Exception as db_fetch_err:
                            logger.warning(
                                "debug_panel_db_aggregated_failed",
                                run_id=run_id,
                                error=f"{type(db_fetch_err).__name__}: {db_fetch_err}",
                            )

                    # Add all cached data
                    self._add_debug_metrics_sections(
                        debug_metrics=debug_metrics,
                        state=state,
                        run_id=run_id,
                        db_aggregated=db_aggregated,
                    )

                    # =============================================================
                    # Interest Detection: Analyze current message for interests
                    # =============================================================
                    # Uses analyze_interests_for_debug() to detect interests in the
                    # current user message. Shows what interests are being extracted.
                    # Results are cached in Redis (reused by background extraction).
                    if self.user_id and state:
                        try:
                            from src.domains.interests.services.extraction_service import (
                                analyze_interests_for_debug,
                            )

                            messages = state.get("messages", [])
                            user_language = state.get("user_language", settings.default_language)

                            interest_detection = await analyze_interests_for_debug(
                                user_id=self.user_id,
                                messages=messages,
                                session_id=run_id,
                                user_language=user_language,
                            )
                            debug_metrics["interest_profile"] = interest_detection

                            logger.debug(
                                "debug_metrics_interest_detection_added",
                                run_id=run_id,
                                enabled=interest_detection.get("enabled", False),
                                analyzed=interest_detection.get("analyzed", False),
                                extracted_count=len(
                                    interest_detection.get("extracted_interests", [])
                                ),
                            )
                        except (ImportError, ValueError, RuntimeError) as interest_err:
                            logger.debug(
                                "debug_metrics_interest_detection_failed",
                                run_id=run_id,
                                error=str(interest_err),
                                error_type=type(interest_err).__name__,
                            )

                    # =============================================================
                    # Memory Detection: Show memories extracted from this message
                    # =============================================================
                    # Retrieves debug data cached by extract_memories_background()
                    # which has already completed (awaited via await_run_id_tasks).
                    if run_id:
                        try:
                            from src.domains.agents.services.memory_extractor import (
                                get_memory_extraction_debug,
                            )

                            memory_detection = get_memory_extraction_debug(run_id)
                            if memory_detection:
                                debug_metrics["memory_detection"] = memory_detection

                                logger.debug(
                                    "debug_metrics_memory_detection_added",
                                    run_id=run_id,
                                    enabled=memory_detection.get("enabled", False),
                                    extracted_count=len(
                                        memory_detection.get("extracted_memories", [])
                                    ),
                                )
                        except (ImportError, ValueError, RuntimeError) as mem_det_err:
                            logger.debug(
                                "debug_metrics_memory_detection_failed",
                                run_id=run_id,
                                error=str(mem_det_err),
                                error_type=type(mem_det_err).__name__,
                            )

                    logger.debug(
                        "debug_metrics_sections_added",
                        run_id=run_id,
                        has_tool_selection="tool_selection" in debug_metrics,
                        has_planner_intelligence="planner_intelligence" in debug_metrics,
                        has_token_budget="token_budget" in debug_metrics,
                        has_llm_calls="llm_calls" in debug_metrics,
                        has_interest_profile="interest_profile" in debug_metrics,
                        has_memory_injection="memory_injection" in debug_metrics,
                        has_memory_detection="memory_detection" in debug_metrics,
                    )

                    # Emit debug_metrics chunk
                    debug_chunk = ChatStreamChunk(
                        type="debug_metrics",
                        content="",
                        metadata=debug_metrics,
                    )
                    yield (debug_chunk, "")

                    logger.debug(
                        "debug_metrics_emitted_at_end",
                        run_id=run_id,
                        tool_selection_present="tool_selection" in debug_metrics,
                        tool_scores_count=len(
                            debug_metrics.get("tool_selection", {}).get("all_scores", {})
                        ),
                        selected_tools_count=len(
                            debug_metrics.get("tool_selection", {}).get("selected_tools", [])
                        ),
                    )
                else:
                    logger.warning(
                        "debug_metrics_skipped",
                        run_id=run_id,
                        has_cached_query_intelligence=False,
                    )
            except (ImportError, ValueError, KeyError, TypeError, AttributeError) as e:
                logger.warning(
                    "debug_metrics_final_emission_failed",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

    async def _emit_post_stream_registry(
        self, state: dict[Any, Any], sent_registry_ids: set[str], run_id: str
    ) -> AsyncGenerator[tuple[ChatStreamChunk, str], None]:
        """Emit the post-streaming ``registry_update`` chunk for the final state.

        Data Registry LOT 5.2 BugFix (2025-11-26): the registry is added to state by
        task_orchestrator_node AFTER the node executes; with stream_mode
        ["values", "messages"] there is no "__end__" chunk, so the final registry is
        emitted here from the accumulated ``state``. Uses current_turn_registry
        (filtered) with a fallback to the full registry for DISPLAY, and
        current_turn_registry ONLY for VOICE. Mutates ``sent_registry_ids`` and
        ``self.voice_context_registry`` exactly as the inline version did.
        """
        if state:
            # For DISPLAY: Prefer current_turn_registry, fallback to full registry
            # For VOICE: ONLY use current_turn_registry (no fallback)
            # This ensures chat mode (no tools) gets Direct TTS, not Voice LLM
            current_turn_registry = state.get("current_turn_registry")
            display_registry = current_turn_registry or state.get("registry")

            if display_registry:
                # Find new items not yet sent (for display)
                new_items = {
                    item_id: item
                    for item_id, item in display_registry.items()
                    if item_id not in sent_registry_ids
                }

                if new_items:
                    # Serialize items for SSE (DRY: use shared helper)
                    serialized_items = _serialize_registry_items(new_items)

                    # Store registry for voice context (fallback if not captured early)
                    # CRITICAL: Only use current_turn_registry for voice, NOT fallback registry
                    # This ensures chat mode (no tools executed) goes to Direct TTS path
                    # instead of Voice LLM (which would comment on stale registry data)
                    if not self.voice_context_registry and current_turn_registry:
                        # Filter serialized items to only include current turn items
                        current_turn_ids = set(current_turn_registry.keys())
                        voice_items = {
                            k: v for k, v in serialized_items.items() if k in current_turn_ids
                        }
                        if voice_items:
                            self.voice_context_registry = voice_items
                            logger.debug(
                                "voice_context_registry_set_post_streaming",
                                registry_items_count=len(voice_items),
                                source="current_turn_only",
                            )

                    # Emit registry_update chunk
                    registry_chunk = self.format_registry_update_chunk(serialized_items)

                    # Track metrics
                    event_type = _get_chunk_event_type(registry_chunk.type)
                    langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

                    yield (registry_chunk, "")

                    # Update sent IDs
                    sent_registry_ids.update(new_items.keys())

                    logger.info(
                        "data_registry_update_emitted_post_streaming",
                        run_id=run_id,
                        new_items_count=len(new_items),
                        total_sent=len(sent_registry_ids),
                        registry_ids=list(new_items.keys()),
                    )
                else:
                    logger.debug(
                        "data_registry_no_new_items_to_emit",
                        run_id=run_id,
                        registry_items_count=len(display_registry),
                        already_sent_count=len(sent_registry_ids),
                    )

    def _process_values_chunk(
        self,
        chunk: dict,
        last_sent_routing: Any,
    ) -> list[tuple[ChatStreamChunk, str]]:
        """
        Process mode="values" state update.

        Orchestrates processing via focused helper methods (SRP refactoring).
        Each helper handles a single responsibility:
        - _track_agent_results_change: Detect task_orchestrator completion
        - _capture_voice_context_registry: Early registry capture for parallel voice
        - _extract_router_decision: Build router_decision SSE chunk
        - _cache_debug_data: Cache debug panel data

        Args:
            chunk: State dict with routing_history, messages, registry, etc.
            last_sent_routing: Last router decision sent (to avoid duplicates)

        Returns:
            List of (SSE chunk, content) tuples
        """
        sse_chunks: list[tuple[ChatStreamChunk, str]] = []

        # 0. Snapshot the latest state.messages so api/service.py can compute the
        # context-usage indicator (tokens vs compaction threshold) when emitting
        # the SSE `done` chunk. Cheap reference assignment; never copies.
        latest_messages = chunk.get("messages")
        if latest_messages is not None:
            self.latest_state_messages = latest_messages

        # 1. Track agent_results changes to detect task_orchestrator completion
        agent_results_changed = self._track_agent_results_change(chunk)

        # 1b. Track routing_history changes to detect router_node completion in the
        # current turn (suppresses stale router_decision emission from checkpoint —
        # see _track_routing_history_change for the bug context).
        routing_history_changed = self._track_routing_history_change(chunk)

        # 2. Capture voice context registry (for parallel voice generation)
        self._capture_voice_context_registry(chunk, agent_results_changed)

        # 3. Extract router decision if new AND fresh (current-turn entry)
        router_chunk = self._extract_router_decision(
            chunk, last_sent_routing, routing_history_changed
        )
        if router_chunk:
            sse_chunks.append(router_chunk)
            # Reset skill tracking at the start of a new turn.
            # The graph checkpoint state (first values chunk) may contain a stale
            # planning_result with skill_name from the previous turn. Resetting here
            # (on the first new router decision) ensures the indicator is cleared before
            # any new planning_result is processed for the current turn.
            self.activated_skill_name = None

        # 4. Cache debug panel data (query_intelligence, tool_scores, filtered_catalogue)
        self._cache_debug_data(chunk)

        # 5. Capture activated skill name for the done-chunk metadata.
        # NOT debug-gated: the skill badge on the assistant message is a
        # user-facing feature (api/service.py puts it in done metadata for
        # every user), so it must not depend on the debug panel flag.
        self._capture_activated_skill(chunk)

        return sse_chunks

    def _track_agent_results_change(self, chunk: dict) -> bool:
        """
        Track agent_results to detect task_orchestrator completion.

        agent_results is populated by task_orchestrator_node. When it CHANGES from
        the checkpoint value, we know task_orchestrator has run and current_turn_registry
        contains FRESH data (not stale checkpoint data from previous turn).

        Args:
            chunk: State dict containing agent_results

        Returns:
            True if agent_results changed from checkpoint (task_orchestrator ran)
        """
        agent_results = chunk.get("agent_results", {})
        current_agent_results_ids = (
            frozenset(agent_results.keys()) if agent_results else frozenset()
        )

        # First chunk: store checkpoint value for comparison
        if self._checkpoint_agent_results_ids is None:
            self._checkpoint_agent_results_ids = current_agent_results_ids
            logger.debug(
                "voice_checkpoint_agent_results_stored",
                checkpoint_ids_count=len(self._checkpoint_agent_results_ids),
            )

        # Detect if agent_results changed (task_orchestrator ran)
        return current_agent_results_ids != self._checkpoint_agent_results_ids

    @staticmethod
    def _routing_history_signature(routing_history: list[Any]) -> tuple[Any, ...]:
        """Build a stable signature of routing_history for stale-detection.

        Combines length with identifying attributes of the last RouterOutput.
        Uses attribute access (not id()) so the signature survives LangGraph
        checkpoint serialization, which discards Python object identity.

        Args:
            routing_history: Current routing_history list from state.

        Returns:
            Tuple suitable for equality comparison.
        """
        if not routing_history:
            return (0, None, None, None, None)
        last = routing_history[-1]
        return (
            len(routing_history),
            getattr(last, "intention", None),
            getattr(last, "confidence", None),
            getattr(last, "next_node", None),
            getattr(last, "context_label", None),
        )

    def _track_routing_history_change(self, chunk: dict) -> bool:
        """Detect whether routing_history was updated in the current turn.

        Symmetric to ``_track_agent_results_change``. Required because LangGraph
        emits the checkpoint state at turn start — routing_history[-1] then
        references the previous turn's RouterOutput. Suppressing router_decision
        emission until the signature changes prevents downstream consumers
        (notably the chat_voice_streamer started on intention="conversation")
        from acting on stale routing data.

        Args:
            chunk: State dict containing routing_history.

        Returns:
            True if routing_history changed from the captured checkpoint
            (router_node has run in the current turn).
        """
        routing_history = chunk.get("routing_history") or []
        current_signature = self._routing_history_signature(routing_history)

        if self._checkpoint_routing_signature is None:
            self._checkpoint_routing_signature = current_signature
            logger.debug(
                "voice_checkpoint_routing_signature_stored",
                signature=current_signature,
            )

        return current_signature != self._checkpoint_routing_signature

    def _capture_voice_context_registry(self, chunk: dict, agent_results_changed: bool) -> None:
        """
        Capture current_turn_registry for early parallel voice generation.

        current_turn_registry is ONLY set by task_orchestrator_node for the
        CURRENT turn. We capture it here to enable parallel voice generation
        BEFORE response_node finishes streaming.

        NOTE: We do NOT emit registry from values chunks (BugFix 2025-11-26).
        The registry in values chunks comes from LangGraph checkpoint (stale).
        FRESH registry is emitted from "__end__" chunk only.

        Args:
            chunk: State dict containing current_turn_registry and registry
            agent_results_changed: Whether task_orchestrator has run
        """
        current_turn_registry = chunk.get("current_turn_registry")

        # Calculate agent_results count for diagnostic logging
        agent_results = chunk.get("agent_results", {})
        current_agent_results_count = len(agent_results) if agent_results else 0

        # DEBUG: Log what we receive to diagnose parallel voice timing
        if current_turn_registry or chunk.get("registry"):
            logger.debug(
                "voice_parallel_registry_check",
                has_current_turn_registry=bool(current_turn_registry),
                current_turn_registry_count=(
                    len(current_turn_registry) if current_turn_registry else 0
                ),
                has_registry=bool(chunk.get("registry")),
                voice_context_already_set=bool(self.voice_context_registry),
                agent_results_changed=agent_results_changed,
                current_agent_results_count=current_agent_results_count,
                chunk_keys=list(chunk.keys())[:10],
            )

        # CRITICAL: Only capture when agent_results has CHANGED from checkpoint
        # This indicates task_orchestrator has run and current_turn_registry is FRESH
        if current_turn_registry and not self.voice_context_registry and agent_results_changed:
            self.voice_context_registry = _serialize_registry_items(current_turn_registry)
            logger.info(
                "voice_context_registry_captured_early",
                registry_items_count=len(self.voice_context_registry),
                registry_ids=list(self.voice_context_registry.keys())[:5],
                trigger="agent_results_changed",
                current_agent_results_count=current_agent_results_count,
            )
        elif (
            current_turn_registry and not self.voice_context_registry and not agent_results_changed
        ):
            logger.debug(
                "voice_context_registry_skipped_stale",
                registry_items_count=len(current_turn_registry),
                reason="agent_results_unchanged_task_orchestrator_not_run",
                checkpoint_ids_count=(
                    len(self._checkpoint_agent_results_ids)
                    if self._checkpoint_agent_results_ids
                    else 0
                ),
            )

        # Log skipped registry (checkpoint data - will emit fresh from __end__)
        registry = chunk.get("registry")
        if registry:
            logger.debug(
                "data_registry_in_values_chunk_skipped",
                registry_items_count=len(registry),
                registry_ids=list(registry.keys())[:5],
                reason="checkpoint_data_will_emit_fresh_from_end",
            )

    def _extract_router_decision(
        self,
        chunk: dict,
        last_sent_routing: Any,
        routing_history_changed: bool,
    ) -> tuple[ChatStreamChunk, str] | None:
        """
        Extract router decision from routing_history if new and fresh.

        Args:
            chunk: State dict containing routing_history
            last_sent_routing: Last router decision sent (to avoid duplicates)
            routing_history_changed: False while routing_history[-1] still matches
                the checkpoint captured at turn start (stale entry from previous
                turn). Suppresses emission until router_node has appended a fresh
                RouterOutput in the current turn.

        Returns:
            (ChatStreamChunk, "") tuple if new router decision, None otherwise
        """
        # Suppress emission while routing_history[-1] still references the
        # previous turn's RouterOutput surfaced by the checkpoint replay.
        if not routing_history_changed:
            return None

        routing_history = chunk.get("routing_history", [])
        if not routing_history or routing_history[-1] == last_sent_routing:
            return None

        last_routing = routing_history[-1]

        # Build router metadata dict
        router_metadata_dict = {
            "intention": last_routing.intention,
            "confidence": last_routing.confidence,
            "context_label": last_routing.context_label,
            "next_node": last_routing.next_node,
            "reasoning": last_routing.reasoning,
        }

        return (
            ChatStreamChunk(
                type="router_decision",
                content="Routing decision made",
                metadata=router_metadata_dict,
            ),
            "",  # No content for router decisions
        )

    def _cache_debug_data(self, chunk: dict) -> None:
        """
        Cache debug panel data for final emission at end of stream.

        Caches query_intelligence, tool_selection_result, and filtered_catalogue.
        Actual debug_metrics emission happens in stream_sse_chunks() when
        ALL data is guaranteed available.

        Controlled by admin setting (fetched once at stream start), NOT settings.debug.

        Args:
            chunk: State dict containing debug data to cache
        """
        try:
            if not self._debug_panel_enabled:
                return

            # Cache query_intelligence
            # CRITICAL: Always update when dict is present (authoritative source)
            query_intelligence_dict = chunk.get("query_intelligence")
            if query_intelligence_dict and isinstance(query_intelligence_dict, dict):
                from src.domains.agents.analysis.query_intelligence_helpers import (
                    reconstruct_query_intelligence,
                )

                try:
                    self._cached_query_intelligence = reconstruct_query_intelligence(
                        query_intelligence_dict
                    )
                    logger.debug(
                        "debug_cache_query_intelligence",
                        source="dict",
                        route_to=self._cached_query_intelligence.route_to,
                        domains=self._cached_query_intelligence.domains,
                    )
                except (ValueError, KeyError, TypeError, AttributeError) as e:
                    logger.warning(
                        "debug_cache_query_intelligence_reconstruction_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                    )

            # Cache tool_selection_result
            tool_selection_result = chunk.get("tool_selection_result")
            if tool_selection_result:
                self._cached_tool_scores = tool_selection_result
                logger.debug(
                    "debug_cache_tool_scores",
                    tools_count=len(tool_selection_result.get("all_scores", {})),
                )

            # Cache filtered_catalogue from planning_result
            # (skill_name capture moved to _capture_activated_skill — it is a
            # user-facing feature and must not be gated by the debug panel)
            planning_result = chunk.get("planning_result")
            if planning_result and hasattr(planning_result, "filtered_catalogue"):
                if planning_result.filtered_catalogue:
                    self._cached_filtered_catalogue = planning_result.filtered_catalogue
                    logger.debug(
                        "debug_cache_filtered_catalogue",
                        tools_count=len(planning_result.filtered_catalogue.tools),
                    )

        except (ImportError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
            # Fail silently - debug metrics should not break streaming
            logger.warning(
                "debug_metrics_cache_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

    def _capture_activated_skill(self, chunk: dict) -> None:
        """Capture the activated skill name from planning_result (all users).

        Feeds the ``skill_name`` field of the SSE done metadata (frontend
        badge). Runs on every values chunk, unconditionally — unlike
        ``_cache_debug_data`` this is NOT gated by the debug panel flag.

        Guard against stale planning_result from the previous turn: the plan
        persists in LangGraph state when the current turn skips the planner
        (route=response). Only trust plan.metadata.skill_name when this turn
        actually routed through the planner (state.query_intelligence.route_to).
        Stale captures from the checkpoint chunk are cleared by the
        activated_skill_name reset on fresh router decisions.

        Args:
            chunk: State dict from the "values" stream mode.
        """
        try:
            # ReAct mode never runs the planner: planning_result in state is a
            # leftover from a previous pipeline turn (route_to only knows
            # "planner"/"response", so it cannot discriminate) — never trust it
            # here. The legitimate ReAct badge comes from the Route 3 fallback
            # (activate_skill_tool calls detected in the turn's messages).
            if chunk.get("execution_mode") == "react":
                return

            planning_result = chunk.get("planning_result")
            plan = getattr(planning_result, "plan", None) if planning_result else None
            if not (plan and hasattr(plan, "metadata")):
                return
            skill_name = plan.metadata.get("skill_name")

            query_intelligence = chunk.get("query_intelligence")
            route_to = (
                query_intelligence.get("route_to")
                if isinstance(query_intelligence, dict)
                else getattr(query_intelligence, "route_to", None)
            )
            if route_to == "planner":
                # Always mirror the CURRENT plan (including None): a fresh plan
                # without skill_name must clear a value captured earlier in the
                # turn from the stale checkpoint plan — otherwise the previous
                # turn's skill badge would survive on a skill-less planner turn.
                self.activated_skill_name = skill_name
            elif skill_name:
                logger.debug(
                    "stale_planning_result_skill_ignored",
                    stale_skill_name=skill_name,
                    route_to=route_to,
                )
        except (KeyError, TypeError, AttributeError) as e:
            # Best-effort capture — never break streaming for a badge
            logger.debug(
                "activated_skill_capture_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

    def resolve_activated_skill_name(self, state: dict | None = None) -> str | None:
        """Resolve the activated skill name, with Route 3 tool-call fallback.

        Route 3 (conversation fallback): when the response LLM called
        ``activate_skill_tool`` directly (no planner), the tool call is in the
        state messages. Scope: current turn only — the scan stops at the last
        HumanMessage so activate_skill_tool calls from previous turns don't
        surface a stale skill badge.

        Args:
            state: Optional state dict to read messages from. Falls back to
                the latest "values" snapshot (``latest_state_messages``).

        Returns:
            The activated skill name, or None if no skill was activated.
        """
        if self.activated_skill_name:
            return self.activated_skill_name

        messages = state.get("messages") if state else None
        if messages is None:
            messages = self.latest_state_messages
        if not messages:
            return None

        from langchain_core.messages import HumanMessage

        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                break
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                if isinstance(tc, dict) and tc.get("name") == "activate_skill_tool":
                    skill_from_tool = tc.get("args", {}).get("name")
                    if skill_from_tool:
                        self.activated_skill_name = skill_from_tool
                        return self.activated_skill_name

        return self.activated_skill_name

    # ============================================================================
    # "updates" mode processing — Pipeline + ReAct step detection
    # ============================================================================

    def _process_updates_chunk(
        self,
        chunk: dict[str, Any],
        accumulated_state: dict[str, Any],
    ) -> list[tuple[ChatStreamChunk, str]]:
        """
        Process mode="updates" node completion.

        "updates" mode yields {node_name: state_delta} after each node completes,
        regardless of which state keys the node updates. This enables execution_step
        emission for ALL nodes (pipeline + ReAct).

        For ReAct: extracts per-tool details from react_call_model's AIMessage.
        For Pipeline: extracts tool names from execution_plan when task_orchestrator completes.

        Args:
            chunk: Dict with single key = node_name, value = state delta.
            accumulated_state: Full state accumulated from "values" mode (from previous nodes).

        Returns:
            List of (SSE chunk, "") tuples for execution_step events.
        """
        sse_chunks: list[tuple[ChatStreamChunk, str]] = []

        if not chunk:
            return sse_chunks

        node_name = next(iter(chunk))
        state_delta = chunk[node_name]

        # Skip LangGraph internal nodes
        if node_name in ("__start__", "__end__"):
            return sse_chunks

        # Guard: state_delta must be a dict.
        # LangGraph normalises an empty-dict return from a node into ``None`` in
        # ``stream_mode="updates"`` (cf. ``langgraph.pregel._io.map_output_updates``):
        # nodes that ran without producing channel writes yield ``{node_name: None}``.
        # That is the expected no-op signal — we still emit the node-level step
        # but at debug level. Anything else (list, str, ...) is a real anomaly
        # and stays at warning.
        if state_delta is None:
            logger.debug(
                "updates_mode_node_no_op",
                node_name=node_name,
            )
            node_step = self._emit_execution_step(node_name)
            if node_step:
                sse_chunks.append((node_step, ""))
            return sse_chunks
        if not isinstance(state_delta, dict):
            logger.warning(
                "updates_mode_non_dict_state_delta",
                node_name=node_name,
                state_delta_type=type(state_delta).__name__,
            )
            # Still emit node-level step (no enrichment possible)
            node_step = self._emit_execution_step(node_name)
            if node_step:
                sse_chunks.append((node_step, ""))
            return sse_chunks

        # --- Node-level execution_step ---
        # NOTE (reasoning streaming): react_call_model now streams its live
        # chain-of-thought through the dedicated "reasoning" custom channel
        # (see infrastructure/llm/reasoning_stream.py + react_nodes.py). The
        # post-hoc ``_extract_react_enrichment`` detail (read from the final
        # AIMessage content in "updates" mode) is intentionally NOT attached
        # here anymore, to avoid showing the reasoning twice (live block +
        # trailing detail). The node-level step (emoji/label) is still emitted.
        node_step = self._emit_execution_step(node_name)
        if node_step:
            sse_chunks.append((node_step, ""))

        # --- Per-tool execution_steps ---
        if node_name == "react_call_model":
            # ReAct: extract tool names from AIMessage.tool_calls
            tool_steps = self._extract_react_tool_steps(state_delta)
            sse_chunks.extend(tool_steps)
        elif node_name == "task_orchestrator":
            # Pipeline: extract tool names from execution_plan (set by planner)
            tool_steps = self._extract_pipeline_tool_steps(accumulated_state)
            sse_chunks.extend(tool_steps)

        logger.debug(
            "updates_chunk_processed",
            node_name=node_name,
            steps_emitted=len(sse_chunks),
        )

        return sse_chunks

    def _extract_react_enrichment(self, state_delta: dict[str, Any]) -> dict[str, Any] | None:
        """
        Extract reasoning detail from react_call_model's AIMessage.

        DEPRECATED (reasoning streaming): no longer called from the hot path.
        react_call_model now streams its live chain-of-thought via the dedicated
        "reasoning" custom channel (infrastructure/llm/reasoning_stream.py), which
        supersedes this post-hoc single-detail extraction. Kept for now to allow a
        quick revert if live reasoning streaming is disabled; remove once the
        feature is confirmed stable in production.

        Args:
            state_delta: State delta from react_call_model containing messages.

        Returns:
            Dict with "detail" key if reasoning found, None otherwise.
        """
        from langchain_core.messages import AIMessage

        messages = state_delta.get("messages", [])
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.content:
                detail = self._extract_reasoning_detail(msg.content)
                if detail:
                    logger.debug(
                        "react_reasoning_detail_extracted",
                        detail_length=len(detail),
                    )
                    return {"detail": detail}
        return None

    def _extract_react_tool_steps(
        self, state_delta: dict[str, Any]
    ) -> list[tuple[ChatStreamChunk, str]]:
        """
        Extract per-tool execution_step events from react_call_model's AIMessage.

        When the ReAct LLM decides to call tools, emit individual execution_step
        events for each tool using the catalogue's DisplayMetadata.

        Args:
            state_delta: State delta from react_call_model containing messages.

        Returns:
            List of (ChatStreamChunk, "") tuples for each tool.
        """
        from langchain_core.messages import AIMessage

        tool_steps: list[tuple[ChatStreamChunk, str]] = []
        messages = state_delta.get("messages", [])

        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_name = tc.get("name", "")
                    if tool_name:
                        tool_chunk = self._emit_tool_execution_step(tool_name)
                        if tool_chunk:
                            tool_steps.append((tool_chunk, ""))

        if tool_steps:
            logger.debug(
                "react_tool_steps_extracted",
                tool_count=len(tool_steps),
            )

        return tool_steps

    def _extract_pipeline_tool_steps(
        self, accumulated_state: dict[str, Any]
    ) -> list[tuple[ChatStreamChunk, str]]:
        """
        Extract per-tool execution_step events from the pipeline execution plan.

        When task_orchestrator completes, the execution_plan (set by planner) contains
        the list of tools that were executed. Emit an execution_step for each TOOL-type
        step using the catalogue's DisplayMetadata.

        Args:
            accumulated_state: Full state from "values" mode containing execution_plan.

        Returns:
            List of (ChatStreamChunk, "") tuples for each tool in the plan.
        """
        tool_steps: list[tuple[ChatStreamChunk, str]] = []

        execution_plan = accumulated_state.get("execution_plan")
        if not execution_plan:
            return tool_steps

        # ExecutionPlan.steps is a list of ExecutionStep objects
        steps = getattr(execution_plan, "steps", None)
        if not steps:
            return tool_steps

        seen_tools: set[str] = set()
        for step in steps:
            tool_name = getattr(step, "tool_name", None)
            if not tool_name or tool_name in seen_tools:
                continue
            seen_tools.add(tool_name)

            tool_chunk = self._emit_tool_execution_step(tool_name)
            if tool_chunk:
                tool_steps.append((tool_chunk, ""))

        if tool_steps:
            logger.debug(
                "pipeline_tool_steps_extracted",
                tool_count=len(tool_steps),
                tool_names=list(seen_tools),
            )

        return tool_steps

    def _extract_reasoning_detail(self, content: str | list[dict[str, Any]] | None) -> str | None:
        """
        Extract a truncated reasoning snippet from AIMessage content.

        Handles both OpenAI format (str) and Anthropic format (list of content blocks).

        Args:
            content: AIMessage.content — str or list[dict] (Anthropic content blocks).

        Returns:
            Truncated reasoning text (max 120 chars) or None if empty.
        """
        if not content:
            return None

        # Normalize str (most providers) and list[dict] blocks (Gemini 3.x/Anthropic).
        text = coerce_content_to_text(content)
        if not text or not text.strip():
            return None

        # Strip markdown formatting
        text = re.sub(r"[*#`_~]", "", text).strip()
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            return None

        # Truncate to 120 chars
        if len(text) > 120:
            text = text[:117] + "..."

        return text

    def _emit_tool_execution_step(self, tool_name: str) -> ChatStreamChunk | None:
        """
        Emit execution_step event for a specific tool call.

        Uses the tool catalogue's DisplayMetadata for emoji and i18n_key.
        Falls back to generic tool execution metadata if not in catalogue.

        Args:
            tool_name: Tool name from AIMessage.tool_calls (e.g., "get_contacts_tool").

        Returns:
            ChatStreamChunk with tool execution_step metadata, or None.
        """
        from src.domains.agents.utils.execution_metadata import build_execution_step_event

        # Try catalogue-based metadata first
        execution_event = build_execution_step_event(
            step_type="tool",
            step_name=tool_name,
            status="started",
        )

        if execution_event:
            return ChatStreamChunk(
                type="execution_step",
                content="",
                metadata=execution_event,
            )

        # Fallback: generic tool execution metadata for tools not in catalogue
        logger.debug(
            "tool_execution_step_fallback",
            tool_name=tool_name,
            reason="tool_not_in_catalogue",
        )
        return ChatStreamChunk(
            type="execution_step",
            content="",
            metadata={
                "type": "execution_step",
                "step_type": "tool",
                "step_name": tool_name,
                FIELD_STATUS: "started",
                "emoji": "⚙️",
                "i18n_key": "react_tool_execution",
                "category": "tool",
            },
        )

    # ============================================================================
    # Context-usage pill — token count + compaction threshold for the SSE `done`
    # ============================================================================

    def compute_context_usage(self) -> dict[str, int] | None:
        """Return current context-usage stats for the SSE `done` metadata.

        Counts the tokens of the latest state.messages snapshot captured in
        `_process_values_chunk` and queries the same dynamic threshold that
        the compaction node uses (`CompactionService.compute_effective_threshold`).

        The frontend renders this as a small progress pill in the chat header
        bar (between the voice mode badge and the delete button).

        Returns:
            A dict with `context_tokens` and `context_threshold` keys, or None
            if no state snapshot is available yet (eg. very first turn with no
            persisted messages).
        """
        if not self.latest_state_messages:
            return None
        try:
            from src.domains.agents.services.compaction_service import (
                CompactionService,
            )

            service = CompactionService()
            tokens = service._token_counter.count_messages_tokens(self.latest_state_messages)
            threshold = service.compute_effective_threshold()
            return {
                "context_tokens": int(tokens),
                "context_threshold": int(threshold),
            }
        except Exception as e:
            # Best-effort: the pill is purely informational, never fail the
            # `done` chunk because of a counting hiccup.
            logger.debug("context_usage_compute_failed", error=str(e))
            return None

    # ============================================================================
    # "custom" mode processing — Node-emitted events (Day 2 / Task 2.1)
    # ============================================================================

    def _process_custom_chunk(
        self,
        chunk: Any,
    ) -> list[tuple[ChatStreamChunk, str]]:
        """
        Forward a node-emitted custom event as an SSE chunk.

        Nodes use `langgraph.config.get_stream_writer()` to push dicts shaped
        like:

            {
                "type": "execution_step",
                "step_type": "compaction",
                "step_label": "compaction_start",
                "metadata": {"phase": "start", "estimated_duration_seconds": 30},
            }

        ChatStreamChunk does not expose `step_type`/`step_label` as root fields
        (see api/schemas.py); we therefore merge them into the `metadata` dict
        so the frontend can dispatch on `metadata.step_type` and
        `metadata.step_label` consistently with the existing execution_step
        events emitted by `_emit_execution_step`.

        Non-dict or malformed payloads are dropped with a warning to avoid
        propagating garbage into the SSE stream.
        """
        if not isinstance(chunk, dict):
            logger.warning(
                "custom_mode_non_dict_chunk",
                chunk_type=type(chunk).__name__,
            )
            return []

        chunk_type = chunk.get("type", "execution_step")
        metadata = chunk.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        # Fold step_type / step_label into metadata to fit the ChatStreamChunk
        # contract (root-level type/content/metadata only).
        merged_metadata: dict[str, Any] = dict(metadata)
        if chunk.get("step_type") is not None:
            merged_metadata.setdefault("step_type", chunk["step_type"])
        if chunk.get("step_label") is not None:
            merged_metadata.setdefault("step_label", chunk["step_label"])

        sse_chunk = ChatStreamChunk(
            type=chunk_type,
            content="",
            metadata=merged_metadata,
        )
        return [(sse_chunk, "")]

    # ============================================================================
    # "messages" mode processing — Token streaming
    # ============================================================================

    def _process_messages_chunk(
        self,
        message_tuple: tuple,
        _state: dict,
        _first_token_time: float | None,
    ) -> list[tuple[ChatStreamChunk, str]]:
        """
        Process mode="messages" message update.

        Streams tokens from response node only. Node transition detection is
        handled by _process_updates_chunk() via "updates" stream mode.

        Args:
            message_tuple: (message, metadata) tuple from LangGraph
            _state: Current state dict
            _first_token_time: First token timestamp (None if not received yet)

        Returns:
            List of (SSE chunk, content) tuples
            - token events: (chunk, content_fragment)
        """
        sse_chunks: list[tuple[ChatStreamChunk, str]] = []

        # Unpack message tuple
        if not isinstance(message_tuple, tuple) or len(message_tuple) < 2:
            return sse_chunks

        message, metadata = message_tuple[0], message_tuple[1]

        # Extract node name from metadata
        node_name = metadata.get("langgraph_node") if metadata else None

        # Stream tokens ONLY from response node
        if node_name == "response" and self._should_stream_token(node_name):
            if hasattr(message, "content") and message.content:
                # Duplicate-display fix: LangGraph "messages" mode emits BOTH the LLM's
                # streaming token deltas (AIMessageChunk) AND the complete AIMessage the
                # response node returns to the ``messages`` channel after post-processing.
                # Streaming that complete message after the deltas reproduces the whole
                # reply a second time on screen — the "double then single" flash, since the
                # post-loop content_replacement then collapses it back to one copy.
                #
                # Stream token deltas only. If the LLM never streamed (non-streaming
                # provider), no delta was seen and the complete message is the only content
                # we have — emit it once. The canonical post-processed content (HTML cards,
                # psyche-tag cleanup) is still delivered by the content_replacement chunk
                # emitted after the loop when post-processing modified the text.
                # NOTE: replaces the former ``content_final_replacement`` guard, which could
                # never fire for the current turn (the flag is set by the response node only
                # AFTER its own tokens have already streamed).
                if isinstance(message, AIMessageChunk):
                    self._response_deltas_streamed = True
                elif self._response_deltas_streamed:
                    logger.debug(
                        "response_duplicate_message_skipped",
                        message_type=type(message).__name__,
                    )
                    return sse_chunks  # Complete returned message = duplicate; skip it.

                # Gemini 3.x streams content as list[dict] blocks; normalize to
                # text so the psyche check below and ChatStreamChunk stay str-safe.
                content = coerce_content_to_text(message.content)

                # Psyche Engine: Strip psyche_eval tag fragments from streaming tokens
                # Prevents brief flash of the tag during SSE streaming.
                # The content_replacement chunk handles full cleanup after response_node.
                if "<psyche_eval" in content or "psyche_eval" in content:
                    from src.domains.psyche.constants import PSYCHE_EVAL_STREAMING_PATTERN

                    content = PSYCHE_EVAL_STREAMING_PATTERN.sub("", content).strip()
                    if not content:
                        return sse_chunks  # Skip empty chunk after tag removal

                token_chunk = self.format_token_chunk(content)
                sse_chunks.append((token_chunk, content))

        return sse_chunks

    def _emit_execution_step(
        self,
        node_name: str,
        additional_data: dict | None = None,
    ) -> ChatStreamChunk | None:
        """
        Emit execution_step event for node transition.

        Args:
            node_name: Name of the node (router, planner, response, etc.)
            additional_data: Optional extra fields (e.g., {"detail": "reasoning..."})

        Returns:
            ChatStreamChunk with execution_step metadata or None if not visible
        """
        from src.domains.agents.utils.execution_metadata import build_execution_step_event

        execution_event = build_execution_step_event(
            step_type="node",
            step_name=node_name,
            status="started",
            additional_data=additional_data,
        )

        if execution_event:
            return ChatStreamChunk(
                type="execution_step",
                content="",
                metadata=execution_event,
            )

        return None

    def _should_stream_token(self, node_name: str) -> bool:
        """
        Check if tokens should be streamed from this node.

        Args:
            node_name: Name of the node

        Returns:
            True if tokens should be streamed, False otherwise
        """
        # Only stream tokens from response node
        return node_name == "response"

    def format_token_chunk(self, content: str | list[Any]) -> ChatStreamChunk:
        """
        Format token for SSE streaming.

        Coerces Gemini 3.x list[dict] content blocks to text so the
        ``ChatStreamChunk.content`` (str | dict) contract is never violated.
        This is the streaming chokepoint shared with the fallback-response path.

        Args:
            content: Token content (str, or Gemini 3.x list of content blocks)

        Returns:
            ChatStreamChunk with type="token"
        """
        return ChatStreamChunk(type="token", content=coerce_content_to_text(content))

    def format_router_decision(self, metadata: dict[str, Any]) -> ChatStreamChunk:
        """
        Format router decision for SSE streaming.

        Args:
            metadata: Router metadata dict

        Returns:
            ChatStreamChunk with type="router_decision"
        """
        return ChatStreamChunk(
            type="router_decision",
            content={
                "intention": metadata.get("intention"),
                "confidence": metadata.get("confidence"),
                "agents": metadata.get("agents", []),
            },
        )

    def format_done_chunk(
        self, final_message: str, metadata: dict[str, Any] | None = None
    ) -> ChatStreamChunk:
        """
        Format final "done" chunk.

        Args:
            final_message: Final assistant message
            metadata: Optional metadata (token summary, etc.)

        Returns:
            ChatStreamChunk with type="done"
        """
        return ChatStreamChunk(
            type="done",
            content={"message": final_message, FIELD_METADATA: metadata or {}},
        )

    def format_error_chunk(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
        language: str = "fr",
    ) -> ChatStreamChunk:
        """Format error chunk with user-friendly message.

        Never exposes raw exception types or messages to the end user.

        Args:
            error: Exception that occurred
            context: Optional error context
            language: User's language for localized message

        Returns:
            ChatStreamChunk with type="error" and sanitized message
        """
        from src.domains.agents.api.error_messages import SSEErrorMessages

        return ChatStreamChunk(
            type="error",
            content=SSEErrorMessages.stream_error(error, language=language),
        )

    def format_registry_update_chunk(self, registry_items: dict[str, Any]) -> ChatStreamChunk:
        """
        Format data registry update for SSE streaming.

        Data Registry Architecture: Registry updates are emitted as side-channel data
        BEFORE tokens, allowing frontend to resolve IDs in subsequent content.

        Args:
            registry_items: Dict mapping item_id → RegistryItem (serialized)

        Returns:
            ChatStreamChunk with type="registry_update"

        Example:
            >>> items = {"contact_abc123": {"id": "contact_abc123", "type": "CONTACT", ...}}
            >>> chunk = service.format_registry_update_chunk(items)
            >>> # SSE: {"type": "registry_update", "content": "", "metadata": {"items": {...}}}
        """
        return ChatStreamChunk(
            type="registry_update",
            content="",  # Empty content - data is in metadata
            metadata={
                "items": registry_items,
                "count": len(registry_items),
            },
        )

    async def _handle_hitl_interrupt(
        self,
        chunk: dict,
        conversation_id: uuid.UUID,
        run_id: str,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Handle HITL interrupt: emit chunks, archive message, store in Redis.

        Phase 1 HITL Streaming (OPTIMPLAN):
        When generate_question_streaming=True in interrupt_data, generates the
        question via true LLM streaming (astream()) for TTFT < 500ms.
        Otherwise, falls back to word split for backward compatibility.

        Data Registry LOT 4 Integration:
        Extracts registry_ids from state.registry and includes them in
        HITL metadata. Frontend uses these to render <LARSCard> components
        alongside the HITL question.

        Args:
            chunk: State dict containing __interrupt__ and registry
            conversation_id: Conversation UUID
            run_id: Unique run identifier

        Yields:
            ChatStreamChunk: HITL interrupt chunks

        Performance:
            - True LLM streaming: TTFT < 500ms
            - Fallback word split: TTFT depends on pre-generated question
        """
        # Import metrics locally to avoid circular imports
        from src.infrastructure.observability.metrics_agents import (
            hitl_streaming_fallback_total,
            registry_hitl_interrupts_total,
            registry_hitl_registry_items_per_interrupt,
        )

        interrupt_tuple = chunk.get("__interrupt__", [])
        if not interrupt_tuple or len(interrupt_tuple) == 0:
            return

        interrupt_obj = interrupt_tuple[0]
        interrupt_data = interrupt_obj.value
        action_requests = interrupt_data.get("action_requests", [])

        if not action_requests:
            return

        # Extract action metadata
        first_action = action_requests[0]
        action_type = first_action.get("type", "unknown")
        # One SSE message per interrupt: replay-safe HITL loops (ADR-092) emit a
        # NEW interrupt per user decision within the SAME run, so the message_id
        # must be unique per interrupt — the frontend keys the assistant bubble
        # on it (STREAM_START is idempotent: a reused id would overwrite the
        # previous bubble instead of creating a new one). The LangGraph
        # Interrupt.id is unique per interrupt and stable across re-emissions
        # of the same pending interrupt (e.g. SSE reconnection).
        interrupt_id = getattr(interrupt_obj, "id", None)
        if interrupt_id and interrupt_id != _LANGGRAPH_INTERRUPT_PLACEHOLDER_ID:
            message_id = f"hitl_{conversation_id}_{interrupt_id}"
        else:
            message_id = f"hitl_{conversation_id}_{run_id}"
        is_plan_approval = action_type == "plan_approval"

        # Phase 1 HITL Streaming: Check if streaming generation is requested
        generate_streaming = interrupt_data.get("generate_question_streaming", False)
        user_language = interrupt_data.get("user_language", settings.default_language)
        # Extract user_timezone from interrupt_data or fallback to state's user_timezone
        user_timezone = interrupt_data.get("user_timezone") or chunk.get(
            "user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE
        )

        # Data Registry LOT 4: Extract registry_ids from state for HITL metadata
        # Registry items are accumulated during tool execution
        registry = chunk.get("registry", {})
        registry_ids = list(registry.keys()) if registry else []

        # Data Registry LOT 4: Track HITL interrupt with registry context
        has_registry_items = len(registry_ids) > 0
        registry_hitl_interrupts_total.labels(
            type=action_type,
            has_registry_items=str(has_registry_items).lower(),
        ).inc()
        registry_hitl_registry_items_per_interrupt.labels(type=action_type).observe(
            len(registry_ids)
        )

        logger.info(
            "hitl_interrupt_detected_in_streaming_service",
            run_id=run_id,
            conversation_id=str(conversation_id),
            action_type=action_type,
            generate_streaming=generate_streaming,
            user_language=user_language,
            # Data Registry LOT 4: Log registry IDs count
            registry_ids_count=len(registry_ids),
            has_registry_items=has_registry_items,
        )

        # === Step 1: Build and emit metadata chunk ===
        # Phase 1 HITL Streaming: Use registry to build metadata if streaming
        # Data Registry LOT 4: Pass registry_ids to interaction for rich rendering
        if generate_streaming:
            try:
                hitl_registry = _get_hitl_registry()
                question_generator = _get_hitl_question_generator()
                interaction = hitl_registry.from_action_type(
                    action_type,
                    question_generator=question_generator,
                )
                # Use interaction to build metadata with proper structure
                # Data Registry LOT 4: Include registry_ids for frontend <LARSCard> rendering
                metadata = interaction.build_metadata_chunk(
                    context=first_action,
                    message_id=message_id,
                    conversation_id=str(conversation_id),
                    registry_ids=registry_ids,  # Data Registry LOT 4
                )
            except (ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
                logger.warning(
                    "hitl_streaming_metadata_build_failed_using_fallback",
                    error=str(e),
                    error_type=type(e).__name__,
                    action_type=action_type,
                )
                # Fallback to basic metadata
                # Data Registry LOT 4: Include registry_ids even in fallback
                metadata = {
                    "message_id": message_id,
                    FIELD_CONVERSATION_ID: str(conversation_id),
                    "action_requests": action_requests,
                    "count": len(action_requests),
                    "is_plan_approval": is_plan_approval,
                    "registry_ids": registry_ids,  # Data Registry LOT 4
                    "has_registry_items": len(registry_ids) > 0,
                }
        else:
            # Legacy behavior: basic metadata
            # Data Registry LOT 4: Include registry_ids for frontend rendering
            metadata = {
                "message_id": message_id,
                FIELD_CONVERSATION_ID: str(conversation_id),
                "action_requests": action_requests,
                "count": len(action_requests),
                "is_plan_approval": is_plan_approval,
                "registry_ids": registry_ids,  # Data Registry LOT 4
                "has_registry_items": len(registry_ids) > 0,
            }

        metadata_chunk = ChatStreamChunk(
            type="hitl_interrupt_metadata",
            content="",
            metadata=metadata,
        )

        # PHASE 2.5 - P5: Track HITL metadata chunk
        event_type = _get_chunk_event_type(metadata_chunk.type)
        langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

        yield metadata_chunk

        # === Step 2: Stream HITL question token by token ===
        generated_question = ""  # Track full question for later storage

        if generate_streaming:
            # Phase 1 HITL Streaming: True LLM streaming via registry
            try:
                hitl_registry = _get_hitl_registry()
                question_generator = _get_hitl_question_generator()
                interaction = hitl_registry.from_action_type(
                    action_type,
                    question_generator=question_generator,
                )

                # Stream tokens from LLM with token tracking.
                # self.tracker is a TrackingContext (not a LangChain callback),
                # so we wrap it in a TokenTrackingCallback for the HITL generator.
                # Without this, HITL question tokens are consumed but not tracked,
                # causing cost under-reporting (~€0.03/request on Anthropic models).
                hitl_tracker = None
                if self.tracker:
                    from src.infrastructure.observability.callbacks import (
                        TokenTrackingCallback,
                    )

                    hitl_tracker = TokenTrackingCallback(self.tracker, run_id)

                async for token in interaction.generate_question_stream(
                    context=first_action,
                    user_language=user_language,
                    user_timezone=user_timezone,
                    tracker=hitl_tracker,
                ):
                    generated_question += token

                    question_token_chunk = ChatStreamChunk(
                        type="hitl_question_token",
                        content=token,
                        metadata={"message_id": message_id},
                    )

                    # Track streaming chunk
                    event_type = _get_chunk_event_type(question_token_chunk.type)
                    langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

                    yield question_token_chunk

                logger.info(
                    "hitl_streaming_question_generated",
                    action_type=action_type,
                    question_length=len(generated_question),
                    run_id=run_id,
                )

            except asyncio.CancelledError:
                # Client disconnected — no point falling back, just propagate
                raise

            except (TimeoutError, RuntimeError, ValueError, OSError) as e:
                # Phase 1 HITL Streaming: Fallback on error
                error_type = type(e).__name__
                hitl_streaming_fallback_total.labels(type=action_type, error_type=error_type).inc()

                logger.warning(
                    "hitl_streaming_failed_using_fallback",
                    error=str(e),
                    error_type=error_type,
                    action_type=action_type,
                    run_id=run_id,
                )

                # Emit fallback event for frontend awareness
                fallback_event_chunk = ChatStreamChunk(
                    type="hitl_streaming_fallback",
                    content="",
                    metadata={
                        "message_id": message_id,
                        "error": "streaming_failed",
                        "error_type": error_type,
                    },
                )
                yield fallback_event_chunk

                # Get fallback question from interaction
                try:
                    fallback_question = interaction.get_fallback_question(user_language)
                except (AttributeError, KeyError, ValueError, RuntimeError):
                    # Ultimate fallback - uses centralized i18n (6 languages)
                    from src.domains.agents.api.error_messages import SSEErrorMessages

                    fallback_question = SSEErrorMessages.confirmation_required(
                        language=user_language  # type: ignore[arg-type]
                    )

                generated_question = fallback_question

                # Stream fallback question word by word (legacy behavior)
                for token in fallback_question.split():
                    question_token_chunk = ChatStreamChunk(
                        type="hitl_question_token",
                        content=token + " ",
                        metadata={"message_id": message_id},
                    )
                    event_type = _get_chunk_event_type(question_token_chunk.type)
                    langgraph_streaming_chunks_total.labels(event_type=event_type).inc()
                    yield question_token_chunk
        else:
            # Legacy behavior: word split on pre-generated question
            # Default uses centralized i18n (6 languages)
            from src.domains.agents.api.error_messages import SSEErrorMessages

            default_question = SSEErrorMessages.confirmation_required(
                language=user_language  # type: ignore[arg-type]
            )
            hitl_question = first_action.get("user_message", default_question)
            generated_question = hitl_question

            for token in hitl_question.split():
                question_token_chunk = ChatStreamChunk(
                    type="hitl_question_token",
                    content=token + " ",
                    metadata={"message_id": message_id},
                )

                # PHASE 2.5 - P5: Track HITL question token chunks
                event_type = _get_chunk_event_type(question_token_chunk.type)
                langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

                yield question_token_chunk

        # === Step 3: Signal completion ===
        # No token metadata in HITL interrupt chunk: tokens are partial (only
        # planner/router, not the full execution) and disappear on conversation reload.
        # Complete token counts are sent in the "done" chunk after HITL resumption.
        complete_chunk = ChatStreamChunk(
            type="hitl_interrupt_complete",
            content="",
            metadata={
                "message_id": message_id,
                "requires_approval": True,
                "generated_question": generated_question,
            },
        )

        # PHASE 2.5 - P5: Track HITL completion chunk
        event_type = _get_chunk_event_type(complete_chunk.type)
        langgraph_streaming_chunks_total.labels(event_type=event_type).inc()

        yield complete_chunk

        # === Step 4: Perform HITL operations (if dependencies available) ===
        if self.tracker:
            await self.tracker.commit()

        # Store the generated question for service.py to archive as assistant message
        # This ensures the HITL question appears in conversation history on reload
        self.hitl_generated_question = generated_question

        if self.hitl_store:
            await self.hitl_store.save_interrupt(
                thread_id=str(conversation_id),
                interrupt_data={
                    "action_requests": action_requests,
                    "count": len(action_requests),
                    FIELD_RUN_ID: run_id,
                    "interrupt_ts": str(time.time()),
                    # Phase 1 HITL Streaming: Store generated question for recovery
                    "generated_question": generated_question,
                },
            )

        logger.info(
            "hitl_interrupt_handled_in_streaming_service",
            run_id=run_id,
            action_type=action_type,
            is_plan_approval=is_plan_approval,
            generate_streaming=generate_streaming,
            question_length=len(generated_question),
            user_message_archived=self.conv_service is not None,
            pending_hitl_stored=self.hitl_store is not None,
        )

    def _add_debug_metrics_sections(
        self,
        debug_metrics: dict[str, Any],
        state: dict[str, Any],
        run_id: str,
        db_aggregated: Any | None = None,
    ) -> None:
        """
        Add all debug metrics sections to debug_metrics dict.

        This method is called at the END of streaming when ALL data is available.
        It builds token_budget, planner_intelligence, tool_selection, execution_timeline, and llm_calls.

        Delegates the section assembly to ``DebugMetricsBuilder`` (behavior-preserving
        extraction — same inputs, same in-place mutation, same section ordering).

        Args:
            debug_metrics: Base debug metrics dict (from query_intelligence.to_debug_metrics())
            state: Final state dict with all data
            run_id: Run ID for logging
            db_aggregated: Optional DB-aggregated token summary (includes prior HITL requests)
        """
        from src.domains.agents.services.streaming.debug_metrics_builder import (
            DebugMetricsBuilder,
        )

        DebugMetricsBuilder(
            tracker=self.tracker,
            cached_filtered_catalogue=self._cached_filtered_catalogue,
            cached_tool_scores=self._cached_tool_scores,
            skill_name_resolver=self.resolve_activated_skill_name,
        ).build(debug_metrics, state, run_id, db_aggregated)
