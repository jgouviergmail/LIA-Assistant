"""
Agents domain router.
FastAPI endpoints for chat with SSE streaming.
"""

import asyncio
import threading
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from src.core.application_device_identity import APPLICATION_DEVICE_HEADER
from src.core.config import settings
from src.core.conversation_selection import ConversationSelection
from src.core.exceptions import raise_user_id_mismatch
from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_STATUS,
)
from src.core.i18n import resolve_language
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_active_session_for_stream,
)
from src.core.sse_response import EventStreamResponse
from src.domains.agents.api.background_runner import (
    link_inline_request_lifetime,
    spawn_chat_run_producer,
)
from src.domains.agents.api.chat_response import (
    browser_chat_stream,
    inline_sse,
    partial_finalizer,
    stale_decision_stream,
)
from src.domains.agents.api.hitl_pending import (
    check_pending_hitl_uncached,
)
from src.domains.agents.api.request_admission import prepare_chat
from src.domains.agents.api.run_controls import (
    active_status,
    cancel_selected,
    read_target,
    require_subscribable,
)
from src.domains.agents.api.run_output import InlineRunOutput
from src.domains.agents.api.run_schemas import ActiveRunResponse, CancelRunResponse
from src.domains.agents.api.schemas import ChatRequest, PendingHitlResponse
from src.domains.agents.api.service import AgentService
from src.domains.agents.api.stream_relay import stream_run_as_sse
from src.domains.agents.services.hitl.action_requests import with_available_actions
from src.domains.conversations.dependencies import selected_conversation
from src.domains.usage_limits.enforcement import raise_for_blocked_verdict
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_recording_session
from src.infrastructure.async_utils import finish_owned_task
from src.infrastructure.streaming.run_admission import release_unstarted_execution

router = APIRouter(prefix="/agents", tags=["agents"])

# Global service instance (singleton) - Thread-safe lazy initialization
_agent_service: AgentService | None = None
_agent_service_lock = threading.Lock()


def get_agent_service() -> AgentService:
    """
    Get or create agent service singleton (thread-safe lazy initialization).

    Uses double-checked locking pattern to avoid race conditions during initialization
    while minimizing lock contention for subsequent calls.
    """
    global _agent_service

    # First check (unlocked) - fast path for already initialized
    if _agent_service is not None:
        return _agent_service

    # Second check (locked) - ensure only one thread initializes
    with _agent_service_lock:
        if _agent_service is None:
            _agent_service = AgentService()

    return _agent_service


@router.post("/chat/stream", response_class=EventStreamResponse)
async def stream_chat(
    http_request: Request,
    request: ChatRequest,
    current_user: User = Depends(get_current_active_session_for_stream),
) -> StreamingResponse:
    """Resolve and admit before headers; the producer owns every later execution step."""
    if current_user.id != request.user_id:
        raise_user_id_mismatch()
    verdict = await UsageLimitService.check_user_allowed(current_user.id)
    if not verdict.allowed:
        raise_for_blocked_verdict(verdict, layer="router")
    bff_session_id = http_request.cookies.get(settings.session_cookie_name)
    application_origin = bind_browser_recording_session(
        current_user.id,
        bff_session_id,
        device_id=http_request.headers.get(APPLICATION_DEVICE_HEADER),
        recording_snapshot=request.recording_device,
    )
    prepared = await prepare_chat(current_user.id, request, live_session_id=request.live_session_id)
    admission = prepared.admission
    transferred = False
    try:
        if request.hitl_decision is not None and prepared.original_run_id is None:
            return sse_response(
                stale_decision_stream(admission, resolve_language(current_user.language))
            )
        chat_stream = browser_chat_stream(
            get_agent_service(),
            request,
            current_user,
            prepared,
            client_user_agent=http_request.headers.get("user-agent"),
            application_origin=application_origin,
        )
        output = None if admission.relayed else InlineRunOutput()
        producer = spawn_chat_run_producer(
            chat_stream=chat_stream,
            admission=admission,
            session_id=request.session_id,
            finalize_partial=partial_finalizer(admission),
            output=output,
        )
        # No await separates spawning from ownership transfer. A producer
        # cancelled before its first instruction still closes its own claim.
        transferred = True
        if output is not None:
            link_inline_request_lifetime(producer, output)
            return sse_response(inline_sse(output, producer, bff_session_id))
        return sse_response(
            stream_run_as_sse(
                admission.stream_id,
                target=admission.target,
                run_id=admission.run_id,
                user_language=resolve_language(current_user.language),
                session_id=bff_session_id,
            )
        )
    finally:
        if not transferred:
            await finish_owned_task(asyncio.create_task(release_unstarted_execution(admission)))


def sse_response(events: AsyncGenerator[str]) -> StreamingResponse:
    """Keep the same non-buffered transport headers on every browser entry point."""
    return EventStreamResponse(
        events,
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/runs/active", response_model=ActiveRunResponse)
async def get_active_run_status(
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> ActiveRunResponse:
    """Report account-wide occupancy while validating the requested discussion."""
    return await active_status(current_user.id, selection)


@router.get("/hitl/pending", response_model=PendingHitlResponse | None)
async def get_pending_hitl_interrupt(
    response: Response,
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> PendingHitlResponse | None:
    """Rehydrate only the selected runtime's question, with a strict read and no writes."""
    response.headers["Cache-Control"] = "no-store"
    target = await read_target(current_user.id, selection)
    if target is None:
        return None
    pending = await check_pending_hitl_uncached(str(target.runtime_id), raise_on_error=True)
    if pending is None or not pending.get(FIELD_ACTION_REQUESTS):
        return None
    return PendingHitlResponse(
        message_id=pending.get("message_id"),
        action_requests=with_available_actions(pending.get(FIELD_ACTION_REQUESTS, [])),
        interrupt_ts=pending.get("interrupt_ts"),
        generated_question=pending.get("generated_question"),
    )


@router.post("/runs/active/cancel", response_model=CancelRunResponse)
async def cancel_active_run(
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> CancelRunResponse:
    """Signal only this generation's producer; an old tab cannot stop another discussion."""
    return await cancel_selected(current_user.id, selection)


@router.get("/runs/{stream_id}/stream", response_class=EventStreamResponse)
async def reattach_run_stream(
    stream_id: str,
    http_request: Request,
    current_user: User = Depends(get_current_active_session_for_stream),
    selection: ConversationSelection = Depends(selected_conversation),
) -> StreamingResponse:
    """Authorize a live relay through SQL; missing Redis mirrors never confer access."""
    active = await require_subscribable(current_user.id, selection, stream_id)
    return sse_response(
        stream_run_as_sse(
            stream_id,
            target=active.busy.target,
            run_id=active.busy.run_id,
            user_language=resolve_language(current_user.language),
            session_id=http_request.cookies.get(settings.session_cookie_name),
        )
    )


@router.get("/health")
async def agents_health() -> dict[str, str | bool]:
    """
    Health check for agents service.

    Returns:
        Status and basic info.
    """
    agent_service = get_agent_service()
    return {
        FIELD_STATUS: "healthy",
        "service": "agents",
        "graph_compiled": agent_service.graph is not None,
    }
