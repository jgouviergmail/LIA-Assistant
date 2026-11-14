"""Routes of the message that waits for its turn (ADR-384, ADR-385).

The selected discussion travels as the same query pair as the run controls; a
read never creates Main, a keep may (it is the person's first words).
"""

from fastapi import APIRouter, Depends, Response, status

from src.core.constants import RATE_LIMIT_WAITING_MESSAGE_PER_MINUTE
from src.core.conversation_selection import ConversationSelection
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.api.waiting_requests import (
    edit_waiting,
    join_waiting,
    keep_waiting,
    read_waiting,
    send_waiting_now,
    withdraw_waiting,
)
from src.domains.agents.api.waiting_schemas import (
    WaitingMessageEdit,
    WaitingMessageJoin,
    WaitingMessageRequest,
    WaitingMessageResponse,
    WaitingQueueResponse,
    WaitingSendResponse,
)
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.conversations.dependencies import selected_conversation
from src.domains.usage_limits.enforcement import raise_for_blocked_verdict
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import User

router = APIRouter(prefix="/agents/chat/waiting", tags=["agents"])

rate_limit_waiting = create_user_rate_limiter(
    action="chat_waiting_message", max_calls=RATE_LIMIT_WAITING_MESSAGE_PER_MINUTE
)


@router.get("", response_model=WaitingMessageResponse | None)
async def get_waiting_message(
    response: Response,
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> WaitingMessageResponse | None:
    """The selected discussion's waiting message, or null."""
    response.headers["Cache-Control"] = "no-store"
    return await read_waiting(current_user.id, selection)


@router.post("", response_model=WaitingQueueResponse, dependencies=[Depends(rate_limit_waiting)])
async def keep_waiting_message(
    request: WaitingMessageRequest,
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> WaitingQueueResponse:
    """Keep words written while LIA works; on a free account they may leave at once."""
    verdict = await UsageLimitService.check_user_allowed(current_user.id)
    if not verdict.allowed:
        raise_for_blocked_verdict(verdict, layer="router")
    return await keep_waiting(current_user.id, selection, request)


@router.put("", response_model=WaitingMessageResponse, dependencies=[Depends(rate_limit_waiting)])
async def edit_waiting_message(
    edit: WaitingMessageEdit,
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> WaitingMessageResponse:
    """Replace the words of the version the person edited."""
    return await edit_waiting(current_user.id, selection, edit)


@router.delete(
    "", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(rate_limit_waiting)]
)
async def withdraw_waiting_message(
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> Response:
    """Withdraw the waiting message before it leaves."""
    await withdraw_waiting(current_user.id, selection)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/join", response_model=WaitingMessageResponse, dependencies=[Depends(rate_limit_waiting)]
)
async def join_waiting_message(
    join: WaitingMessageJoin,
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> WaitingMessageResponse:
    """Add the waiting message to the answer being written in this discussion (ADR-385)."""
    return await join_waiting(current_user.id, selection, join)


@router.post(
    "/send", response_model=WaitingSendResponse, dependencies=[Depends(rate_limit_waiting)]
)
async def send_waiting_message_now(
    current_user: User = Depends(get_current_active_session),
    selection: ConversationSelection = Depends(selected_conversation),
) -> WaitingSendResponse:
    """« Send now »: stop this discussion's running answer, then send."""
    verdict = await UsageLimitService.check_user_allowed(current_user.id)
    if not verdict.allowed:
        raise_for_blocked_verdict(verdict, layer="router")
    return await send_waiting_now(current_user.id, selection)
