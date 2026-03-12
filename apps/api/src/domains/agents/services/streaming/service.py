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
import time
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from structlog import get_logger

from src.core.constants import DEFAULT_LANGUAGE, DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.field_names import (
    FIELD_CONVERSATION_ID,
    FIELD_ERROR_TYPE,
    FIELD_METADATA,
    FIELD_RUN_ID,
)
from src.domains.agents.api.schemas import ChatStreamChunk
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
        - router_decision, planner_metadata, execution_step → STREAM_METADATA
        - registry_update → STREAM_REGISTRY (Data Registry side-channel data)
        - hitl_* → STREAM_INTERRUPT
        - error → STREAM_ERROR
        - done → STREAM_COMPLETE
        - planner_error → STREAM_ERROR
    """
    if chunk_type == "token":
        return "STREAM_TOKEN"
    elif chunk_type == "content_replacement":
        return "STREAM_TOKEN"  # Final content is token-like
    elif chunk_type in ("router_decision", "planner_metadata", "execution_step"):
        return "STREAM_METADATA"
    elif chunk_type == "registry_update":
        return "STREAM_REGISTRY"  # Data Registry: Side-channel registry data
    elif chunk_type == "debug_metrics":
        return "STREAM_DEBUG"  # Debug Panel: Scoring metrics (DEBUG=true only)
    elif chunk_type.startswith("hitl_"):
        return "STREAM_INTERRUPT"
    elif chunk_type in ("error", "planner_error"):
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

                    # NO HITL - process normally
                    # Data Registry: Pass sent_registry_ids to track and emit registry updates
                    sse_chunks = self._process_values_chunk(
                        chunk, last_sent_routing, sent_registry_ids
                    )

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
                    # Message tuple - extract tokens and execution steps
                    # Type narrowing: LangGraph "messages" mode always emits tuple
                    if not isinstance(chunk, tuple):
                        logger.warning(
                            "messages_mode_non_tuple_chunk",
                            mode=mode,
                            chunk_type=type(chunk).__name__,
                            run_id=run_id,
                        )
                        continue

                    sse_chunks = self._process_messages_chunk(
                        chunk, state, last_emitted_node, first_token_time
                    )

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

                        # Track node transitions
                        if sse_chunk.type == "execution_step":
                            if sse_chunk.metadata:
                                node_name = sse_chunk.metadata.get("step_name")
                                if node_name:
                                    last_emitted_node = node_name

                        # Track token count and emit
                        if sse_chunk.type == "token":
                            token_count += 1
                            response_content += content_fragment

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

            # =========================================================================
            # Data Registry LOT 5.2 BugFix (2025-11-26): Emit registry_update AFTER streaming loop
            # =========================================================================
            # The registry is added to state by task_orchestrator_node AFTER the node
            # executes. Since we use stream_mode=["values", "messages"], there is NO
            # "__end__" chunk - the final state is captured in the last "values" chunk.
            #
            # We emit registry_update here, after the streaming loop completes, using
            # the accumulated `state` variable which contains the final graph state.
            # This ensures registry data is sent BEFORE the streaming officially ends.
            #
            # Note: Registry is emitted AFTER tokens to ensure consistency. The LLM
            # generates content with Markdown and the frontend
            # receives tokens + registry in the same stream. Frontend updates registry
            # state which triggers re-render of registry components.
            #
            # BugFix 2025-12-18: Use current_turn_registry (filtered) instead of full registry
            # The full registry is merged across all turns. For display purposes, we should
            # only send items from the current turn to avoid showing stale data.
            # Example: "detail of the second restaurant" was sending BOTH restaurants (2 items)
            # instead of just the requested one (1 item).
            # =========================================================================
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

            # =================================================================
            # Debug Panel: Emit debug_metrics ONCE at the end (all data available)
            # Skip entirely when panel is disabled (zero processing)
            # =================================================================
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

                        # Add all cached data
                        self._add_debug_metrics_sections(
                            debug_metrics=debug_metrics,
                            state=state,
                            run_id=run_id,
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
                                user_language = state.get("user_language", DEFAULT_LANGUAGE)

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

                        logger.debug(
                            "debug_metrics_sections_added",
                            run_id=run_id,
                            has_tool_selection="tool_selection" in debug_metrics,
                            has_planner_intelligence="planner_intelligence" in debug_metrics,
                            has_token_budget="token_budget" in debug_metrics,
                            has_llm_calls="llm_calls" in debug_metrics,
                            has_interest_profile="interest_profile" in debug_metrics,
                            has_memory_injection="memory_injection" in debug_metrics,
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

        except (TimeoutError, RuntimeError, ValueError, asyncio.CancelledError, OSError) as e:
            logger.error(
                "streaming_error",
                exc_info=True,
                run_id=run_id,
                conversation_id=str(conversation_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _process_values_chunk(
        self,
        chunk: dict,
        last_sent_routing: Any,
        sent_registry_ids: set[str] | None = None,
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
            sent_registry_ids: Set of registry IDs already sent (mutated in-place)

        Returns:
            List of (SSE chunk, content) tuples
        """
        sse_chunks: list[tuple[ChatStreamChunk, str]] = []

        # Initialize sent_registry_ids if not provided
        if sent_registry_ids is None:
            sent_registry_ids = set()

        # 1. Track agent_results changes to detect task_orchestrator completion
        agent_results_changed = self._track_agent_results_change(chunk)

        # 2. Capture voice context registry (for parallel voice generation)
        self._capture_voice_context_registry(chunk, agent_results_changed)

        # 3. Extract router decision if new
        router_chunk = self._extract_router_decision(chunk, last_sent_routing)
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
        self, chunk: dict, last_sent_routing: Any
    ) -> tuple[ChatStreamChunk, str] | None:
        """
        Extract router decision from routing_history if new.

        Args:
            chunk: State dict containing routing_history
            last_sent_routing: Last router decision sent (to avoid duplicates)

        Returns:
            (ChatStreamChunk, "") tuple if new router decision, None otherwise
        """
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

            # Cache filtered_catalogue and skill_name from planning_result
            planning_result = chunk.get("planning_result")
            if planning_result and hasattr(planning_result, "filtered_catalogue"):
                if planning_result.filtered_catalogue:
                    self._cached_filtered_catalogue = planning_result.filtered_catalogue
                    logger.debug(
                        "debug_cache_filtered_catalogue",
                        tools_count=len(planning_result.filtered_catalogue.tools),
                    )
                # Capture skill_name for done metadata (frontend badge)
                plan = getattr(planning_result, "plan", None)
                if plan and hasattr(plan, "metadata"):
                    skill_name = plan.metadata.get("skill_name")
                    if skill_name:
                        self.activated_skill_name = skill_name

        except (ImportError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
            # Fail silently - debug metrics should not break streaming
            logger.warning(
                "debug_metrics_cache_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

    def _process_messages_chunk(
        self,
        message_tuple: tuple,
        _state: dict,
        last_emitted_node: str | None,
        _first_token_time: float | None,
    ) -> list[tuple[ChatStreamChunk, str]]:
        """
        Process mode="messages" message update.

        Extracts node transitions and tokens from messages.

        Args:
            message_tuple: (message, metadata) tuple from LangGraph
            state: Current state dict
            last_emitted_node: Last node that emitted an execution_step
            first_token_time: First token timestamp (None if not received yet)

        Returns:
            List of (SSE chunk, content) tuples
            - execution_step events: (chunk, "")
            - token events: (chunk, content_fragment)
        """
        sse_chunks: list[tuple[ChatStreamChunk, str]] = []

        # Unpack message tuple
        if not isinstance(message_tuple, tuple) or len(message_tuple) < 2:
            return sse_chunks

        message, metadata = message_tuple[0], message_tuple[1]

        # Extract node name from metadata
        node_name = metadata.get("langgraph_node") if metadata else None

        # Emit execution_step for node transitions
        if node_name and node_name != last_emitted_node:
            execution_step = self._emit_execution_step(node_name)
            if execution_step:
                sse_chunks.append((execution_step, ""))

        # Stream tokens ONLY from response node
        if node_name == "response" and self._should_stream_token(node_name):
            if hasattr(message, "content") and message.content:
                # BugFix 2025-12-29: Skip replacement messages to avoid duplicate display
                # When content_final_replacement is set, this message is a post-processed
                # version (with injected photos, etc.) that will be sent via content_replacement
                # chunk after the streaming loop. Emitting it here would cause duplicate display.
                # LangGraph emission order guarantees "values" mode (which sets state) comes
                # BEFORE "messages" mode, so _state is already updated when we receive this.
                if _state.get("content_final_replacement"):
                    return sse_chunks  # Skip - replacement will be sent after loop

                content = message.content
                token_chunk = self.format_token_chunk(content)
                sse_chunks.append((token_chunk, content))

        return sse_chunks

    def _emit_execution_step(self, node_name: str) -> ChatStreamChunk | None:
        """
        Emit execution_step event for node transition.

        Args:
            node_name: Name of the node (router, planner, response, etc.)

        Returns:
            ChatStreamChunk with execution_step metadata or None if not visible
        """
        from src.domains.agents.utils.execution_metadata import build_execution_step_event

        execution_event = build_execution_step_event(
            step_type="node",
            step_name=node_name,
            status="started",
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

    def format_token_chunk(self, content: str) -> ChatStreamChunk:
        """
        Format token for SSE streaming.

        Args:
            content: Token content

        Returns:
            ChatStreamChunk with type="token"
        """
        return ChatStreamChunk(type="token", content=content)

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
        self, error: Exception, context: dict[str, Any] | None = None
    ) -> ChatStreamChunk:
        """
        Format error chunk.

        Args:
            error: Exception that occurred
            context: Optional error context

        Returns:
            ChatStreamChunk with type="error"
        """
        return ChatStreamChunk(
            type="error",
            content={
                "error": str(error),
                FIELD_ERROR_TYPE: type(error).__name__,
                "context": context or {},
            },
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
        message_id = f"hitl_{conversation_id}_{run_id}"
        is_plan_approval = action_type == "plan_approval"

        # Phase 1 HITL Streaming: Check if streaming generation is requested
        generate_streaming = interrupt_data.get("generate_question_streaming", False)
        user_language = interrupt_data.get("user_language", DEFAULT_LANGUAGE)
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

                # Stream tokens from LLM
                # Note: tracker is NOT passed here because:
                # 1. self.tracker is a TrackingContext, NOT a LangChain callback
                # 2. Token tracking is handled via Langfuse callbacks in create_instrumented_config()
                # 3. Passing TrackingContext causes "'TrackingContext' object has no attribute 'run_inline'" error
                # See OPTIMPLAN PLAN.md section 3.1 lines 295-334 for architecture details
                async for token in interaction.generate_question_stream(
                    context=first_action,
                    user_language=user_language,
                    user_timezone=user_timezone,
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

            except (TimeoutError, asyncio.CancelledError, RuntimeError, ValueError, OSError) as e:
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

        # === Step 3: Signal completion with token metadata ===
        # Get token summary from tracker BEFORE commit (FIX: tokens not displayed on HITL)
        token_metadata = {}
        if self.tracker:
            try:
                summary_dto = self.tracker.get_summary_dto()
                token_metadata = summary_dto.to_metadata()
                logger.info(
                    "hitl_token_metadata_extracted",
                    run_id=run_id,
                    tokens_in=summary_dto.tokens_in,
                    tokens_out=summary_dto.tokens_out,
                    cost_eur=summary_dto.cost_eur,
                    tracker_type=type(self.tracker).__name__,
                )
            except (AttributeError, ValueError, RuntimeError) as e:
                logger.warning(
                    "hitl_token_metadata_extraction_failed",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )

        complete_chunk = ChatStreamChunk(
            type="hitl_interrupt_complete",
            content="",
            metadata={
                "message_id": message_id,
                "requires_approval": True,
                # Phase 1 HITL Streaming: Include generated question for F5 recovery
                "generated_question": generated_question,
                # FIX: Include token metadata for frontend display
                **token_metadata,
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
    ) -> None:
        """
        Add all debug metrics sections to debug_metrics dict.

        This method is called at the END of streaming when ALL data is available.
        It builds token_budget, planner_intelligence, tool_selection, execution_timeline, and llm_calls.

        Args:
            debug_metrics: Base debug metrics dict (from query_intelligence.to_debug_metrics())
            state: Final state dict with all data
            run_id: Run ID for logging
        """
        from src.core.config import get_settings
        from src.core.config.agents import get_debug_thresholds

        settings = get_settings()

        # =================================================================
        # Token Budget: Calculate context size and determine zone
        # =================================================================
        try:
            from src.domains.agents.services.token_counter_service import (
                FallbackLevel,
                TokenCounterService,
            )

            token_counter = TokenCounterService(settings=settings)
            messages = state.get("messages", [])

            # Count tokens in messages
            message_tokens = token_counter.count_messages_tokens(messages)

            # Determine zone and strategy
            fallback_level = token_counter.get_fallback_level(message_tokens)

            # Map fallback level to zone
            zone_mapping = {
                FallbackLevel.FULL_CATALOGUE: "safe",
                FallbackLevel.FILTERED_CATALOGUE: "warning",
                FallbackLevel.REDUCED_DESCRIPTIONS: "warning",
                FallbackLevel.PRIMARY_DOMAIN_ONLY: "critical",
                FallbackLevel.SIMPLE_SEARCH: "emergency",
            }
            zone = zone_mapping.get(fallback_level, "safe")

            debug_metrics["token_budget"] = {
                "current_tokens": message_tokens,
                "thresholds": {
                    "safe": token_counter.threshold_safe,
                    "warning": token_counter.threshold_warning,
                    "critical": token_counter.threshold_critical,
                    "max": token_counter.threshold_max,
                },
                "zone": zone,
                "strategy": fallback_level,
                "fallback_active": fallback_level != FallbackLevel.FULL_CATALOGUE,
            }
        except (ImportError, ValueError, RuntimeError, AttributeError) as token_err:
            logger.debug(
                "debug_metrics_token_budget_failed",
                error=str(token_err),
                error_type=type(token_err).__name__,
            )

        # =================================================================
        # Planner Intelligence: Strategy, tokens, corrections
        # =================================================================
        planning_result = state.get("planning_result")
        if planning_result is not None:
            # Determine strategy name
            if planning_result.used_template:
                strategy = "template_bypass"
            elif planning_result.used_panic_mode:
                strategy = "panic_mode"
            elif planning_result.used_generative:
                strategy = "generative"
            else:
                strategy = "filtered_catalogue"

            # Calculate token reduction percentage
            tokens_used = planning_result.tokens_used
            tokens_saved = planning_result.tokens_saved
            total_would_be = tokens_used + tokens_saved
            reduction_pct = (
                round((tokens_saved / total_would_be) * 100, 1) if total_would_be > 0 else 0
            )

            # Get plan details
            plan_details = {}
            if planning_result.plan:
                plan_details = {
                    "steps_count": len(planning_result.plan.steps),
                    "tools_used": [
                        step.tool_name
                        for step in planning_result.plan.steps
                        if hasattr(step, "tool_name")
                    ],
                    "estimated_cost_usd": (
                        planning_result.plan.estimated_cost
                        if hasattr(planning_result.plan, "estimated_cost")
                        else None
                    ),
                }

            debug_metrics["planner_intelligence"] = {
                "strategy": strategy,
                "tokens": {
                    "used": tokens_used,
                    "saved": tokens_saved,
                    "full_catalogue_estimate": total_would_be,
                    "reduction_percentage": reduction_pct,
                },
                "plan": plan_details,
                "flags": {
                    "used_template": planning_result.used_template,
                    "used_panic_mode": planning_result.used_panic_mode,
                    "used_generative": planning_result.used_generative,
                },
                "success": planning_result.success,
                "error": planning_result.error,
            }

        # =================================================================
        # Execution Timeline: Collect step information from plan and results
        # =================================================================
        execution_plan = state.get("execution_plan")
        completed_steps = state.get("completed_steps", {})
        if execution_plan:
            try:
                timeline_steps = []
                for step in execution_plan.steps:
                    step_id = step.step_id if hasattr(step, "step_id") else str(id(step))
                    step_result = completed_steps.get(step_id, {})

                    # Extract domain from agent_name (e.g., "contacts_agent" → "contacts")
                    agent_name = getattr(step, "agent_name", None) or "unknown"
                    domain = (
                        agent_name.removesuffix("_agent") if agent_name != "unknown" else "unknown"
                    )

                    timeline_steps.append(
                        {
                            "step_id": step_id,
                            "tool_name": (
                                step.tool_name if hasattr(step, "tool_name") else "unknown"
                            ),
                            "domain": domain,
                            "status": "completed" if step_id in completed_steps else "pending",
                            "success": step_result.get("success", None),
                            "duration_ms": step_result.get("duration_ms", None),
                        }
                    )

                debug_metrics["execution_timeline"] = {
                    "steps": timeline_steps,
                    "total_steps": len(timeline_steps),
                    "completed_steps": len(completed_steps),
                }
            except (AttributeError, KeyError, ValueError, TypeError) as timeline_err:
                logger.debug(
                    "debug_metrics_execution_timeline_failed",
                    error=str(timeline_err),
                    error_type=type(timeline_err).__name__,
                )

        # =================================================================
        # Tool Selection: Merge semantic scores + filtered catalogue
        # =================================================================
        # Like domain_selection: show ALL tools from domains (with scores)
        # + highlight which ones are actually selected (filtered catalogue)
        filtered_catalogue = self._cached_filtered_catalogue
        tool_scores = self._cached_tool_scores

        logger.debug(
            "debug_metrics_tool_selection_check",
            run_id=run_id,
            has_filtered_catalogue=filtered_catalogue is not None,
            filtered_catalogue_tools_count=(
                len(filtered_catalogue.tools) if filtered_catalogue else 0
            ),
            has_tool_scores=tool_scores is not None,
            tool_scores_count=len(tool_scores.get("all_scores", {})) if tool_scores else 0,
        )

        if tool_scores:
            # Use selected_tools from tool_scores (tools that passed the > threshold filter)
            # This is the authoritative source from SemanticToolSelector
            selected_tools = tool_scores.get("selected_tools", [])

            # Fallback: if selected_tools not available, build from filtered_catalogue (legacy)
            if not selected_tools and filtered_catalogue:
                selected_tool_names = {t.get("name") for t in filtered_catalogue.tools}
                selected_tools = []
                for tool_name in selected_tool_names:
                    score = tool_scores["all_scores"].get(tool_name, 0.0)
                    selected_tools.append(
                        {
                            "tool_name": tool_name,
                            "score": round(score, 3),
                            "confidence": (
                                "high" if score >= 0.40 else ("medium" if score >= 0.15 else "low")
                            ),
                        }
                    )
                # Sort by score descending
                selected_tools.sort(key=lambda t: t["score"], reverse=True)

            thresholds = get_debug_thresholds()
            tool_th = thresholds.get("tool_selection", {})

            # Frontend-compatible format (like domain_selection)
            debug_metrics["tool_selection"] = {
                "selected_tools": selected_tools,
                "top_score": round(tool_scores["top_score"], 3),
                "has_uncertainty": tool_scores["has_uncertainty"],
                "all_scores": {
                    name: round(score, 3)
                    for name, score in sorted(
                        tool_scores["all_scores"].items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )
                },
                "thresholds": {
                    "softmax_temperature": {
                        "value": tool_th.get("softmax_temperature", 0.1),
                        "info": "Lower = sharper discrimination",
                    },
                    "primary_min": {
                        "value": tool_th.get("primary_min", 0.15),
                        "actual": round(tool_scores["top_score"], 3),
                        "passed": tool_scores["top_score"] >= tool_th.get("primary_min", 0.15),
                    },
                    "max_tools": {
                        "value": tool_th.get("max_tools", 8),
                        "info": f"Selected: {len(selected_tools)} from catalogue (filtered by intent), Scored: {len(tool_scores['all_scores'])} from domains",
                    },
                },
            }

            logger.debug(
                "debug_metrics_tool_selection_built",
                run_id=run_id,
                selected_count=len(selected_tools),
                scored_count=len(tool_scores["all_scores"]),
                top_score=tool_scores["top_score"],
            )

        # =================================================================
        # LLM Calls Breakdown: Per-node token consumption
        # =================================================================
        if self.tracker and hasattr(self.tracker, "get_llm_calls_breakdown"):
            try:
                llm_calls = self.tracker.get_llm_calls_breakdown()
                if llm_calls:
                    debug_metrics["llm_calls"] = llm_calls
                    debug_metrics["llm_summary"] = {
                        "total_calls": len(llm_calls),
                        "total_tokens_in": sum(c.get("tokens_in", 0) for c in llm_calls),
                        "total_tokens_out": sum(c.get("tokens_out", 0) for c in llm_calls),
                        "total_tokens_cache": sum(c.get("tokens_cache", 0) for c in llm_calls),
                        "total_cost_eur": round(sum(c.get("cost_eur", 0) for c in llm_calls), 6),
                    }
                    # v3.1: Update token_budget with REAL total from LLM calls
                    # User wants real consumed tokens, not just context size
                    if "token_budget" in debug_metrics:
                        total_consumed = (
                            debug_metrics["llm_summary"]["total_tokens_in"]
                            + debug_metrics["llm_summary"]["total_tokens_out"]
                        )
                        debug_metrics["token_budget"]["total_consumed"] = total_consumed
                        debug_metrics["token_budget"]["tokens_input"] = debug_metrics[
                            "llm_summary"
                        ]["total_tokens_in"]
                        debug_metrics["token_budget"]["tokens_output"] = debug_metrics[
                            "llm_summary"
                        ]["total_tokens_out"]
                        debug_metrics["token_budget"]["tokens_cache"] = debug_metrics[
                            "llm_summary"
                        ]["total_tokens_cache"]
            except (AttributeError, ValueError, RuntimeError) as llm_err:
                logger.debug(
                    "debug_metrics_llm_calls_failed",
                    run_id=run_id,
                    error=str(llm_err),
                    error_type=type(llm_err).__name__,
                )

        # =================================================================
        # Google API Calls Breakdown: Per-call details
        # =================================================================
        if self.tracker and hasattr(self.tracker, "get_google_api_calls_breakdown"):
            try:
                google_api_calls = self.tracker.get_google_api_calls_breakdown()
                if google_api_calls:
                    debug_metrics["google_api_calls"] = google_api_calls
                    # Summary stats
                    billable_calls = [c for c in google_api_calls if not c.get("cached", False)]
                    debug_metrics["google_api_summary"] = {
                        "total_calls": len(google_api_calls),
                        "billable_calls": len(billable_calls),
                        "cached_calls": len(google_api_calls) - len(billable_calls),
                        "total_cost_usd": round(
                            sum(c.get("cost_usd", 0) for c in billable_calls), 6
                        ),
                        "total_cost_eur": round(
                            sum(c.get("cost_eur", 0) for c in billable_calls), 6
                        ),
                    }
                    logger.debug(
                        "debug_metrics_google_api_calls_added",
                        run_id=run_id,
                        total_calls=len(google_api_calls),
                        billable_calls=len(billable_calls),
                    )
            except (AttributeError, ValueError, RuntimeError) as gapi_err:
                logger.debug(
                    "debug_metrics_google_api_calls_failed",
                    run_id=run_id,
                    error=str(gapi_err),
                    error_type=type(gapi_err).__name__,
                )

        # =================================================================
        # Execution Waves: Parallel visualization (v3.1)
        # SYNC: DependencyGraph.get_wave_info() is pure computation, no I/O
        # =================================================================
        if execution_plan:
            try:
                from src.domains.agents.orchestration.dependency_graph import DependencyGraph

                graph = DependencyGraph(execution_plan)
                debug_metrics["execution_waves"] = graph.get_wave_info()
            except (ImportError, AttributeError, ValueError, RuntimeError) as wave_err:
                logger.debug(
                    "debug_metrics_execution_waves_failed",
                    run_id=run_id,
                    error=str(wave_err),
                    error_type=type(wave_err).__name__,
                )

        # =================================================================
        # Request Lifecycle: Pipeline node progression (v3.2)
        # SYNC: Pure data transformation from already-collected llm_calls
        # Now includes duration_ms per node for execution time tracking
        # =================================================================
        if "llm_calls" in debug_metrics:
            try:
                llm_calls_data = debug_metrics["llm_calls"]
                nodes_data: dict[str, dict[str, Any]] = {}

                for call in llm_calls_data:
                    node_name = call.get("node_name", "unknown")
                    if node_name not in nodes_data:
                        nodes_data[node_name] = {
                            "name": node_name,
                            "status": "completed",
                            "tokens_in": 0,
                            "tokens_out": 0,
                            "tokens_cache": 0,
                            "cost_eur": 0.0,
                            "calls_count": 0,
                            "duration_ms": 0.0,  # v3.2: Track execution time
                        }
                    nodes_data[node_name]["tokens_in"] += call.get("tokens_in", 0)
                    nodes_data[node_name]["tokens_out"] += call.get("tokens_out", 0)
                    nodes_data[node_name]["tokens_cache"] += call.get("tokens_cache", 0)
                    nodes_data[node_name]["cost_eur"] += call.get("cost_eur", 0.0)
                    nodes_data[node_name]["calls_count"] += 1
                    nodes_data[node_name]["duration_ms"] += call.get("duration_ms", 0.0)

                # Order by pipeline progression
                from src.core.constants import DEBUG_PIPELINE_NODE_ORDER

                ordered_nodes: list[dict[str, Any]] = []

                # First add nodes in pipeline order
                for node_name in DEBUG_PIPELINE_NODE_ORDER:
                    if node_name in nodes_data:
                        ordered_nodes.append(nodes_data[node_name])

                # Then add any remaining nodes not in pipeline order
                for node_name, node_data in nodes_data.items():
                    if node_name not in DEBUG_PIPELINE_NODE_ORDER:
                        ordered_nodes.append(node_data)

                # v3.2: Calculate total duration across all nodes
                total_duration_ms = sum(node.get("duration_ms", 0.0) for node in ordered_nodes)

                debug_metrics["request_lifecycle"] = {
                    "nodes": ordered_nodes,
                    "total_nodes": len(ordered_nodes),
                    "total_duration_ms": total_duration_ms,  # v3.2: Total LLM execution time
                }
            except (KeyError, TypeError, ValueError) as lifecycle_err:
                logger.debug(
                    "debug_metrics_request_lifecycle_failed",
                    run_id=run_id,
                    error=str(lifecycle_err),
                    error_type=type(lifecycle_err).__name__,
                )

        # =================================================================
        # Knowledge Enrichment (Brave Search): Merge execution results
        # =================================================================
        # Base structure already created by QueryIntelligence.to_debug_metrics()
        # with encyclopedia_keywords and is_news_query. Here we enrich with
        # actual execution results from response_node.
        try:
            # Defensive check: ensure knowledge_enrichment section exists
            # (may not exist if query_intelligence was None during to_debug_metrics())
            if "knowledge_enrichment" not in debug_metrics:
                debug_metrics["knowledge_enrichment"] = {
                    "enabled": settings.knowledge_enrichment_enabled,
                    "executed": False,
                    "encyclopedia_keywords": [],
                    "is_news_query": False,
                }

            # Get knowledge_enrichment_result from state (set by response_node)
            enrichment_result = state.get("knowledge_enrichment_result") if state else None

            # Update the enabled field with actual settings value
            debug_metrics["knowledge_enrichment"]["enabled"] = settings.knowledge_enrichment_enabled

            if enrichment_result:
                # Determine if enrichment was actually executed (API called)
                # vs skipped (skip_reason present without endpoint/error)
                has_api_result = enrichment_result.get("endpoint") is not None
                has_api_error = enrichment_result.get("error") is not None
                was_executed = has_api_result or has_api_error

                debug_metrics["knowledge_enrichment"]["executed"] = was_executed
                debug_metrics["knowledge_enrichment"]["endpoint"] = enrichment_result.get(
                    "endpoint"
                )
                debug_metrics["knowledge_enrichment"]["keyword_used"] = enrichment_result.get(
                    "keyword_used"
                )
                debug_metrics["knowledge_enrichment"]["results_count"] = enrichment_result.get(
                    "results_count"
                )
                debug_metrics["knowledge_enrichment"]["from_cache"] = enrichment_result.get(
                    "from_cache"
                )
                debug_metrics["knowledge_enrichment"]["skip_reason"] = enrichment_result.get(
                    "skip_reason"
                )
                debug_metrics["knowledge_enrichment"]["error"] = enrichment_result.get("error")
                # Include actual results for debugging (title, description, url)
                debug_metrics["knowledge_enrichment"]["results"] = enrichment_result.get("results")
                # Include the formatted context that was injected into the LLM prompt
                debug_metrics["knowledge_enrichment"]["prompt_context"] = enrichment_result.get(
                    "prompt_context"
                )
            else:
                # Enrichment was not executed (feature disabled, no keywords, etc.)
                debug_metrics["knowledge_enrichment"]["executed"] = False
                if not settings.knowledge_enrichment_enabled:
                    debug_metrics["knowledge_enrichment"]["skip_reason"] = "feature_disabled"
                elif not debug_metrics["knowledge_enrichment"].get("encyclopedia_keywords"):
                    debug_metrics["knowledge_enrichment"]["skip_reason"] = "no_keywords"

            logger.debug(
                "debug_metrics_knowledge_enrichment_built",
                run_id=run_id,
                executed=debug_metrics["knowledge_enrichment"]["executed"],
                endpoint=debug_metrics["knowledge_enrichment"].get("endpoint"),
                results_count=debug_metrics["knowledge_enrichment"].get("results_count"),
            )
        except (KeyError, TypeError, AttributeError) as ke_err:
            logger.debug(
                "debug_metrics_knowledge_enrichment_failed",
                run_id=run_id,
                error=str(ke_err),
                error_type=type(ke_err).__name__,
            )

        # =================================================================
        # Memory Injection: Injected memories with scores for tuning
        # =================================================================
        try:
            memory_debug = state.get("memory_injection_debug") if state else None
            if memory_debug:
                debug_metrics["memory_injection"] = memory_debug
                logger.debug(
                    "debug_metrics_memory_injection_added",
                    run_id=run_id,
                    memory_count=memory_debug.get("memory_count", 0),
                    emotional_state=memory_debug.get("emotional_state"),
                )
        except (KeyError, TypeError, AttributeError) as mem_err:
            logger.debug(
                "debug_metrics_memory_injection_failed",
                run_id=run_id,
                error=str(mem_err),
                error_type=type(mem_err).__name__,
            )

        # =================================================================
        # Skills: Skill activation details for debug panel
        # =================================================================
        try:
            # Route 3 (conversation fallback): detect activate_skill_tool calls from messages.
            # When the response LLM called activate_skill_tool, the tool call is in state messages.
            if not self.activated_skill_name and state:
                messages = state.get("messages", [])
                for msg in reversed(messages[-10:]):
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    for tc in tool_calls:
                        if isinstance(tc, dict) and tc.get("name") == "activate_skill_tool":
                            skill_from_tool = tc.get("args", {}).get("name")
                            if skill_from_tool:
                                self.activated_skill_name = skill_from_tool
                                break
                    if self.activated_skill_name:
                        break

            effective_skill_name = self.activated_skill_name

            if effective_skill_name:
                from src.domains.skills.cache import SkillsCache

                skill_data = SkillsCache.get_by_name(effective_skill_name)
                activation_mode = "planner"
                is_deterministic = False

                # Determine activation mode
                if planning_result and planning_result.plan and planning_result.plan.metadata:
                    if planning_result.plan.metadata.get("skill_bypass"):
                        activation_mode = "bypass"
                    elif planning_result.plan.metadata.get("skill_name"):
                        activation_mode = "planner"
                    else:
                        # Route 3: LLM called activate_skill_tool directly
                        activation_mode = "tool"
                    is_deterministic = bool(planning_result.plan.metadata.get("skill_bypass"))
                else:
                    # Route 3: no plan → LLM called activate_skill_tool
                    activation_mode = "tool"

                skills_debug: dict[str, Any] = {
                    "activated": True,
                    "skill_name": effective_skill_name,
                    "activation_mode": activation_mode,
                    "is_deterministic": is_deterministic,
                }
                if skill_data:
                    skills_debug["category"] = skill_data.get("category")
                    skills_debug["priority"] = skill_data.get("priority", 50)
                    skills_debug["has_scripts"] = bool(skill_data.get("scripts"))
                    skills_debug["has_references"] = bool(skill_data.get("references"))
                    skills_debug["scope"] = skill_data.get("scope", "admin")

                debug_metrics["skills"] = skills_debug
                logger.debug(
                    "debug_metrics_skills_added",
                    run_id=run_id,
                    skill_name=effective_skill_name,
                    activation_mode=activation_mode,
                )
        except (KeyError, TypeError, AttributeError) as skill_err:
            logger.debug(
                "debug_metrics_skills_failed",
                run_id=run_id,
                error=str(skill_err),
                error_type=type(skill_err).__name__,
            )
