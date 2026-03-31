"""
Background Memory Extractor for Psychological Profiling.

Performs asynchronous psychoanalytical extraction from conversations
to build the user's psychological profile. Runs in background after
response generation to avoid blocking the main conversation flow.

Key features:
- Fire-and-forget pattern with safe_fire_and_forget
- Psychoanalytical prompt for emotional detection
- Deduplication against existing memories (semantic pre-filter)
- Create/update/delete actions (micro-consolidation, same as journal)
- Personality-aware extraction nuances
- Accepts pre-computed embedding from centralized UserMessageEmbeddingService

Architecture:
    response_node -> safe_fire_and_forget(extract_memories_background(...))
                                          |
                         [Background Task - Non-blocking]
                                          |
                         semantic dedup search (pre-computed embedding)
                                          |
                         LLM psychoanalysis -> create/update/delete -> MemoryService

Phase: v1.14.0 -- Migrated from LangGraph store to PostgreSQL custom + create/update/delete
"""

import json
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import settings
from src.core.constants import (
    MEMORY_DEDUP_MIN_SCORE,
    MEMORY_DEDUP_SEARCH_LIMIT,
    MEMORY_EXTRACTION_QUERY_TRUNCATION_LENGTH,
    MEMORY_RELATIONSHIP_MIN_SCORE,
    MEMORY_RELATIONSHIP_SEARCH_LIMIT,
)
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts import load_prompt
from src.domains.memories.schemas import ExtractedMemory
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Per-run_id debug results cache for memory extraction.
_memory_extraction_debug_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_MEMORY_DEBUG_CACHE_MAX_SIZE = 100
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
    """Persist token usage from memory extraction LLM call to database.

    Uses TrackingContext for real cost calculation and dashboard integration.

    Args:
        user_id: User ID for statistics.
        session_id: Session/thread ID.
        conversation_id: Conversation UUID (optional).
        result: AIMessage with usage_metadata.
        model_name: LLM model used.
        parent_run_id: UPSERT into parent message's summary if provided.
        duration_ms: LLM call duration in milliseconds.
    """
    from src.domains.chat.service import TrackingContext

    try:
        usage_metadata = getattr(result, "usage_metadata", None)
        if not usage_metadata:
            return

        raw_input_tokens = usage_metadata.get("input_tokens", 0)
        output_tokens = usage_metadata.get("output_tokens", 0)
        input_details = usage_metadata.get("input_token_details", {})
        cached_tokens = input_details.get("cache_read", 0) if input_details else 0
        input_tokens = raw_input_tokens - cached_tokens

        if input_tokens == 0 and output_tokens == 0:
            return

        run_id = parent_run_id or f"mem_extract_{uuid.uuid4().hex[:12]}"

        conv_uuid: UUID | None = None
        if conversation_id:
            try:
                conv_uuid = UUID(conversation_id)
            except ValueError:
                pass

        async with TrackingContext(
            run_id=run_id,
            user_id=UUID(user_id),
            session_id=session_id,
            conversation_id=conv_uuid,
            auto_commit=False,
        ) as tracker:
            await tracker.record_node_tokens(
                node_name="memory_extraction",
                model_name=model_name,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                cached_tokens=cached_tokens,
                duration_ms=duration_ms,
            )
            await tracker.commit()

        logger.info(
            "memory_tokens_persisted",
            user_id=user_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
        )

    except Exception as e:
        logger.error(
            "memory_tokens_persistence_failed",
            user_id=user_id,
            error=str(e),
            exc_info=True,
        )


# ============================================================================
# Prompt & Formatting Helpers
# ============================================================================


def _get_psychoanalysis_prompt() -> str:
    """Load the memory extraction prompt from file."""
    return str(load_prompt("memory_extraction_prompt"))


def _get_personality_addon_prompt() -> str:
    """Load the personality addon prompt from file."""
    return str(load_prompt("memory_extraction_personality_addon"))


def _format_messages_for_extraction(messages: list[BaseMessage]) -> str:
    """Format messages for extraction prompt context.

    Args:
        messages: List of conversation messages.

    Returns:
        Formatted conversation string.
    """
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            prefix = "USER"
        elif isinstance(msg, AIMessage):
            if msg.additional_kwargs.get("proactive_notification"):
                continue
            prefix = "ASSISTANT"
        else:
            prefix = "SYSTEM"

        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        max_chars = settings.memory_extraction_message_max_chars
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        lines.append(f"{prefix}: {content}")

    return "\n".join(lines)


def _format_existing_memories_with_ids(
    memories: list[tuple[Any, float]],
) -> str:
    """Format existing memories for the extraction prompt with IDs.

    Shows memories with their UUIDs so the LLM can reference them
    for update/delete actions.

    Args:
        memories: List of (Memory, score) tuples from search_by_relevance.

    Returns:
        Formatted string for prompt injection.
    """
    if not memories:
        return "None"

    lines = []
    for memory, _score in memories:
        content = memory.content or ""
        category = memory.category or "personal"
        importance = memory.importance or 0.7
        lines.append(f"- [id={memory.id} | {category} | importance={importance:.1f}] {content}")

    return "\n".join(lines)


# ============================================================================
# LLM Output Parsing
# ============================================================================


def _parse_extraction_result(result_text: str) -> list[ExtractedMemory]:
    """Parse LLM extraction result into ExtractedMemory objects.

    Handles common JSON parsing issues and supports both old format
    (no action field → create) and new format (with action field).

    Args:
        result_text: Raw LLM output.

    Returns:
        List of validated ExtractedMemory objects.
    """
    cleaned = result_text.strip()

    # Remove markdown code fences
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        start_idx = 0
        end_idx = len(lines)
        for i, line in enumerate(lines):
            if line.startswith("```") and i == 0:
                start_idx = 1
            elif line.startswith("```") and i > 0:
                end_idx = i
                break
        cleaned = "\n".join(lines[start_idx:end_idx])

    # Remove single-line comments
    cleaned = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)
    # Remove trailing commas
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)

    def _extract_json_array(text: str) -> str | None:
        start = text.find("[")
        if start == -1:
            return None
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

    def _parse_items(data: list) -> list[ExtractedMemory]:
        entries = []
        for item in data:
            try:
                entry = ExtractedMemory(**item)
                # Reject create actions missing required content/category
                if entry.action == "create" and (not entry.content or not entry.category):
                    logger.debug(
                        "memory_item_missing_required_fields",
                        item=item,
                        action=entry.action,
                    )
                    continue
                entries.append(entry)
            except Exception as e:
                logger.debug(
                    "memory_item_validation_failed",
                    item=item,
                    error=str(e),
                )
                continue
        return entries

    # Try direct parsing
    try:
        data = json.loads(cleaned)
        if not isinstance(data, list):
            return []
        return _parse_items(data)

    except json.JSONDecodeError as e:
        logger.warning(
            "extraction_json_parse_failed",
            error=str(e),
            result_preview=cleaned[:500] if cleaned else "empty",
        )

        extracted = _extract_json_array(cleaned)
        if extracted:
            try:
                extracted = re.sub(r",\s*([\]}])", r"\1", extracted)
                data = json.loads(extracted)
                if isinstance(data, list):
                    items = _parse_items(data)
                    if items:
                        logger.info("extraction_json_recovered", recovered_count=len(items))
                        return items
            except json.JSONDecodeError:
                pass

        return []


# ============================================================================
# Debug Cache
# ============================================================================


def _cache_debug_result(run_id: str, data: dict[str, Any]) -> None:
    """Store debug data with timestamp and size enforcement."""
    while len(_memory_extraction_debug_cache) >= _MEMORY_DEBUG_CACHE_MAX_SIZE:
        oldest_key = min(
            _memory_extraction_debug_cache,
            key=lambda k: _memory_extraction_debug_cache[k][0],
        )
        _memory_extraction_debug_cache.pop(oldest_key, None)
    _memory_extraction_debug_cache[run_id] = (time.monotonic(), data)


def get_memory_extraction_debug(run_id: str) -> dict[str, Any] | None:
    """Retrieve and consume debug data for streaming service.

    Args:
        run_id: Pipeline run_id.

    Returns:
        Debug dict or None.
    """
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
    return entry[1]


# ============================================================================
# Main Extraction Function
# ============================================================================


async def extract_memories_background(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    personality_instruction: str | None = None,
    conversation_id: str | None = None,
    parent_run_id: str | None = None,
    query_embedding: list[float] | None = None,
) -> int:
    """Background psychoanalytical extraction from conversation.

    OPTIMIZED: Only analyzes the LAST user message with minimal context.
    Uses pre-computed embedding for semantic dedup search.
    Supports create/update/delete actions (micro-consolidation).

    Args:
        user_id: Target user ID.
        messages: Conversation messages.
        session_id: Current session ID.
        personality_instruction: Optional personality context.
        conversation_id: Optional conversation UUID.
        parent_run_id: Pipeline run_id for token UPSERT and debug cache.
        query_embedding: Pre-computed embedding from centralized service.

    Returns:
        Number of actions applied (create/update/delete).
    """
    from src.infrastructure.database.session import get_db_context

    try:
        if not settings.memory_extraction_enabled:
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

        if not messages:
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

        # Set embedding context for cost tracking
        set_embedding_context(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

        # Find the LAST HumanMessage
        last_human_message: HumanMessage | None = None
        last_human_index = -1
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, HumanMessage):
                last_human_message = msg
                last_human_index = i
                break

        if not last_human_message:
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

        # Get context messages (last 4 before target)
        context_start = max(0, last_human_index - 3)
        context_messages = messages[context_start : last_human_index + 1]
        conversation = _format_messages_for_extraction(context_messages)

        # ================================================================
        # Semantic search for dedup + relationships (using pre-computed embedding or local)
        # ================================================================
        existing_results: list[tuple[Any, float]] = []
        known_relationships: list[str] = []
        existing_memories_text: str = "None"
        known_ids: set[str] = set()
        existing_similar_debug: list[dict[str, Any]] = []

        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)

            # Compute embedding if not provided (fallback)
            if query_embedding is None:
                message_content = (
                    last_human_message.content
                    if isinstance(last_human_message.content, str)
                    else str(last_human_message.content)
                )
                truncated_query = message_content[:MEMORY_EXTRACTION_QUERY_TRUNCATION_LENGTH]

                from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

                embeddings = get_memory_embeddings()
                query_embedding = await embeddings.aembed_query(truncated_query)

            if query_embedding:
                # Semantic dedup search
                existing_results = await repo.search_by_relevance(
                    user_id=UUID(user_id),
                    query_embedding=query_embedding,
                    limit=MEMORY_DEDUP_SEARCH_LIMIT,
                    min_score=MEMORY_DEDUP_MIN_SCORE,
                )

                # Relationship enrichment search
                relationship_results = await repo.get_relationships_for_user(
                    user_id=UUID(user_id),
                    query_embedding=query_embedding,
                    limit=MEMORY_RELATIONSHIP_SEARCH_LIMIT,
                    min_score=MEMORY_RELATIONSHIP_MIN_SCORE,
                )
                known_relationships = [m.content for m, _ in relationship_results if m.content]

            # Extract all needed data INSIDE the session (ORM objects are attached)
            existing_memories_text = _format_existing_memories_with_ids(existing_results)
            known_ids = {str(m.id) for m, _ in existing_results}
            # Pre-extract debug data before session closes
            existing_similar_debug = [
                {
                    "content": m.content or "",
                    "category": m.category or "unknown",
                    "score": round(score, 3),
                }
                for m, score in existing_results
            ]

        # Build prompt
        current_datetime = datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M")
        prompt = _get_psychoanalysis_prompt().format(
            conversation=conversation,
            existing_memories=existing_memories_text,
            current_datetime=current_datetime,
            known_relationships=(
                "\n".join(f"- {r}" for r in known_relationships)
                if known_relationships
                else "No known relationships"
            ),
        )

        if personality_instruction:
            prompt += _get_personality_addon_prompt().format(
                personality_instruction=personality_instruction
            )

        # Call LLM
        llm = get_llm("memory_extraction")
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

        # Persist token usage
        llm_config = get_llm_config_for_agent(settings, "memory_extraction")
        await _persist_memory_tokens(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            result=result,
            model_name=llm_config.model,
            parent_run_id=parent_run_id,
            duration_ms=_llm_duration_ms,
        )

        # Build debug metadata
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

        # Parse result into actions
        actions = _parse_extraction_result(result_content)

        if not actions:
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

        # ================================================================
        # Filter hallucinated IDs (same pattern as journal)
        # ================================================================
        valid_actions = []
        for action in actions:
            if action.action in ("update", "delete") and action.memory_id:
                if action.memory_id not in known_ids:
                    logger.warning(
                        "memory_extraction_unknown_memory_id",
                        user_id=user_id,
                        action=action.action,
                        memory_id=action.memory_id,
                    )
                    continue
            valid_actions.append(action)

        if len(valid_actions) < len(actions):
            logger.info(
                "memory_extraction_filtered_hallucinated_ids",
                user_id=user_id,
                original_count=len(actions),
                valid_count=len(valid_actions),
            )
        actions = valid_actions

        # ================================================================
        # Apply actions via MemoryService
        # ================================================================
        applied_count = 0
        stored_memories_debug: list[dict[str, Any]] = []

        # Set embedding context for create operations (auto-embedding)
        set_embedding_context(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

        try:
            async with get_db_context() as db:
                from src.domains.memories.service import MemoryService

                service = MemoryService(db)

                for action in actions:
                    try:
                        if action.action == "create" and action.content and action.category:
                            await service.create_memory(
                                user_id=UUID(user_id),
                                content=action.content,
                                category=action.category,
                                emotional_weight=action.emotional_weight or 0,
                                trigger_topic=action.trigger_topic or "",
                                usage_nuance=action.usage_nuance or "",
                                importance=action.importance or 0.7,
                            )
                            applied_count += 1
                            stored_memories_debug.append(
                                {
                                    "action": "create",
                                    "content": action.content,
                                    "category": action.category,
                                    "emotional_weight": action.emotional_weight or 0,
                                    "importance": round(action.importance or 0.7, 2),
                                    "stored": True,
                                }
                            )

                        elif action.action == "update" and action.memory_id:
                            from src.domains.memories.repository import MemoryRepository as _Repo

                            repo = _Repo(db)
                            memory = await repo.get_by_id(UUID(action.memory_id))
                            if memory and str(memory.user_id) == user_id:
                                if memory.pinned:
                                    logger.info(
                                        "memory_extraction_pinned_skip",
                                        user_id=user_id,
                                        action="update",
                                        memory_id=action.memory_id,
                                    )
                                    continue
                                await service.update_memory(
                                    memory=memory,
                                    content=action.content,
                                    emotional_weight=action.emotional_weight,
                                    trigger_topic=action.trigger_topic,
                                    usage_nuance=action.usage_nuance,
                                    importance=action.importance,
                                )
                                applied_count += 1
                                stored_memories_debug.append(
                                    {
                                        "action": "update",
                                        "memory_id": action.memory_id,
                                        "content": action.content or memory.content,
                                        "category": memory.category,
                                        "emotional_weight": (
                                            action.emotional_weight
                                            if action.emotional_weight is not None
                                            else memory.emotional_weight
                                        ),
                                        "importance": round(
                                            (
                                                action.importance
                                                if action.importance is not None
                                                else memory.importance
                                            ),
                                            2,
                                        ),
                                        "trigger_topic": memory.trigger_topic,
                                        "stored": True,
                                    }
                                )

                        elif action.action == "delete" and action.memory_id:
                            from src.domains.memories.repository import MemoryRepository as _Repo

                            repo = _Repo(db)
                            memory = await repo.get_by_id(UUID(action.memory_id))
                            if memory and str(memory.user_id) == user_id:
                                if memory.pinned:
                                    logger.info(
                                        "memory_extraction_pinned_skip",
                                        user_id=user_id,
                                        action="delete",
                                        memory_id=action.memory_id,
                                    )
                                    continue
                                await service.delete_memory(memory)
                                applied_count += 1
                                stored_memories_debug.append(
                                    {
                                        "action": "delete",
                                        "memory_id": action.memory_id,
                                        "content": memory.content,
                                        "category": memory.category,
                                        "emotional_weight": memory.emotional_weight,
                                        "importance": round(memory.importance, 2),
                                        "trigger_topic": memory.trigger_topic,
                                        "stored": True,
                                    }
                                )

                    except Exception as e:
                        logger.warning(
                            "memory_extraction_action_failed",
                            user_id=user_id,
                            action=action.action,
                            error=str(e),
                        )
                        stored_memories_debug.append(
                            {
                                "action": action.action,
                                "content": action.content or "",
                                "category": "unknown",
                                "emotional_weight": 0,
                                "importance": 0.5,
                                "trigger_topic": "",
                                "stored": False,
                            }
                        )
                        continue

                await db.commit()
        finally:
            clear_embedding_context()

        logger.info(
            "memory_extraction_completed",
            user_id=user_id,
            session_id=session_id,
            actions_parsed=len(actions),
            actions_applied=applied_count,
        )

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

        return applied_count

    except Exception as e:
        logger.error(
            "memory_extraction_failed",
            user_id=user_id,
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
        clear_embedding_context()


async def extract_memories_from_single_message(
    user_id: str,
    message: str,
    personality_instruction: str | None = None,
) -> int:
    """Extract memories from a single user message.

    Args:
        user_id: Target user ID.
        message: Single user message.
        personality_instruction: Optional personality context.

    Returns:
        Number of memories extracted.
    """
    messages: list[BaseMessage] = [HumanMessage(content=message)]
    return await extract_memories_background(
        user_id=user_id,
        messages=messages,
        session_id="single_message",
        personality_instruction=personality_instruction,
    )
