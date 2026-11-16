"""Words written on a channel while LIA works: the assistant's half (Telegram lot 34, ADR-384).

A channel speaks in the person's Main. What they write there while the account
is busy is kept like the app's words — read under the owner lock admission and
every close take, in the transaction that keeps them — and names the channel it
was written on, so its answer goes back there (``waiting_departure``). A held
message is sent or withdrawn from the channel by the two answers the chat's
bubble offers, and only the message the person was shown is acted on.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE
from src.core.conversation_selection import ConversationSelection
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.api.run_controls import read_target
from src.domains.agents.api.waiting_departure import Candidate, Departure, depart
from src.domains.agents.api.waiting_requests import send_waiting_now, withdraw_waiting
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.waiting_models import WaitingStatus
from src.domains.conversations.waiting_repository import (
    WaitingMessageDeparting,
    WaitingMessageRepository,
    WaitingMessageTooLong,
)
from src.infrastructure.channels.assistant_gateway import (
    ChannelKeep,
    WaitingAction,
    WaitingActionOutcome,
)
from src.infrastructure.database import get_db_context
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.observability.metrics_agents import chat_waiting_messages_total

logger = structlog.get_logger(__name__)

#: The ``detail.error`` a send refused because a question waits there.
_QUESTION_PENDING = "waiting_question_pending"


async def keep_from_channel(owner_id: UUID, text: str, channel_type: str) -> ChannelKeep:
    """Keep words written on a channel for Main; on a free account they leave at once.

    No run is named behind them (a channel does not know which one refused
    them): on a free account they simply leave, as a plain send does (ADR-384).

    Args:
        owner_id: The person.
        text: Their words (a voice note already transcribed).
        channel_type: The channel they wrote on, where the answer goes.

    Returns:
        What became of the words.
    """
    async with get_db_context() as db:
        target = await ConversationCatalogueService(db).resolve_target(
            owner_id, ConversationSelection(), create_primary=True
        )
    assert target is not None
    async with get_db_context() as db:
        await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, owner_id)
        busy = await ConversationExecutionRepository(db).active_for_owner(owner_id) is not None
        try:
            row, appended = await WaitingMessageRepository(db).keep(
                target,
                text,
                rendering=None,
                status=WaitingStatus.WAITING,
                reply_channel=channel_type,
            )
        except WaitingMessageTooLong:
            return ChannelKeep.TOO_LONG
        except WaitingMessageDeparting:
            return ChannelKeep.DEPARTING
        candidate = Candidate.of(row)
    chat_waiting_messages_total.labels(event="added" if appended else "kept").inc()
    logger.info(
        "waiting_message_kept",
        user_id=str(owner_id),
        conversation_id=str(target.id),
        appended=appended,
        busy=busy,
        reply_channel=channel_type,
        length=len(candidate.content),
    )
    if busy:
        return ChannelKeep.KEPT
    sent = (await depart(owner_id, candidate)).outcome is Departure.SENT
    return ChannelKeep.DEPARTED if sent else ChannelKeep.KEPT


async def act_on_waiting(
    owner_id: UUID, waiting_id: UUID, action: WaitingAction
) -> WaitingActionOutcome:
    """Send or withdraw the message a channel showed the person — that one only.

    A button carries the id of the message it was drawn for: when what waits in
    Main is another message (the first left, was withdrawn, a new one began),
    the press acts on nothing. Send is the chat's « Send now » (ADR-384): it
    leaves at once on a free account, first at the release otherwise.

    Args:
        owner_id: The person.
        waiting_id: The message the button was drawn for.
        action: Send it now, or withdraw it.

    Returns:
        What the action found.
    """
    selection = ConversationSelection()
    target = await read_target(owner_id, selection)
    if target is None:
        return WaitingActionOutcome.GONE
    async with get_db_context() as db:
        current = await WaitingMessageRepository(db).for_discussion(owner_id, target.id)
    if current is None or current.id != waiting_id:
        return WaitingActionOutcome.GONE
    try:
        if action is WaitingAction.WITHDRAW:
            await withdraw_waiting(owner_id, selection)
            return WaitingActionOutcome.WITHDRAWN
        sent = await send_waiting_now(owner_id, selection)
    except ResourceNotFoundError:
        return WaitingActionOutcome.GONE
    except ResourceConflictError as refused:
        detail: object = refused.detail
        if isinstance(detail, dict) and detail.get("error") == _QUESTION_PENDING:
            return WaitingActionOutcome.QUESTION
        return WaitingActionOutcome.GONE
    return WaitingActionOutcome.SENT if sent.departed else WaitingActionOutcome.QUEUED
