"""Assistant-owned implementation injected into the channel boundary at startup."""

from collections.abc import AsyncGenerator
from contextlib import aclosing

from src.core.config import settings
from src.core.i18n import resolve_language
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
        async with aclosing(
            AgentService().stream_chat_response(
                user_message=request.user_message,
                user_id=request.user_id,
                session_id=request.session_id,
                user_timezone=request.user_timezone,
                user_language=request.user_language,
                user_display_name=request.user_display_name,
                original_run_id=request.original_run_id,
                user_memory_enabled=request.user_memory_enabled,
                user_journals_enabled=request.user_journals_enabled,
                user_psyche_enabled=request.user_psyche_enabled,
                hitl_decision=(
                    dict(request.hitl_decision) if request.hitl_decision is not None else None
                ),
            )
        ) as stream:
            async for chunk in stream:
                yield chunk
    finally:
        plain_surface_ctx.reset(token)


async def _pending(conversation_id: str) -> dict[str, object] | None:
    from src.domains.agents.utils.hitl_store import HITLStore
    from src.infrastructure.cache.redis import get_redis_cache

    store = HITLStore(await get_redis_cache(), ttl_seconds=settings.hitl_pending_data_ttl_seconds)
    return await store.get_pending(conversation_id)


def _confirmation_text(language: str) -> str:
    from src.domains.agents.api.error_messages import SSEErrorMessages

    return SSEErrorMessages.confirmation_required(language=resolve_language(language))


def build_channel_gateway() -> ChannelAssistantGateway:
    return ChannelAssistantGateway(
        stream=_stream, pending=_pending, confirmation_text=_confirmation_text
    )
