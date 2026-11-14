"""Historical spending and the checkpoint footprint of one owned discussion."""

import asyncio
from uuid import UUID

import structlog
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.conversation_selection import ConversationSelection
from src.core.exceptions import raise_no_active_conversation
from src.core.field_names import (
    FIELD_TOTAL_COST_EUR,
    FIELD_TOTAL_GOOGLE_API_REQUESTS,
    FIELD_TOTAL_TOKENS_CACHE,
    FIELD_TOTAL_TOKENS_IN,
    FIELD_TOTAL_TOKENS_OUT,
    FIELD_USER_MESSAGE_COUNT,
)
from src.core.i18n_api_messages import APIMessages
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.checkpointer import get_checkpointer
from src.domains.conversations.repository import ConversationRepository
from src.domains.conversations.schemas import ConversationTotalsResponse

logger = structlog.get_logger(__name__)


async def _checkpoint_usage(runtime_id: UUID) -> tuple[int, int] | None:
    """Read the selected runtime's footprint, or explicitly leave it unavailable."""
    from src.domains.agents.services.compaction_service import CompactionService
    from src.domains.agents.services.token_counter_service import get_token_counter

    try:
        checkpointer = await get_checkpointer()
        config = RunnableConfig(configurable={"thread_id": str(runtime_id)})
        snapshot = await checkpointer.aget_tuple(config)
        messages = snapshot.checkpoint.get("channel_values", {}).get("messages") if snapshot else []
        counter = get_token_counter(settings)
        tokens = await asyncio.to_thread(counter.count_messages_tokens, messages or [])
        return tokens, CompactionService(counter).compute_effective_threshold()
    except Exception as exc:
        logger.debug("conversation_context_usage_unavailable", error_type=type(exc).__name__)
        return None


async def read_conversation_usage(
    db: AsyncSession, owner_id: UUID, selection: ConversationSelection
) -> ConversationTotalsResponse:
    """Read billed history for the exact generation, then its isolated checkpoint.

    Args:
        db: Request session, committed before the checkpoint read.
        owner_id: Authenticated account.
        selection: Exact target, or omission for Main.

    Returns:
        The discussion's authoritative cumulative totals and optional context usage.
    """
    target = await ConversationCatalogueService(db).resolve_target(owner_id, selection, lock=True)
    if target is None:
        raise_no_active_conversation(APIMessages.no_active_conversation())
    totals = await ConversationRepository(db).get_token_totals(target)
    await db.commit()
    context = await _checkpoint_usage(target.runtime_id)
    return ConversationTotalsResponse(
        conversation_id=target.id,
        conversation_revision=target.revision,
        user_message_count=int(totals[FIELD_USER_MESSAGE_COUNT]),
        total_tokens_in=int(totals[FIELD_TOTAL_TOKENS_IN]),
        total_tokens_out=int(totals[FIELD_TOTAL_TOKENS_OUT]),
        total_tokens_cache=int(totals[FIELD_TOTAL_TOKENS_CACHE]),
        total_cost_eur=float(totals[FIELD_TOTAL_COST_EUR]),
        total_google_api_requests=int(totals[FIELD_TOTAL_GOOGLE_API_REQUESTS]),
        context_tokens=context[0] if context is not None else None,
        context_threshold=context[1] if context is not None else None,
    )
