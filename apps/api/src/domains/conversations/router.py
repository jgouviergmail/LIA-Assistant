"""
Conversations API router.
REST endpoints for conversation management and message history.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    CONVERSATION_SEARCH_MAX_LENGTH,
    CONVERSATION_SEARCH_MIN_LENGTH,
)
from src.core.dependencies import get_db
from src.core.exceptions import raise_no_active_conversation
from src.core.field_names import (
    FIELD_CONTENT,
    FIELD_CONVERSATION_ID,
    FIELD_CREATED_AT,
    FIELD_TOTAL_COST_EUR,
    FIELD_TOTAL_GOOGLE_API_REQUESTS,
    FIELD_TOTAL_TOKENS_CACHE,
    FIELD_TOTAL_TOKENS_IN,
    FIELD_TOTAL_TOKENS_OUT,
)
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.conversations.schemas import (
    ConversationMessageResponse,
    ConversationMessagesResponse,
    ConversationResetResponse,
    ConversationResponse,
    ConversationStatsResponse,
    ConversationTotalsResponse,
)
from src.domains.conversations.service import ConversationService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get(
    "/me",
    response_model=ConversationResponse | None,
    summary="Get my conversation",
    description="Get current user's active conversation. Returns null if no conversation exists yet (lazy creation).",
)
async def get_my_conversation(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse | None:
    """
    Get current user's active conversation.

    Conversation is created lazily on first message, so this endpoint may return null
    for new users who haven't started chatting yet.

    Returns:
        ConversationResponse if conversation exists, None otherwise
    """
    service = ConversationService()
    conversation = await service.get_active_conversation(current_user.id, db)

    if not conversation:
        logger.debug("conversation_not_found", user_id=str(current_user.id))
        return None

    logger.debug(
        "conversation_retrieved",
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
        message_count=conversation.message_count,
    )

    return ConversationResponse.model_validate(conversation)


@router.get(
    "/me/messages",
    response_model=ConversationMessagesResponse,
    summary="Get conversation messages",
    description="Get message history for current user's conversation. Messages are returned newest first.",
)
async def get_conversation_messages(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of messages to return"),
    search: str | None = Query(
        None,
        min_length=CONVERSATION_SEARCH_MIN_LENGTH,
        max_length=CONVERSATION_SEARCH_MAX_LENGTH,
        description="Optional case-insensitive substring to filter message content",
    ),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationMessagesResponse:
    """
    Get conversation message history for UI display.

    Messages are paginated and returned in descending order (newest first).
    Useful for displaying chat history without deserializing LangGraph checkpoints.

    Args:
        limit: Maximum number of messages (1-200, default 50)
        search: Optional substring filter on message content (case-insensitive
                ILIKE match, accent-sensitive). 2-200 chars.
        current_user: Authenticated user from session dependency.
        db: Database session from FastAPI dependency injection.

    Returns:
        List of messages with conversation metadata

    Raises:
        HTTPException 404: If user has no active conversation
    """
    service = ConversationService()

    # Get conversation
    conversation = await service.get_active_conversation(current_user.id, db)

    if not conversation:
        raise_no_active_conversation(APIMessages.no_active_conversation_start_chatting())

    # Get messages with token usage (auto-routing with feature flag for N+1 optimization)
    # Note: ALL messages are now returned including HITL (APPROVE/REJECT/EDIT/AMBIGUOUS)
    messages = await service.get_messages_with_tokens_auto(
        current_user.id, limit, db, search=search
    )

    # Calculate total_count from messages (consistent with returned data)
    # Count all user messages including HITL responses
    total_user_messages = sum(1 for msg in messages if msg["role"] == "user")

    logger.debug(
        "messages_retrieved",
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
        total_messages=len(messages),
        user_messages=total_user_messages,
        limit=limit,
    )

    return ConversationMessagesResponse(
        messages=[
            ConversationMessageResponse(
                id=msg["id"],
                role=msg["role"],
                content=msg[FIELD_CONTENT],
                message_metadata=msg["message_metadata"],  # Use actual field name from service
                created_at=msg[FIELD_CREATED_AT],
                tokens_in=msg["tokens_in"],
                tokens_out=msg["tokens_out"],
                tokens_cache=msg["tokens_cache"],
                cost_eur=msg["cost_eur"],
                google_api_requests=msg["google_api_requests"],
            )
            for msg in messages
        ],
        conversation_id=conversation.id,
        total_count=total_user_messages,  # Consistent with filtered messages
    )


@router.post(
    "/me/reset",
    response_model=ConversationResetResponse,
    summary="Reset conversation",
    description="Reset conversation: soft delete + purge history. Requires explicit user confirmation on frontend.",
)
async def reset_my_conversation(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationResetResponse:
    """
    Reset user's conversation: soft delete + purge checkpoints.

    This operation:
    - Soft deletes the conversation (sets deleted_at timestamp)
    - Cascade deletes all conversation messages
    - Creates audit log entry
    - Next message will create a new conversation

    IMPORTANT: Frontend MUST show explicit confirmation dialog before calling this endpoint.
    This action is permanent and cannot be undone (soft delete is for audit trail only).

    Returns:
        Success response with previous message count

    Raises:
        HTTPException 404: If user has no active conversation
    """
    service = ConversationService()

    # Get conversation before reset to capture stats
    conversation = await service.get_active_conversation(current_user.id, db)

    if not conversation:
        raise_no_active_conversation(APIMessages.no_active_conversation_to_reset())

    previous_message_count = conversation.message_count

    # Reset conversation (soft delete + audit log)
    await service.reset_conversation(current_user.id, db)

    logger.info(
        "conversation_reset_endpoint",
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
        previous_message_count=previous_message_count,
    )

    return ConversationResetResponse(
        status="success",
        message=APIMessages.conversation_reset_successful(),
        previous_message_count=previous_message_count,
    )


@router.get(
    "/me/stats",
    response_model=ConversationStatsResponse,
    summary="Get conversation statistics",
    description="Get statistics for current user's conversation (message count, tokens, etc.).",
)
async def get_conversation_stats(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationStatsResponse:
    """
    Get conversation statistics.

    Returns summary metrics for the user's active conversation:
    - Total message count
    - Total tokens consumed
    - Creation date
    - Last message timestamp

    Returns:
        Conversation statistics

    Raises:
        HTTPException 404: If user has no active conversation
    """
    service = ConversationService()
    conversation = await service.get_active_conversation(current_user.id, db)

    if not conversation:
        raise_no_active_conversation(APIMessages.no_active_conversation())

    # Get last message timestamp
    messages = await service.get_messages(current_user.id, limit=1, db=db)
    last_message_at = messages[0].created_at if messages else None

    return ConversationStatsResponse(
        conversation_id=conversation.id,
        message_count=conversation.message_count,
        total_tokens=conversation.total_tokens,
        created_at=conversation.created_at,
        last_message_at=last_message_at,
    )


@router.get(
    "/me/totals",
    response_model=ConversationTotalsResponse,
    summary="Get conversation totals",
    description="Get aggregated token usage and recalculated cost for conversation history.",
)
async def get_conversation_totals(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationTotalsResponse:
    """
    Get conversation totals: aggregate tokens and cost from historical messages.

    Sums all token usage from message_token_summary linked to this conversation,
    then recalculates total cost using current llm_model_pricing table.

    Returns:
        Aggregated totals (tokens_in/out/cache, cost_eur)

    Raises:
        HTTPException 404: If user has no active conversation
    """
    service = ConversationService()
    conversation = await service.get_active_conversation(current_user.id, db)

    if not conversation:
        raise_no_active_conversation(APIMessages.no_active_conversation())

    # Get totals from service
    totals = await service.get_conversation_totals(current_user.id, db)

    logger.debug(
        "conversation_totals_retrieved",
        user_id=str(current_user.id),
        conversation_id=str(totals[FIELD_CONVERSATION_ID]),
        total_cost_eur=totals[FIELD_TOTAL_COST_EUR],
    )

    return ConversationTotalsResponse(
        conversation_id=totals[FIELD_CONVERSATION_ID],
        total_tokens_in=totals[FIELD_TOTAL_TOKENS_IN],
        total_tokens_out=totals[FIELD_TOTAL_TOKENS_OUT],
        total_tokens_cache=totals[FIELD_TOTAL_TOKENS_CACHE],
        total_cost_eur=totals[FIELD_TOTAL_COST_EUR],
        total_google_api_requests=totals[FIELD_TOTAL_GOOGLE_API_REQUESTS],
    )
