"""Assistant-owned implementation injected into the channel boundary at startup."""

from collections.abc import AsyncGenerator
from contextlib import aclosing
from uuid import UUID

from src.core.config import settings
from src.core.conversation_execution import RunEnd
from src.core.conversation_selection import ConversationSelection
from src.core.i18n import resolve_language
from src.core.run_authority import current_run_authority
from src.domains.agents.api.hitl_pending import hitl_stale_chunks
from src.domains.agents.api.internal_admission import internal_turn
from src.infrastructure.channels.assistant_gateway import (
    ChannelAgentRequest,
    ChannelAssistantGateway,
    ChannelStreamChunk,
)


async def _stream(request: ChannelAgentRequest) -> AsyncGenerator[ChannelStreamChunk]:
    from src.domains.agents.api.run_origin import plain_surface_ctx
    from src.domains.agents.api.service import AgentService

    token = plain_surface_ctx.set(True)
    try:
        async with internal_turn(
            request.user_id,
            selection=ConversationSelection(),
            language=request.user_language,
            run_id=None,
            answer_pending=True,
        ) as prepared:
            if (
                request.original_run_id is not None
                and request.original_run_id != prepared.original_run_id
            ):
                _declare_end(RunEnd.UNSTARTED)
                for chunk in hitl_stale_chunks(request.user_language):
                    yield chunk
                return
            failed = False
            async with aclosing(
                AgentService().stream_chat_response(
                    user_message=request.user_message,
                    user_id=request.user_id,
                    session_id=request.session_id,
                    user_timezone=request.user_timezone,
                    user_language=request.user_language,
                    user_display_name=request.user_display_name,
                    original_run_id=prepared.original_run_id,
                    run_id=prepared.admission.run_id,
                    target=prepared.admission.target,
                    admission=prepared.admission,
                    user_memory_enabled=request.user_memory_enabled,
                    user_journals_enabled=request.user_journals_enabled,
                    user_psyche_enabled=request.user_psyche_enabled,
                    hitl_decision=(
                        dict(request.hitl_decision) if request.hitl_decision is not None else None
                    ),
                )
            ) as stream:
                async for chunk in stream:
                    failed |= chunk.type == "error"
                    yield chunk
            _declare_end(RunEnd.INTERRUPTED if failed else RunEnd.NORMAL)
    finally:
        plain_surface_ctx.reset(token)


def _declare_end(end: RunEnd) -> None:
    """Tell the admission this turn owns how it ended, before its close reads it (ADR-384)."""
    authority = current_run_authority()
    if authority is not None:
        authority.end = end


async def _pending(owner_id: UUID, conversation_id: str) -> dict[str, object] | None:
    """Read only the owner's current Main, after releasing the SQL session."""
    from src.domains.agents.utils.hitl_store import HITLStore
    from src.domains.conversations.repository import ConversationRepository
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        conversation = await ConversationRepository(db).get_active_for_user(owner_id)
        if conversation is None or str(conversation.id) != conversation_id:
            return None
        runtime_id = str(conversation.runtime_id)
    store = HITLStore(await get_redis_cache(), ttl_seconds=settings.hitl_pending_data_ttl_seconds)
    return await store.get_pending(runtime_id)


def _confirmation_text(language: str) -> str:
    from src.domains.agents.api.error_messages import SSEErrorMessages

    return SSEErrorMessages.confirmation_required(language=resolve_language(language))


def build_channel_gateway() -> ChannelAssistantGateway:
    return ChannelAssistantGateway(
        stream=_stream, pending=_pending, confirmation_text=_confirmation_text
    )
