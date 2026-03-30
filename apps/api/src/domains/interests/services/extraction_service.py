"""
Background Interest Extraction Service.

Performs asynchronous interest extraction from conversations to build
the user's interest profile. Runs in background after response generation
to avoid blocking the main conversation flow.

Key features:
- Fire-and-forget pattern with safe_fire_and_forget
- Extract 0-2 interests per conversation turn
- Deduplication against existing interests via embedding similarity
- Token tracking via TrackingContext
- DRY architecture with shared _analyze_interests_core()
- Redis cache to avoid duplicate LLM calls between debug and background

Architecture:
    response_node -> safe_fire_and_forget(extract_interests_background(...))
                                          |
                         [Background Task - Non-blocking]
                                          |
                         LLM analysis -> new/consolidated interests -> PostgreSQL

    streaming_service -> analyze_interests_for_debug(...)
                                          |
                         [Sync - for debug panel]
                                          |
                         LLM analysis (cached) -> debug data -> SSE

Example:
    >>> from src.infrastructure.async_utils import safe_fire_and_forget
    >>> safe_fire_and_forget(
    ...     extract_interests_background(user_id, messages, session_id),
    ...     name="interest_extraction"
    ... )

References:
    - Pattern: memory_extractor.py
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import settings
from src.core.constants import (
    INTEREST_ACTIVE_LIST_LIMIT,
    INTEREST_ANALYSIS_CACHE_TTL,
    INTEREST_EXTRACTION_MIN_CONFIDENCE,
    INTEREST_EXTRACTION_QUERY_TRUNCATION_LENGTH,
    REDIS_KEY_INTEREST_ANALYSIS_PREFIX,
)
from src.core.i18n_types import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts import load_prompt
from src.domains.interests.models import UserInterest
from src.domains.interests.repository import InterestRepository
from src.domains.interests.schemas import ExtractedInterest
from src.infrastructure.database import get_db_context
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class InterestAnalysisResult:
    """
    Result of interest extraction analysis (LLM-based).

    Used by both debug panel and background extraction to avoid
    duplicate LLM calls via caching.
    """

    # Analysis metadata
    analyzed: bool = False
    analysis_skipped_reason: str | None = None

    # Extracted interests from LLM
    extracted_interests: list[ExtractedInterest] = field(default_factory=list)

    # LLM call metadata
    llm_model: str | None = None
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_cached_tokens: int = 0
    llm_temperature: float = 0.0

    # Context info
    analyzed_message: str | None = None
    context_messages_count: int = 0

    # LLM call duration for debug panel
    llm_duration_ms: float = 0.0

    # Raw AIMessage for token persistence (not serialized to cache)
    _raw_result: AIMessage | None = field(default=None, repr=False)

    def to_cache_dict(self) -> dict:
        """Serialize to dict for Redis cache (excludes _raw_result)."""
        return {
            "analyzed": self.analyzed,
            "analysis_skipped_reason": self.analysis_skipped_reason,
            "extracted_interests": [
                {
                    "action": i.action,
                    "interest_id": i.interest_id,
                    "topic": i.topic or "",
                    "category": i.category.value if i.category else "other",
                    "confidence": i.confidence if i.confidence is not None else 0.0,
                }
                for i in self.extracted_interests
            ],
            "llm_model": self.llm_model,
            "llm_input_tokens": self.llm_input_tokens,
            "llm_output_tokens": self.llm_output_tokens,
            "llm_cached_tokens": self.llm_cached_tokens,
            "llm_temperature": self.llm_temperature,
            "analyzed_message": self.analyzed_message,
            "context_messages_count": self.context_messages_count,
        }

    @classmethod
    def from_cache_dict(cls, data: dict) -> "InterestAnalysisResult":
        """Deserialize from Redis cache dict."""
        extracted = []
        for item in data.get("extracted_interests", []):
            try:
                extracted.append(ExtractedInterest(**item))
            except Exception:
                continue

        return cls(
            analyzed=data.get("analyzed", False),
            analysis_skipped_reason=data.get("analysis_skipped_reason"),
            extracted_interests=extracted,
            llm_model=data.get("llm_model"),
            llm_input_tokens=data.get("llm_input_tokens", 0),
            llm_output_tokens=data.get("llm_output_tokens", 0),
            llm_cached_tokens=data.get("llm_cached_tokens", 0),
            llm_temperature=data.get("llm_temperature", 0.0),
            analyzed_message=data.get("analyzed_message"),
            context_messages_count=data.get("context_messages_count", 0),
        )


# ============================================================================
# Redis Cache for Analysis Results
# ============================================================================


def _compute_analysis_cache_key(user_id: str, message_content: str) -> str:
    """
    Compute Redis cache key for interest analysis.

    Key is based on user_id and hash of the analyzed message content.
    This ensures the same message analyzed twice uses cached result.
    """
    content_hash = hashlib.sha256(message_content.encode()).hexdigest()[:16]
    return f"{REDIS_KEY_INTEREST_ANALYSIS_PREFIX}{user_id}:{content_hash}"


async def _get_cached_analysis(cache_key: str) -> InterestAnalysisResult | None:
    """Retrieve cached analysis result from Redis."""
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()

        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            logger.debug(
                "interest_analysis_cache_hit",
                cache_key=cache_key,
            )
            return InterestAnalysisResult.from_cache_dict(data)

        return None

    except Exception as e:
        logger.debug(
            "interest_analysis_cache_get_failed",
            cache_key=cache_key,
            error=str(e),
        )
        return None


async def _set_cached_analysis(cache_key: str, result: InterestAnalysisResult) -> None:
    """Store analysis result in Redis cache."""
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()

        await redis.set(
            cache_key,
            json.dumps(result.to_cache_dict()),
            ex=INTEREST_ANALYSIS_CACHE_TTL,
        )

        logger.debug(
            "interest_analysis_cache_set",
            cache_key=cache_key,
            ttl=INTEREST_ANALYSIS_CACHE_TTL,
        )

    except Exception as e:
        logger.debug(
            "interest_analysis_cache_set_failed",
            cache_key=cache_key,
            error=str(e),
        )


# ============================================================================
# Token Persistence for Background Interest Tasks
# ============================================================================


async def _persist_interest_tokens(
    user_id: str,
    session_id: str,
    conversation_id: str | None,
    result: AIMessage,
    model_name: str,
    parent_run_id: str | None = None,
    duration_ms: float = 0.0,
) -> None:
    """
    Persist token usage from interest extraction LLM call to database.

    Uses TrackingContext to reuse existing persistence infrastructure:
    - TokenUsageLog (detailed node breakdown)
    - MessageTokenSummary (aggregated per run)
    - UserStatistics (cumulative per user)

    Args:
        user_id: User ID for statistics
        session_id: Session/thread ID
        conversation_id: Conversation UUID (optional, for linking)
        result: AIMessage with usage_metadata
        model_name: LLM model used for extraction
        parent_run_id: If provided, UPSERT tokens into the parent message's
            MessageTokenSummary instead of creating an orphan record.
    """
    from src.domains.chat.service import TrackingContext

    try:
        # Extract token usage from AIMessage.usage_metadata
        usage_metadata = getattr(result, "usage_metadata", None)
        if not usage_metadata:
            logger.debug(
                "interest_tokens_no_usage_metadata",
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
                "interest_tokens_zero_usage",
                user_id=user_id,
            )
            return

        # Use parent_run_id to UPSERT into the originating message's summary,
        # or generate a standalone run_id for backward compatibility
        run_id = parent_run_id or f"interest_extract_{uuid.uuid4().hex[:12]}"

        # Parse conversation_id if provided
        conv_uuid: UUID | None = None
        if conversation_id:
            try:
                conv_uuid = UUID(conversation_id)
            except ValueError:
                logger.warning(
                    "interest_tokens_invalid_conversation_id",
                    conversation_id=conversation_id,
                )

        # Create TrackingContext for persistence
        async with TrackingContext(
            run_id=run_id,
            user_id=UUID(user_id),
            session_id=session_id,
            conversation_id=conv_uuid,
            auto_commit=False,
        ) as tracker:
            await tracker.record_node_tokens(
                node_name="interest_extraction",
                model_name=model_name,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                cached_tokens=cached_tokens,
                duration_ms=duration_ms,
            )
            await tracker.commit()

        logger.info(
            "interest_tokens_persisted",
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            model_name=model_name,
        )

    except Exception as e:
        # Graceful degradation - token persistence failure must not break extraction
        logger.error(
            "interest_tokens_persistence_failed",
            user_id=user_id,
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )


async def _persist_interest_tokens_from_metadata(
    user_id: str,
    session_id: str,
    conversation_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    model_name: str,
    parent_run_id: str | None = None,
) -> None:
    """
    Persist token usage from cached metadata (when cache hit occurs).

    This is used when extract_interests_background() reads from cache
    (because analyze_interests_for_debug() already ran). The tokens
    must still be persisted for accurate cost tracking.

    Args:
        user_id: User ID for statistics
        session_id: Session/thread ID
        conversation_id: Conversation UUID (optional, for linking)
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cached_tokens: Number of cached tokens
        model_name: LLM model used for extraction
        parent_run_id: If provided, UPSERT tokens into the parent message's
            MessageTokenSummary instead of creating an orphan record.
    """
    from src.domains.chat.service import TrackingContext

    try:
        if input_tokens == 0 and output_tokens == 0:
            logger.debug(
                "interest_tokens_from_cache_zero_usage",
                user_id=user_id,
            )
            return

        # Use parent_run_id to UPSERT into the originating message's summary,
        # or generate a standalone run_id for backward compatibility
        run_id = parent_run_id or f"interest_extract_cached_{uuid.uuid4().hex[:12]}"

        # Parse conversation_id if provided
        conv_uuid: UUID | None = None
        if conversation_id:
            try:
                conv_uuid = UUID(conversation_id)
            except ValueError:
                logger.warning(
                    "interest_tokens_invalid_conversation_id",
                    conversation_id=conversation_id,
                )

        # Create TrackingContext for persistence
        async with TrackingContext(
            run_id=run_id,
            user_id=UUID(user_id),
            session_id=session_id,
            conversation_id=conv_uuid,
            auto_commit=False,
        ) as tracker:
            await tracker.record_node_tokens(
                node_name="interest_extraction",
                model_name=model_name,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                cached_tokens=cached_tokens,
                # Cache hit: no LLM call, duration unknown
            )
            await tracker.commit()

        logger.info(
            "interest_tokens_persisted_from_cache",
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            model_name=model_name,
        )

    except Exception as e:
        # Graceful degradation
        logger.error(
            "interest_tokens_from_cache_persistence_failed",
            user_id=user_id,
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )


# ============================================================================
# Utility Functions
# ============================================================================


def _get_extraction_prompt() -> str:
    """Load the interest extraction prompt from file."""
    return str(load_prompt("interest_extraction_prompt"))


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
    max_chars = INTEREST_EXTRACTION_QUERY_TRUNCATION_LENGTH

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
        # Truncate very long messages
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        lines.append(f"{prefix}: {content}")

    return "\n".join(lines)


def _parse_extraction_result(result_text: str) -> list[ExtractedInterest]:
    """
    Parse LLM extraction result into ExtractedInterest objects.

    Handles common JSON parsing issues (markdown fences, whitespace, comments).

    Args:
        result_text: Raw LLM output

    Returns:
        List of validated ExtractedInterest objects
    """
    import re

    # Clean common LLM artifacts
    cleaned = result_text.strip()

    # Remove markdown code fences if present
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

    # Remove trailing commas before ] or }
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)

    def extract_json_array(text: str) -> str | None:
        """Extract first valid-looking JSON array from text."""
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

    # Try direct parsing first
    try:
        data = json.loads(cleaned)

        if not isinstance(data, list):
            logger.warning("interest_extraction_result_not_list", type=type(data).__name__)
            return []

        interests = []
        for item in data:
            try:
                action = item.get("action", "create")

                # Filter by minimum confidence (only for create actions)
                if action == "create":
                    confidence = item.get("confidence", 0)
                    if confidence < INTEREST_EXTRACTION_MIN_CONFIDENCE:
                        logger.debug(
                            "interest_extraction_low_confidence",
                            topic=item.get("topic", "")[:50],
                            confidence=confidence,
                        )
                        continue

                interest = ExtractedInterest(**item)
                interests.append(interest)
            except Exception as e:
                logger.debug(
                    "interest_item_validation_failed",
                    item=item,
                    error=str(e),
                )
                continue

        return interests

    except json.JSONDecodeError as e:
        logger.warning(
            "interest_extraction_json_parse_failed",
            error=str(e),
            result_length=len(cleaned),
            result_preview=cleaned[:500] if cleaned else "empty",
        )

        # Try to extract JSON array from potentially malformed response
        extracted = extract_json_array(cleaned)
        if extracted:
            try:
                extracted = re.sub(r",\s*([\]}])", r"\1", extracted)
                data = json.loads(extracted)

                if isinstance(data, list):
                    interests = []
                    for item in data:
                        try:
                            action = item.get("action", "create")
                            if action == "create":
                                confidence = item.get("confidence", 0)
                                if confidence < INTEREST_EXTRACTION_MIN_CONFIDENCE:
                                    continue
                            interest = ExtractedInterest(**item)
                            interests.append(interest)
                        except Exception:
                            continue

                    if interests:
                        logger.info(
                            "interest_extraction_json_recovered",
                            recovered_count=len(interests),
                        )
                        return interests
            except json.JSONDecodeError:
                pass

        return []


async def _find_similar_interest(
    repo: InterestRepository,
    user_id: UUID,
    topic: str,
    existing_interests: list[UserInterest],
) -> tuple[bool, UserInterest | None]:
    """
    Find if a similar interest already exists using semantic similarity.

    Uses embedding-based cosine similarity when embeddings are available,
    with fallback to string matching for interests without embeddings.

    Args:
        repo: InterestRepository instance
        user_id: User UUID
        topic: Topic to check
        existing_interests: List of existing UserInterest objects

    Returns:
        Tuple of (is_similar, matching_interest or None)
    """
    # Generate embedding for the new topic
    from src.domains.interests.helpers import generate_interest_embedding

    topic_embedding = generate_interest_embedding(topic)

    best_match: UserInterest | None = None
    best_similarity: float = 0.0

    for interest in existing_interests:
        # Try embedding-based similarity first
        if topic_embedding and interest.embedding:
            from src.infrastructure.llm.local_embeddings import cosine_similarity

            similarity = cosine_similarity(topic_embedding, interest.embedding)

            if similarity >= settings.interest_dedup_similarity_threshold:
                logger.debug(
                    "interest_similarity_embedding_match",
                    new_topic=topic[:50],
                    existing_topic=interest.topic[:50],
                    similarity=round(similarity, 3),
                    threshold=settings.interest_dedup_similarity_threshold,
                )
                # Track best match in case multiple are above threshold
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = interest

        # Fallback: string-based matching for interests without embeddings
        elif not interest.embedding:
            if interest.topic.lower() in topic.lower() or topic.lower() in interest.topic.lower():
                logger.debug(
                    "interest_similarity_string_match",
                    new_topic=topic[:50],
                    existing_topic=interest.topic[:50],
                )
                return True, interest

    if best_match:
        # INFO-level log for production monitoring of deduplication decisions
        logger.info(
            "interest_dedup_match_found",
            new_topic=topic[:50],
            matched_topic=best_match.topic[:50],
            similarity=round(best_similarity, 4),
            threshold=settings.interest_dedup_similarity_threshold,
            matched_interest_id=str(best_match.id),
        )
        return True, best_match

    return False, None


# ============================================================================
# Core Analysis Function (DRY - used by both debug and background)
# ============================================================================


async def _analyze_interests_core(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    user_language: str = settings.default_language,
    use_cache: bool = True,
) -> InterestAnalysisResult:
    """
    Core interest extraction analysis (LLM-based).

    This is the shared implementation used by both:
    - analyze_interests_for_debug() - for debug panel display
    - extract_interests_background() - for background persistence

    Uses Redis cache to avoid duplicate LLM calls when the same message
    is analyzed by both functions.

    Args:
        user_id: Target user ID
        messages: Conversation messages to analyze
        session_id: Session ID for logging
        user_language: User's preferred language (default: fr)
        use_cache: Whether to use Redis cache (default True)

    Returns:
        InterestAnalysisResult with extracted interests and metadata
    """
    # Check if interest extraction is enabled
    if not settings.interest_extraction_enabled:
        return InterestAnalysisResult(
            analyzed=False,
            analysis_skipped_reason="Feature disabled globally",
        )

    # Skip if no messages
    if not messages:
        return InterestAnalysisResult(
            analyzed=False,
            analysis_skipped_reason="No messages to analyze",
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
        return InterestAnalysisResult(
            analyzed=False,
            analysis_skipped_reason="No user message in conversation",
        )

    # Get message content for cache key
    message_content = (
        last_human_message.content
        if isinstance(last_human_message.content, str)
        else str(last_human_message.content)
    )

    # Check cache first
    cache_key = _compute_analysis_cache_key(user_id, message_content)
    if use_cache:
        cached = await _get_cached_analysis(cache_key)
        if cached:
            logger.debug(
                "interest_analysis_using_cache",
                user_id=user_id,
                cache_key=cache_key,
            )
            return cached

    # Get minimal context: last 4 messages before the target message
    context_start = max(0, last_human_index - 3)
    context_messages = messages[context_start : last_human_index + 1]

    user_uuid = UUID(user_id)

    # Use database context for interest operations
    async with get_db_context() as db:
        repo = InterestRepository(db)

        # Retrieve existing interests for deduplication
        existing_interests = await repo.get_active_for_user(
            user_uuid, limit=settings.interest_dedup_search_limit
        )

        existing_texts = [
            f"- [id={interest.id}] {interest.topic} ({interest.category})"
            for interest in existing_interests
        ]

        # Format conversation with context
        conversation = _format_messages_for_extraction(context_messages)

        # Build prompt from external file
        current_datetime = datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M")
        prompt = _get_extraction_prompt().format(
            conversation=conversation,
            existing_interests=(
                "\n".join(existing_texts) if existing_texts else "Aucun interet connu"
            ),
            current_datetime=current_datetime,
            user_language=get_language_name(user_language),
        )

        # Get extraction LLM from unified config (LLM_DEFAULTS + admin overrides)
        llm = get_llm("interest_extraction")

        # DEBUG: Log what we're sending to LLM
        logger.info(
            "interest_extraction_llm_input",
            user_id=user_id,
            session_id=session_id,
            conversation_preview=conversation[:500] if conversation else "EMPTY",
            existing_interests_preview=(
                "\n".join(existing_texts)[:200] if existing_texts else "Aucun"
            ),
            user_language=user_language,
        )

        # Invoke LLM with instrumentation for token tracking
        import time as _time

        _llm_start = _time.time()
        result = await invoke_with_instrumentation(
            llm=llm,
            llm_type="interest_extraction",
            messages=prompt,
            session_id=session_id,
            user_id=user_id,
        )
        _llm_duration_ms = (_time.time() - _llm_start) * 1000
        result_content = result.content if isinstance(result.content, str) else str(result.content)

        # DEBUG: Log LLM response
        logger.info(
            "interest_extraction_llm_output",
            user_id=user_id,
            session_id=session_id,
            result_content=result_content[:500] if result_content else "EMPTY",
        )

        # Extract LLM metadata
        usage_metadata = getattr(result, "usage_metadata", {}) or {}
        raw_input_tokens = usage_metadata.get("input_tokens", 0)
        output_tokens = usage_metadata.get("output_tokens", 0)
        input_details = usage_metadata.get("input_token_details", {})
        cached_tokens = input_details.get("cache_read", 0) if input_details else 0
        input_tokens = raw_input_tokens - cached_tokens

        # Parse extraction result
        extracted_interests = _parse_extraction_result(result_content)

        # Build result
        analysis_result = InterestAnalysisResult(
            analyzed=True,
            extracted_interests=extracted_interests,
            llm_model=get_llm_config_for_agent(settings, "interest_extraction").model,
            llm_input_tokens=input_tokens,
            llm_output_tokens=output_tokens,
            llm_cached_tokens=cached_tokens,
            llm_temperature=get_llm_config_for_agent(settings, "interest_extraction").temperature,
            analyzed_message=(
                message_content[:200] + "..." if len(message_content) > 200 else message_content
            ),
            context_messages_count=len(context_messages),
            llm_duration_ms=_llm_duration_ms,
            _raw_result=result,
        )

        # Store in cache
        if use_cache:
            await _set_cached_analysis(cache_key, analysis_result)

        logger.debug(
            "interest_analysis_completed",
            user_id=user_id,
            session_id=session_id,
            extracted_count=len(extracted_interests),
            from_cache=False,
        )

        return analysis_result


# ============================================================================
# Public API: Background Extraction (Fire-and-Forget)
# ============================================================================


async def extract_interests_background(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    conversation_id: str | None = None,
    user_language: str = settings.default_language,
    parent_run_id: str | None = None,
) -> int:
    """
    Background interest extraction from conversation.

    OPTIMIZED: Only analyzes the LAST user message to avoid:
    - Reprocessing already-analyzed messages (cost savings)
    - Duplicate interest extraction
    - Analyzing assistant messages (no user info there)

    Uses _analyze_interests_core() with Redis cache to avoid duplicate
    LLM calls if analyze_interests_for_debug() already ran.

    Token Tracking:
        LLM tokens are persisted to database for:
        - UserStatistics (dashboard cumulative)
        - MessageTokenSummary (conversation totals, deferred)

    Args:
        user_id: Target user ID
        messages: Conversation messages to analyze
        session_id: Current session ID for logging
        conversation_id: Optional conversation UUID for linking token costs
        user_language: User's preferred language for LLM output (default: fr)

    Returns:
        Number of new interests extracted and stored

    Example:
        >>> safe_fire_and_forget(
        ...     extract_interests_background(
        ...         "user-123", messages, "session-456",
        ...         conversation_id="conv-uuid",
        ...         user_language="en"
        ...     ),
        ...     name="interest_extraction"
        ... )
    """
    try:
        # Run core analysis (uses cache if available)
        analysis = await _analyze_interests_core(
            user_id=user_id,
            messages=messages,
            session_id=session_id,
            user_language=user_language,
            use_cache=True,
        )

        if not analysis.analyzed:
            logger.debug(
                "interest_extraction_skipped",
                user_id=user_id,
                reason=analysis.analysis_skipped_reason,
            )
            return 0

        # Persist tokens - use raw result if available, otherwise use cached metadata
        # This ensures tokens are always persisted even if debug panel ran first
        if analysis._raw_result:
            # Fresh LLM call - persist using AIMessage
            await _persist_interest_tokens(
                user_id=user_id,
                session_id=session_id,
                conversation_id=conversation_id,
                result=analysis._raw_result,
                model_name=analysis.llm_model
                or get_llm_config_for_agent(settings, "interest_extraction").model,
                parent_run_id=parent_run_id,
                duration_ms=analysis.llm_duration_ms,
            )
        elif analysis.llm_input_tokens > 0 or analysis.llm_output_tokens > 0:
            # From cache - persist using stored metadata
            await _persist_interest_tokens_from_metadata(
                user_id=user_id,
                session_id=session_id,
                conversation_id=conversation_id,
                input_tokens=analysis.llm_input_tokens,
                output_tokens=analysis.llm_output_tokens,
                cached_tokens=analysis.llm_cached_tokens,
                model_name=analysis.llm_model
                or get_llm_config_for_agent(settings, "interest_extraction").model,
                parent_run_id=parent_run_id,
            )

        if not analysis.extracted_interests:
            logger.debug(
                "interest_extraction_no_new_interests",
                user_id=user_id,
                session_id=session_id,
            )
            return 0

        # Process each extracted interest action (create/update/delete)
        user_uuid = UUID(user_id)
        stored_count = 0

        async with get_db_context() as db:
            repo = InterestRepository(db)

            # Retrieve existing interests for deduplication (create actions)
            existing_interests = await repo.get_active_for_user(
                user_uuid, limit=settings.interest_dedup_search_limit
            )
            known_interest_ids = {str(i.id) for i in existing_interests}

            for extracted in analysis.extracted_interests:
                try:
                    # ── DELETE action ──
                    if extracted.action == "delete" and extracted.interest_id:
                        if extracted.interest_id not in known_interest_ids:
                            logger.warning(
                                "interest_extraction_unknown_id",
                                user_id=user_id,
                                action="delete",
                                interest_id=extracted.interest_id,
                            )
                            continue
                        interest = await repo.get_by_id(UUID(extracted.interest_id))
                        if interest and str(interest.user_id) == user_id:
                            await repo.delete(interest)
                            logger.info(
                                "interest_deleted_by_extraction",
                                user_id=user_id,
                                interest_id=extracted.interest_id,
                                topic=interest.topic[:50],
                            )
                            stored_count += 1
                        continue

                    # ── UPDATE action ──
                    if extracted.action == "update" and extracted.interest_id:
                        if extracted.interest_id not in known_interest_ids:
                            logger.warning(
                                "interest_extraction_unknown_id",
                                user_id=user_id,
                                action="update",
                                interest_id=extracted.interest_id,
                            )
                            continue
                        interest = await repo.get_by_id(UUID(extracted.interest_id))
                        if interest and str(interest.user_id) == user_id:
                            if extracted.topic:
                                interest.topic = extracted.topic
                                # Re-embed with updated topic
                                from src.domains.interests.helpers import (
                                    generate_interest_embedding,
                                )

                                interest.embedding = generate_interest_embedding(extracted.topic)
                            if extracted.category:
                                interest.category = extracted.category.value
                            await repo.consolidate_on_mention(interest)
                            logger.info(
                                "interest_updated_by_extraction",
                                user_id=user_id,
                                interest_id=extracted.interest_id,
                                topic=interest.topic[:50],
                            )
                            stored_count += 1
                        continue

                    # ── CREATE action (default, backward-compatible) ──
                    if not extracted.topic or not extracted.category:
                        continue

                    # Check for similar existing interest (dedup)
                    is_similar, existing = await _find_similar_interest(
                        repo, user_uuid, extracted.topic, existing_interests
                    )

                    if is_similar and existing:
                        # Consolidate: increment positive signals
                        await repo.consolidate_on_mention(existing)
                        logger.info(
                            "interest_consolidated",
                            user_id=user_id,
                            interest_id=str(existing.id),
                            topic=existing.topic[:50],
                            positive_signals=existing.positive_signals,
                        )
                        stored_count += 1
                    else:
                        # Compute embedding for the topic (for deduplication)
                        from src.domains.interests.helpers import generate_interest_embedding

                        topic_embedding = generate_interest_embedding(extracted.topic)

                        # Create new interest
                        new_interest = await repo.create(
                            user_id=user_uuid,
                            topic=extracted.topic,
                            category=extracted.category.value,
                            embedding=topic_embedding,
                        )
                        logger.info(
                            "interest_created",
                            user_id=user_id,
                            interest_id=str(new_interest.id),
                            topic=extracted.topic[:50],
                            category=extracted.category.value,
                            confidence=extracted.confidence,
                        )
                        stored_count += 1

                except Exception as e:
                    logger.warning(
                        "interest_storage_failed",
                        user_id=user_id,
                        topic=extracted.topic[:50] if extracted.topic else "",
                        error=str(e),
                    )
                    continue

            # Commit all changes
            await db.commit()

            logger.info(
                "interest_extraction_completed",
                user_id=user_id,
                session_id=session_id,
                extracted_count=len(analysis.extracted_interests),
                stored_count=stored_count,
            )

            return stored_count

    except Exception as e:
        logger.error(
            "interest_extraction_failed",
            user_id=user_id,
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )
        return 0


# ============================================================================
# Public API: Debug Panel Analysis
# ============================================================================


async def analyze_interests_for_debug(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    user_language: str = settings.default_language,
) -> dict:
    """
    Analyze conversation for interests (debug panel - LLM-based).

    Uses _analyze_interests_core() with Redis cache. Results are cached
    so that extract_interests_background() can reuse them without
    making another LLM call.

    This function does NOT persist interests to database - it only
    returns debug information for the debug panel.

    Args:
        user_id: Target user ID
        messages: Conversation messages to analyze
        session_id: Session ID for logging
        user_language: User's preferred language for LLM output (default: fr)

    Returns:
        Dict with:
        - enabled: bool (feature enabled)
        - analyzed: bool (whether analysis was performed)
        - extracted_interests: list of extracted interests with confidence
        - matching_decisions: list of dedup/consolidation decisions
        - existing_interests: list of current user interests
        - llm_metadata: tokens used, model, etc.
        - error: str if any error occurred

    Example:
        >>> result = await analyze_interests_for_debug("user-123", messages, "session-456", "en")
        >>> # Returns: {
        >>> #   "enabled": True,
        >>> #   "analyzed": True,
        >>> #   "extracted_interests": [
        >>> #     {"topic": "iOS development", "category": "technology", "confidence": 0.85}
        >>> #   ],
        >>> #   ...
        >>> # }
    """
    try:
        # Check if interest extraction is enabled
        if not settings.interest_extraction_enabled:
            return {
                "enabled": False,
                "analyzed": False,
                "extracted_interests": [],
                "matching_decisions": [],
                "existing_interests": [],
                "llm_metadata": None,
                "analysis_skipped_reason": "Feature disabled globally",
            }

        # Run core analysis (results are cached for background extraction)
        analysis = await _analyze_interests_core(
            user_id=user_id,
            messages=messages,
            session_id=session_id,
            user_language=user_language,
            use_cache=True,
        )

        if not analysis.analyzed:
            return {
                "enabled": True,
                "analyzed": False,
                "extracted_interests": [],
                "matching_decisions": [],
                "existing_interests": [],
                "llm_metadata": None,
                "analysis_skipped_reason": analysis.analysis_skipped_reason,
            }

        # Build LLM metadata
        llm_metadata = {
            "model": analysis.llm_model,
            "input_tokens": analysis.llm_input_tokens,
            "output_tokens": analysis.llm_output_tokens,
            "cached_tokens": analysis.llm_cached_tokens,
            "total_tokens": (
                analysis.llm_input_tokens + analysis.llm_output_tokens + analysis.llm_cached_tokens
            ),
            "temperature": analysis.llm_temperature,
        }

        # Build extracted interests data (include action/interest_id for debug panel)
        # Provide safe defaults for fields the frontend accesses (topic, confidence)
        extracted_interests_data = [
            {
                "action": interest.action,
                "interest_id": interest.interest_id,
                "topic": interest.topic or "(deleted)",
                "category": interest.category.value if interest.category else "other",
                "confidence": round(interest.confidence, 3) if interest.confidence else 0.0,
            }
            for interest in analysis.extracted_interests
        ]

        # Get existing interests for matching decisions
        user_uuid = UUID(user_id)
        async with get_db_context() as db:
            repo = InterestRepository(db)

            existing_interests = await repo.get_active_for_user(
                user_uuid, limit=settings.interest_dedup_search_limit
            )

            # Format existing interests for debug output
            existing_interests_data = [
                {
                    "topic": interest.topic,
                    "category": interest.category,
                    "weight": round(
                        repo.calculate_effective_weight(
                            interest,
                            decay_rate_per_day=settings.interest_decay_rate_per_day,
                        ),
                        3,
                    ),
                    "status": interest.status,
                    "positive_signals": interest.positive_signals,
                    "negative_signals": interest.negative_signals,
                }
                for interest in existing_interests
            ]

            # Determine matching decisions for each extracted interest
            matching_decisions: list[dict[str, str | None]] = []

            for extracted in analysis.extracted_interests:
                # Explicit LLM actions (delete/update) take precedence
                if extracted.action == "delete" and extracted.interest_id:
                    matching_decisions.append(
                        {
                            "extracted_topic": extracted.topic or "N/A",
                            "action": "delete",
                            "interest_id": extracted.interest_id,
                            "matched_interest": None,
                            "reason": "LLM recommends deletion",
                        }
                    )
                    continue

                if extracted.action == "update" and extracted.interest_id:
                    matching_decisions.append(
                        {
                            "extracted_topic": extracted.topic,
                            "action": "update",
                            "interest_id": extracted.interest_id,
                            "matched_interest": None,
                            "reason": "LLM recommends update",
                        }
                    )
                    continue

                # For create actions: show dedup logic
                if not extracted.topic:
                    continue

                is_similar, existing = await _find_similar_interest(
                    repo, user_uuid, extracted.topic, existing_interests
                )

                if is_similar and existing:
                    matching_decisions.append(
                        {
                            "extracted_topic": extracted.topic,
                            "action": "consolidate",
                            "matched_interest": existing.topic,
                            "matched_category": existing.category,
                            "reason": "Similar topic found in existing interests",
                        }
                    )
                else:
                    matching_decisions.append(
                        {
                            "extracted_topic": extracted.topic,
                            "action": "create_new",
                            "matched_interest": None,
                            "reason": "No similar existing interest found",
                        }
                    )

        logger.info(
            "interest_extraction_debug_completed",
            user_id=user_id,
            session_id=session_id,
            extracted_count=len(analysis.extracted_interests),
            existing_count=len(existing_interests),
        )

        return {
            "enabled": True,
            "analyzed": True,
            "extracted_interests": extracted_interests_data,
            "matching_decisions": matching_decisions,
            "existing_interests": existing_interests_data,
            "llm_metadata": llm_metadata,
            "analyzed_message": analysis.analyzed_message,
            "context_messages_count": analysis.context_messages_count,
        }

    except Exception as e:
        logger.warning(
            "analyze_interests_for_debug_failed",
            user_id=user_id,
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )
        return {
            "enabled": True,
            "analyzed": False,
            "extracted_interests": [],
            "matching_decisions": [],
            "existing_interests": [],
            "llm_metadata": None,
            "error": str(e),
        }


# ============================================================================
# Debug Panel: User Interest Profile (DB-only, fast)
# ============================================================================


async def get_user_interests_for_debug(
    user_id: str,
) -> dict:
    """
    Get user's interest profile for debug panel display.

    Returns the user's existing interests with their computed weights,
    without running any LLM analysis (fast, no latency impact).

    Args:
        user_id: Target user ID

    Returns:
        Dict with:
        - enabled: bool (feature enabled)
        - interests: list of interest dicts with topic, category, weight, status
        - total_count: int
        - active_count: int

    Example:
        >>> profile = await get_user_interests_for_debug("user-123")
        >>> # Returns: {
        >>> #   "enabled": True,
        >>> #   "interests": [
        >>> #     {"topic": "iOS development", "category": "technology", "weight": 0.85, "status": "active"}
        >>> #   ],
        >>> #   "total_count": 5,
        >>> #   "active_count": 4
        >>> # }
    """
    try:
        # Check if interest extraction is enabled
        if not settings.interest_extraction_enabled:
            return {
                "enabled": False,
                "interests": [],
                "total_count": 0,
                "active_count": 0,
            }

        user_uuid = UUID(user_id)

        async with get_db_context() as db:
            repo = InterestRepository(db)

            # Get all interests for user (not just active)
            all_interests = await repo.get_all_for_user(user_uuid, limit=INTEREST_ACTIVE_LIST_LIMIT)

            # Calculate weights and build response
            interests_data: list[dict[str, str | float | int]] = []
            active_count = 0

            for interest in all_interests:
                weight = repo.calculate_effective_weight(
                    interest,
                    decay_rate_per_day=settings.interest_decay_rate_per_day,
                )
                is_active = interest.status == "active"
                if is_active:
                    active_count += 1

                interests_data.append(
                    {
                        "topic": interest.topic,
                        "category": interest.category,
                        "weight": round(weight, 3),
                        "status": interest.status,
                        "positive_signals": interest.positive_signals,
                        "negative_signals": interest.negative_signals,
                    }
                )

            # Sort by weight descending
            interests_data.sort(key=lambda x: float(x["weight"]), reverse=True)

            return {
                "enabled": True,
                "interests": interests_data,
                "total_count": len(interests_data),
                "active_count": active_count,
            }

    except Exception as e:
        logger.warning(
            "get_user_interests_for_debug_failed",
            user_id=user_id,
            error=str(e),
        )
        return {
            "enabled": False,
            "interests": [],
            "total_count": 0,
            "active_count": 0,
            "error": str(e),
        }
