"""One browser preference mapping and one supervised producer for both SSE transports."""

import asyncio
from collections.abc import AsyncGenerator

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE, DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.conversation_execution import RunAdmission
from src.core.conversation_publication import PinnedRunPublication
from src.core.i18n import resolve_language
from src.core.run_authority import run_authority_scope
from src.core.user_display import resolve_user_display_name
from src.domains.agents.api.archive_metadata import build_interrupted_stream_metadata
from src.domains.agents.api.background_runner import PartialFinalizer, stop_inline_producer
from src.domains.agents.api.hitl_pending import hitl_stale_chunks
from src.domains.agents.api.request_admission import PreparedChat
from src.domains.agents.api.run_output import InlineRunOutput
from src.domains.agents.api.schemas import ChatRequest, ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.agents.api.session_watch import SESSION_REVOKED_COMMENT, session_still_valid
from src.domains.agents.api.stream_identity import with_invocation_identity
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.publication_repository import ConversationPublicationRepository
from src.domains.conversations.service import ConversationService
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.streaming.run_stream_broker import has_listeners


def browser_chat_stream(
    service: AgentService,
    request: ChatRequest,
    user: User,
    prepared: PreparedChat,
    *,
    client_user_agent: str | None,
    application_origin: ApplicationOrigin | None,
) -> AsyncGenerator[ChatStreamChunk]:
    """Apply the account's same settings to Main, annexes, HITL resumptions and the
    message that waited for its turn (ADR-384), which has no request of its own."""
    admission = prepared.admission

    async def listening() -> bool:
        return await has_listeners(await get_redis_cache(), admission.stream_id)

    return service.stream_chat_response(
        user_message=request.message,
        user_id=user.id,
        session_id=request.session_id,
        target=admission.target,
        admission=admission,
        run_id=admission.run_id,
        original_run_id=prepared.original_run_id,
        has_listeners=listening if admission.relayed else None,
        user_timezone=user.timezone or DEFAULT_USER_DISPLAY_TIMEZONE,
        user_language=resolve_language(user.language),
        user_display_name=resolve_user_display_name(user.full_name, user.email),
        user_memory_enabled=user.memory_enabled,
        user_journals_enabled=user.journals_enabled,
        user_psyche_enabled=user.psyche_enabled,
        user_display_mode=user.response_display_mode,
        user_execution_mode=user.execution_mode,
        browser_context=request.context,
        attachment_ids=request.attachment_ids,
        stt_provider=request.stt_provider,
        stt_audio_duration_seconds=request.stt_audio_duration_seconds,
        stt_cost_usd=request.stt_cost_usd,
        stt_cost_eur=request.stt_cost_eur,
        hitl_decision=request.hitl_decision.model_dump() if request.hitl_decision else None,
        directive=request.directive.model_dump() if request.directive else None,
        client_user_agent=client_user_agent,
        live_session_id=request.live_session_id,
        spoken_text=request.spoken_text,
        application_origin=application_origin,
    )


def partial_finalizer(admission: RunAdmission) -> PartialFinalizer:
    """Archive already-produced content under the pinned admission in the SAME transaction."""

    async def finalize(content: str, reason: str) -> None:
        async with get_db_context() as db:
            # Serialise repeated finalizers without holding anything over I/O.
            await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, admission.target.owner_id)
            await ConversationExecutionRepository(db).require_current(admission)
            if await ConversationPublicationRepository(db).has_invocation_answer(admission):
                return
            # The producer owns this last write after local revocation; SQL
            # still pins its original generation and must authorize the write.
            with run_authority_scope(None):
                await ConversationService().archive_message(
                    PinnedRunPublication(admission),
                    "assistant",
                    content,
                    build_interrupted_stream_metadata(run_id=admission.run_id, reason=reason),
                    db,
                )

    return finalize


async def stale_decision_stream(admission: RunAdmission, language: str) -> AsyncGenerator[str]:
    """An expired button remains a typed SSE refusal, without a graph or model call."""
    yield "retry: 5000\n\n"
    for chunk in hitl_stale_chunks(language):
        yield f"data: {with_invocation_identity(chunk, admission).model_dump_json()}\n\n"


async def inline_sse(
    output: InlineRunOutput,
    producer: asyncio.Task[None],
    session_id: str | None,
) -> AsyncGenerator[str]:
    """The subscriber owns its bounded transport; teardown joins the supervised owner."""
    try:
        yield "retry: 5000\n\n"
        while True:
            try:
                item = await output.read(settings.sse_heartbeat_interval)
            except TimeoutError:
                if not await session_still_valid(session_id):
                    yield SESSION_REVOKED_COMMENT
                    return
                yield ": heartbeat\n\n"
            else:
                if item is None:
                    return
                yield f"data: {item.model_dump_json()}\n\n"
                await asyncio.sleep(settings.agent_stream_sleep_interval)
    finally:
        await stop_inline_producer(producer, output)
