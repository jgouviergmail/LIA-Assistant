"""
Background Memory Extractor for Psychological Profiling.

Performs asynchronous psychoanalytical extraction from conversations
to build the user's psychological profile. Runs in background after
response generation to avoid blocking the main conversation flow.

Key features:
- Fire-and-forget pattern with safe_fire_and_forget
- Psychoanalytical prompt for emotional detection
- Deduplication against existing memories
- Personality-aware extraction nuances

Architecture:
    response_node → safe_fire_and_forget(extract_memories_background(...))
                                          ↓
                         [Background Task - Non-blocking]
                                          ↓
                         LLM psychoanalysis → new memories → store.aput()

Example:
    >>> from src.infrastructure.async_utils import safe_fire_and_forget
    >>> safe_fire_and_forget(
    ...     extract_memories_background(store, user_id, messages, session_id),
    ...     name="memory_extraction"
    ... )

"""

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.store.base import BaseStore

from src.core.config import settings
from src.core.constants import (
    MEMORY_CATEGORY_RELATIONSHIP,
    MEMORY_DEDUP_MIN_SCORE,
    MEMORY_DEDUP_SEARCH_LIMIT,
    MEMORY_EXTRACTION_QUERY_TRUNCATION_LENGTH,
    MEMORY_RELATIONSHIP_MIN_SCORE,
    MEMORY_RELATIONSHIP_SEARCH_LIMIT,
)
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts import load_prompt
from src.domains.agents.tools.memory_tools import MemorySchema
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.store.semantic_store import MemoryNamespace, search_semantic

logger = get_logger(__name__)

# Per-run_id debug results cache for memory extraction.
# Stores debug data from background extraction so the streaming service
# can include it in debug_metrics after await_run_id_tasks completes.
# Each entry is (timestamp, data) to allow TTL-based eviction.
_memory_extraction_debug_cache: dict[str, tuple[float, dict[str, Any]]] = {}

# Maximum number of entries before forced eviction of oldest
_MEMORY_DEBUG_CACHE_MAX_SIZE = 100
# Entries older than this (seconds) are evicted on access
_MEMORY_DEBUG_CACHE_TTL_SECONDS = 120.0


# ============================================================================
# Token Persistence for Background Memory Tasks
# ============================================================================


async def _persist_memory_tokens(
    user_id: str,
    session_id: str,
    conversation_id: str | None,
    result: AIMessage,
    model_name: str,
    parent_run_id: str | None = None,
    duration_ms: float = 0.0,
) -> None:
    """
    Persist token usage from memory extraction LLM call to database.

    Uses TrackingContext to reuse existing persistence infrastructure:
    - TokenUsageLog (detailed node breakdown)
    - MessageTokenSummary (aggregated per run)
    - UserStatistics (cumulative per user)

    This enables memory costs to appear in:
    - Dashboard cumulative statistics
    - Conversation total costs (deferred update)

    Args:
        user_id: User ID for statistics
        session_id: Session/thread ID
        conversation_id: Conversation UUID (optional, for linking)
        result: AIMessage with usage_metadata
        model_name: LLM model used for extraction
        parent_run_id: If provided, UPSERT tokens into the parent message's
            MessageTokenSummary instead of creating an orphan record.
            This ensures background extraction costs appear under the
            originating assistant bubble on page refresh.
    """
    from src.domains.chat.service import TrackingContext

    try:
        # Extract token usage from AIMessage.usage_metadata
        usage_metadata = getattr(result, "usage_metadata", None)
        if not usage_metadata:
            logger.debug(
                "memory_tokens_no_usage_metadata",
                user_id=user_id,
                session_id=session_id,
            )
            return

        # Parse tokens (OpenAI format: input_tokens includes cached)
        raw_input_tokens = usage_metadata.get("input_tokens", 0)
        output_tokens = usage_metadata.get("output_tokens", 0)

        # Extract cached tokens if available
        input_details = usage_metadata.get("input_token_details", {})
        cached_tokens = input_details.get("cache_read", 0) if input_details else 0

        # CRITICAL: OpenAI's input_tokens INCLUDES cached tokens
        # Subtract cached to get non-cached input tokens
        input_tokens = raw_input_tokens - cached_tokens

        if input_tokens == 0 and output_tokens == 0:
            logger.debug(
                "memory_tokens_zero_usage",
                user_id=user_id,
            )
            return

        # Use parent_run_id to UPSERT into the originating message's summary,
        # or generate a standalone run_id for backward compatibility
        run_id = parent_run_id or f"mem_extract_{uuid.uuid4().hex[:12]}"

        # Parse conversation_id if provided
        conv_uuid: UUID | None = None
        if conversation_id:
            try:
                conv_uuid = UUID(conversation_id)
            except ValueError:
                logger.warning(
                    "memory_tokens_invalid_conversation_id",
                    conversation_id=conversation_id,
                )

        # Create TrackingContext for persistence (auto_commit=False for manual control)
        async with TrackingContext(
            run_id=run_id,
            user_id=UUID(user_id),
            session_id=session_id,
            conversation_id=conv_uuid,
            auto_commit=False,
        ) as tracker:
            # Record tokens with node_name="memory_extraction"
            await tracker.record_node_tokens(
                node_name="memory_extraction",
                model_name=model_name,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                cached_tokens=cached_tokens,
                duration_ms=duration_ms,
            )

            # Manually commit to persist
            await tracker.commit()

        logger.info(
            "memory_tokens_persisted",
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            run_id=run_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            model_name=model_name,
        )

    except Exception as e:
        # Graceful degradation - token persistence failure must not break memory extraction
        logger.error(
            "memory_tokens_persistence_failed",
            user_id=user_id,
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )


def _get_psychoanalysis_prompt() -> str:
    """Load the memory extraction prompt from file."""
    return str(load_prompt("memory_extraction_prompt"))


def _get_personality_addon_prompt() -> str:
    """Load the personality addon prompt from file."""
    return str(load_prompt("memory_extraction_personality_addon"))


def _format_messages_for_extraction(messages: list[BaseMessage]) -> str:
    """
    Format messages for extraction prompt.

    Converts LangChain messages to readable conversation format.

    Args:
        messages: List of conversation messages

    Returns:
        Formatted conversation string
    """
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            prefix = "USER"
        elif isinstance(msg, AIMessage):
            # Skip proactive notifications (interest/heartbeat) — not user-generated content
            if msg.additional_kwargs.get("proactive_notification"):
                continue
            prefix = "ASSISTANT"
        else:
            prefix = "SYSTEM"

        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        # Truncate very long messages (configurable limit)
        max_chars = settings.memory_extraction_message_max_chars
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        lines.append(f"{prefix}: {content}")

    return "\n".join(lines)


def _parse_extraction_result(result_text: str) -> list[MemorySchema]:
    """
    Parse LLM extraction result into MemorySchema objects.

    Handles common JSON parsing issues (markdown fences, whitespace, comments).

    Args:
        result_text: Raw LLM output

    Returns:
        List of validated MemorySchema objects
    """
    import re

    # Clean common LLM artifacts
    cleaned = result_text.strip()

    # Remove markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Find start and end of code block
        start_idx = 0
        end_idx = len(lines)
        for i, line in enumerate(lines):
            if line.startswith("```") and i == 0:
                start_idx = 1
            elif line.startswith("```") and i > 0:
                end_idx = i
                break
        cleaned = "\n".join(lines[start_idx:end_idx])

    # Remove single-line comments (// comment)
    cleaned = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)

    # Remove trailing commas before ] or }
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)

    # Try to find JSON array in the text if direct parsing fails
    def extract_json_array(text: str) -> str | None:
        """Extract first valid-looking JSON array from text."""
        # Find opening bracket
        start = text.find("[")
        if start == -1:
            return None

        # Track bracket depth to find matching closing bracket
        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue

            if char == "\\":
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None

    # Try direct parsing first
    try:
        data = json.loads(cleaned)

        if not isinstance(data, list):
            logger.warning("extraction_result_not_list", type=type(data).__name__)
            return []

        memories = []
        for item in data:
            try:
                memory = MemorySchema(**item)
                memories.append(memory)
            except Exception as e:
                logger.debug(
                    "memory_item_validation_failed",
                    item=item,
                    error=str(e),
                )
                continue

        return memories

    except json.JSONDecodeError as e:
        # Log full output for debugging
        logger.warning(
            "extraction_json_parse_failed",
            error=str(e),
            result_length=len(cleaned),
            result_preview=cleaned[:500] if cleaned else "empty",
        )

        # Try to extract JSON array from potentially malformed response
        extracted = extract_json_array(cleaned)
        if extracted:
            try:
                # Apply same cleaning to extracted array
                extracted = re.sub(r",\s*([\]}])", r"\1", extracted)
                data = json.loads(extracted)

                if isinstance(data, list):
                    memories = []
                    for item in data:
                        try:
                            memory = MemorySchema(**item)
                            memories.append(memory)
                        except Exception:
                            continue

                    if memories:
                        logger.info(
                            "extraction_json_recovered",
                            recovered_count=len(memories),
                        )
                        return memories
            except json.JSONDecodeError:
                pass

        return []


def _generate_memory_key() -> str:
    """Generate unique key for memory storage."""
    return f"mem_{uuid.uuid4().hex[:12]}"


def _cache_debug_result(run_id: str, data: dict[str, Any]) -> None:
    """
    Store debug data in the cache with timestamp and size enforcement.

    Args:
        run_id: Pipeline run_id key.
        data: Debug data dict to cache.
    """
    # Enforce max size: evict oldest entries if full
    while len(_memory_extraction_debug_cache) >= _MEMORY_DEBUG_CACHE_MAX_SIZE:
        oldest_key = min(
            _memory_extraction_debug_cache,
            key=lambda k: _memory_extraction_debug_cache[k][0],
        )
        _memory_extraction_debug_cache.pop(oldest_key, None)

    _memory_extraction_debug_cache[run_id] = (time.monotonic(), data)


def get_memory_extraction_debug(run_id: str) -> dict[str, Any] | None:
    """
    Retrieve and consume debug data from background memory extraction.

    Called by streaming_service after await_run_id_tasks to include
    memory detection data in the debug_metrics SSE event.

    Also performs lazy eviction of stale cache entries to prevent
    memory leaks if streaming_service fails to consume some entries.

    Args:
        run_id: Pipeline run_id used when scheduling the extraction task.

    Returns:
        Debug dict with extracted memories, dedup info, and LLM metadata,
        or None if no data is available for this run_id.
    """
    # Lazy eviction of stale entries (TTL-based)
    now = time.monotonic()
    stale_keys = [
        k
        for k, (ts, _) in _memory_extraction_debug_cache.items()
        if now - ts > _MEMORY_DEBUG_CACHE_TTL_SECONDS
    ]
    for k in stale_keys:
        _memory_extraction_debug_cache.pop(k, None)

    entry = _memory_extraction_debug_cache.pop(run_id, None)
    if entry is None:
        return None
    return entry[1]  # Return data, discard timestamp


async def extract_memories_background(
    store: BaseStore,
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    personality_instruction: str | None = None,
    conversation_id: str | None = None,
    parent_run_id: str | None = None,
) -> int:
    """
    Background psychoanalytical extraction from conversation.

    OPTIMIZED: Only analyzes the LAST user message to avoid:
    - Reprocessing already-analyzed messages (cost savings)
    - Duplicate memory extraction
    - Analyzing assistant messages (no user info there)

    Includes minimal context (last 4 messages) for understanding.

    Token Tracking:
        LLM tokens are persisted to database for:
        - UserStatistics (dashboard cumulative)
        - MessageTokenSummary (conversation totals, deferred)
        This enables memory costs to be included in user statistics.

    Args:
        store: LangGraph BaseStore for memory persistence
        user_id: Target user ID for memory storage
        messages: Conversation messages to analyze
        session_id: Current session ID for logging
        personality_instruction: Optional personality context for nuance adaptation
        conversation_id: Optional conversation UUID for linking token costs
        parent_run_id: Pipeline run_id for UPSERT into the originating message's
            token summary and for caching debug data retrievable via
            ``get_memory_extraction_debug(run_id)``.

    Returns:
        Number of new memories extracted and stored

    Example:
        >>> safe_fire_and_forget(
        ...     extract_memories_background(
        ...         store, "user-123", messages, "session-456",
        ...         conversation_id="conv-uuid"
        ...     ),
        ...     name="memory_extraction"
        ... )
    """
    try:
        # Check if memory extraction is enabled
        if not settings.memory_extraction_enabled:
            logger.debug(
                "memory_extraction_disabled",
                user_id=user_id,
            )
            if parent_run_id:
                _cache_debug_result(
                    parent_run_id,
                    {
                        "enabled": False,
                        "extracted_memories": [],
                        "existing_similar": [],
                        "llm_metadata": None,
                        "skipped_reason": "Feature disabled globally",
                    },
                )
            return 0

        # Skip if no messages
        if not messages:
            logger.debug(
                "memory_extraction_skipped_no_messages",
                user_id=user_id,
            )
            if parent_run_id:
                _cache_debug_result(
                    parent_run_id,
                    {
                        "enabled": True,
                        "extracted_memories": [],
                        "existing_similar": [],
                        "llm_metadata": None,
                        "skipped_reason": "No messages to analyze",
                    },
                )
            return 0

        # Set embedding context for DB persistence of embedding tokens
        # This enables embedding costs to be tracked in user statistics
        set_embedding_context(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

        # Find the LAST HumanMessage (the new user message to analyze)
        last_human_message: HumanMessage | None = None
        last_human_index = -1

        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, HumanMessage):
                last_human_message = msg
                last_human_index = i
                break

        if not last_human_message:
            logger.debug(
                "memory_extraction_skipped_no_human_message",
                user_id=user_id,
            )
            if parent_run_id:
                _cache_debug_result(
                    parent_run_id,
                    {
                        "enabled": True,
                        "extracted_memories": [],
                        "existing_similar": [],
                        "llm_metadata": None,
                        "skipped_reason": "No human message found",
                    },
                )
            return 0

        # Get minimal context: last 4 messages before the target message
        # (enough to understand context without reprocessing everything)
        context_start = max(0, last_human_index - 3)
        context_messages = messages[context_start : last_human_index + 1]

        logger.debug(
            "memory_extraction_targeting",
            user_id=user_id,
            target_message_index=last_human_index,
            context_messages=len(context_messages),
            total_messages=len(messages),
        )

        # Retrieve SIMILAR existing memories for deduplication (semantic search)
        # OPTIMIZATION: Instead of loading all memories, we only search for
        # memories similar to the current message. This:
        # - Reduces token usage (only relevant memories sent to LLM)
        # - Provides better deduplication (semantic match vs full scan)
        # - Scales better as memory count grows
        namespace = MemoryNamespace(user_id)
        message_content = (
            last_human_message.content
            if isinstance(last_human_message.content, str)
            else str(last_human_message.content)
        )

        # Truncate query for efficiency (embedding computation)
        truncated_query = message_content[:MEMORY_EXTRACTION_QUERY_TRUNCATION_LENGTH]

        # Semantic search using the user's message as query
        # Only retrieve memories that are semantically similar (potential duplicates)
        # Uses centralized search_semantic for DRY compliance
        existing_results = await search_semantic(
            store=store,
            namespace=namespace,
            query=truncated_query,
            limit=MEMORY_DEDUP_SEARCH_LIMIT,
            min_score=MEMORY_DEDUP_MIN_SCORE,
        )

        # Extract content from filtered results
        existing_texts = [
            r.value.get("content", "")
            for r in existing_results
            if isinstance(r.value, dict) and r.value.get("content")
        ]

        logger.debug(
            "memory_dedup_semantic_search",
            user_id=user_id,
            query_length=len(message_content),
            similar_memories_found=len(existing_texts),
        )

        # Format conversation with context
        conversation = _format_messages_for_extraction(context_messages)

        # Retrieve known relationships for enrichment (names resolution)
        # Uses semantic search to find relationships matching the user's message
        # This allows the LLM to enrich "my son" with "My son John Smith"
        # Uses centralized search_semantic for DRY compliance, with category filter on top
        relationship_results = await search_semantic(
            store=store,
            namespace=namespace,
            query=truncated_query,
            limit=MEMORY_RELATIONSHIP_SEARCH_LIMIT,
            min_score=MEMORY_RELATIONSHIP_MIN_SCORE,
        )

        # Filter by category "relationship" and extract content
        # search_semantic already filtered by min_score, we just add category filter
        known_relationships = [
            item.value.get("content", "")
            for item in relationship_results
            if isinstance(item.value, dict)
            and item.value.get("category") == MEMORY_CATEGORY_RELATIONSHIP
            and item.value.get("content")
        ]

        logger.debug(
            "memory_extraction_relationships_found",
            user_id=user_id,
            relationship_count=len(known_relationships),
            search_results=len(relationship_results),
        )

        # Build prompt from external file
        current_datetime = datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M")
        prompt = _get_psychoanalysis_prompt().format(
            conversation=conversation,
            existing_memories=(
                "\n".join(f"- {t}" for t in existing_texts) if existing_texts else "None"
            ),
            current_datetime=current_datetime,
            known_relationships=(
                "\n".join(f"- {r}" for r in known_relationships)
                if known_relationships
                else "No known relationships"
            ),
        )

        # Add personality context if available
        if personality_instruction:
            prompt += _get_personality_addon_prompt().format(
                personality_instruction=personality_instruction
            )

        # Get extraction LLM from unified config (LLM_DEFAULTS + admin overrides)
        llm = get_llm("memory_extraction")

        # Invoke LLM with instrumentation for token tracking
        # Uses node_name="memory_extraction" for cost attribution in metrics
        _llm_start = time.time()
        result = await invoke_with_instrumentation(
            llm=llm,
            llm_type="memory_extraction",
            messages=prompt,
            session_id=session_id,
            user_id=user_id,
        )
        _llm_duration_ms = (time.time() - _llm_start) * 1000
        result_content = result.content if isinstance(result.content, str) else str(result.content)

        # Resolve LLM config once for both token persistence and debug metadata
        llm_config = get_llm_config_for_agent(settings, "memory_extraction")

        # Persist token usage to database (deferred update for user statistics)
        # This enables memory costs to appear in dashboard and conversation totals
        await _persist_memory_tokens(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            result=result,
            model_name=llm_config.model,
            parent_run_id=parent_run_id,
            duration_ms=_llm_duration_ms,
        )

        # Build LLM metadata for debug panel
        usage_metadata = getattr(result, "usage_metadata", None) or {}
        raw_input_tokens = usage_metadata.get("input_tokens", 0)
        output_tokens = usage_metadata.get("output_tokens", 0)
        input_details = usage_metadata.get("input_token_details", {})
        cached_tokens = input_details.get("cache_read", 0) if input_details else 0

        llm_metadata_debug: dict[str, Any] = {
            "model": llm_config.model,
            "input_tokens": raw_input_tokens - cached_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "total_tokens": raw_input_tokens + output_tokens,
        }

        # Build existing similar memories debug data
        existing_similar_debug = [
            {
                "content": r.value.get("content", ""),
                "category": r.value.get("category", "unknown"),
                "score": round(getattr(r, "score", 0.0), 3),
            }
            for r in existing_results
            if isinstance(r.value, dict) and r.value.get("content")
        ]

        # Parse extraction result
        new_memories = _parse_extraction_result(result_content)

        if not new_memories:
            logger.debug(
                "memory_extraction_no_new_memories",
                user_id=user_id,
                session_id=session_id,
            )
            if parent_run_id:
                _cache_debug_result(
                    parent_run_id,
                    {
                        "enabled": True,
                        "extracted_memories": [],
                        "existing_similar": existing_similar_debug,
                        "llm_metadata": llm_metadata_debug,
                        "skipped_reason": None,
                    },
                )
            return 0

        # Persist new memories
        stored_count = 0
        namespace_tuple = namespace.to_tuple()

        logger.info(
            "memory_persistence_starting",
            user_id=user_id,
            namespace=namespace_tuple,
            memories_to_store=len(new_memories),
        )

        now = datetime.now(UTC).isoformat()
        stored_memories_debug: list[dict[str, Any]] = []

        for memory in new_memories:
            try:
                memory_key = _generate_memory_key()
                memory_value = {
                    **memory.model_dump(),
                    "created_at": now,
                }

                logger.info(
                    "memory_aput_attempt",
                    user_id=user_id,
                    namespace=namespace_tuple,
                    key=memory_key,
                    value_keys=list(memory_value.keys()),
                )

                await store.aput(
                    namespace_tuple,
                    key=memory_key,
                    value=memory_value,
                )

                # Verify storage immediately
                verification = await store.aget(namespace_tuple, memory_key)
                stored = verification is not None
                if stored:
                    stored_count += 1
                    logger.info(
                        "memory_stored_verified",
                        user_id=user_id,
                        key=memory_key,
                        category=memory.category,
                        verified=True,
                    )
                else:
                    logger.warning(
                        "memory_stored_but_not_found",
                        user_id=user_id,
                        key=memory_key,
                        message="aput succeeded but aget returned None",
                    )

                # Collect debug data for each extracted memory
                stored_memories_debug.append(
                    {
                        "content": memory.content,
                        "category": memory.category,
                        "emotional_weight": memory.emotional_weight,
                        "importance": round(memory.importance, 2),
                        "trigger_topic": memory.trigger_topic,
                        "stored": stored,
                    }
                )

            except Exception as e:
                logger.warning(
                    "memory_storage_failed",
                    user_id=user_id,
                    error=str(e),
                    content_preview=memory.content[:50] if memory.content else "",
                )
                # Still record as failed in debug
                stored_memories_debug.append(
                    {
                        "content": memory.content,
                        "category": memory.category,
                        "emotional_weight": memory.emotional_weight,
                        "importance": round(memory.importance, 2),
                        "trigger_topic": memory.trigger_topic,
                        "stored": False,
                    }
                )
                continue

        logger.info(
            "memory_extraction_completed",
            user_id=user_id,
            session_id=session_id,
            extracted_count=len(new_memories),
            stored_count=stored_count,
        )

        # Cache debug data for streaming_service to pick up
        if parent_run_id:
            _cache_debug_result(
                parent_run_id,
                {
                    "enabled": True,
                    "extracted_memories": stored_memories_debug,
                    "existing_similar": existing_similar_debug,
                    "llm_metadata": llm_metadata_debug,
                    "skipped_reason": None,
                },
            )

        return stored_count

    except Exception as e:
        logger.error(
            "memory_extraction_failed",
            user_id=user_id,
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )
        if parent_run_id:
            _cache_debug_result(
                parent_run_id,
                {
                    "enabled": True,
                    "extracted_memories": [],
                    "existing_similar": [],
                    "llm_metadata": None,
                    "skipped_reason": None,
                    "error": str(e),
                },
            )
        return 0

    finally:
        # Always clear embedding context to prevent cross-request contamination
        clear_embedding_context()


async def extract_memories_from_single_message(
    store: BaseStore,
    user_id: str,
    message: str,
    personality_instruction: str | None = None,
) -> int:
    """
    Extract memories from a single user message.

    Lighter-weight extraction for individual messages.
    Used for real-time extraction during conversation.

    Args:
        store: LangGraph BaseStore
        user_id: Target user ID
        message: Single user message to analyze
        personality_instruction: Optional personality context

    Returns:
        Number of memories extracted
    """
    # Convert to HumanMessage for consistent processing
    messages: list[BaseMessage] = [HumanMessage(content=message)]
    return await extract_memories_background(
        store=store,
        user_id=user_id,
        messages=messages,
        session_id="single_message",
        personality_instruction=personality_instruction,
    )
