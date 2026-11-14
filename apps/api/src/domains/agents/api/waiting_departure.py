"""A waiting message leaves as the person's own turn once the account is free (ADR-384).

Installed into ``infrastructure/streaming/release_listener`` at import (and again,
with proof, by the boot): every committed release of an account's graph slot
hands its owner and its declared end here. The account slot itself is the mutex:
whoever reserves it first runs, so two departures never send two messages at once.

The message is claimed AFTER the slot is reserved, on the version that was read:
an edit made meanwhile wins and the departure starts over. Once claimed, the text
is frozen; the archive of the person's message deletes it in its own transaction.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

import structlog

from src.core.constants import WAITING_DEPARTURE_ROUNDS
from src.core.conversation_execution import RunAdmission, RunBusy, RunEnd
from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationRef
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.api.background_runner import spawn_chat_run_producer
from src.domains.agents.api.chat_response import browser_chat_stream, partial_finalizer
from src.domains.agents.api.hitl_pending import pending_run_id
from src.domains.agents.api.request_admission import PreparedChat
from src.domains.agents.api.schemas import BrowserContext, ChatRequest
from src.domains.agents.api.service import AgentService
from src.domains.agents.utils import generate_run_id
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from src.domains.users.models import User
from src.infrastructure.async_utils import finish_owned_task
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.metrics_agents import chat_waiting_messages_total
from src.infrastructure.streaming.release_listener import install_release_listener
from src.infrastructure.streaming.run_admission import (
    release_unstarted_execution,
    reserve_execution,
)

logger = structlog.get_logger(__name__)


class Departure(Enum):
    """What one attempt to send one waiting message found."""

    SENT = "sent"
    BUSY = "busy"
    SKIPPED = "skipped"
    CLAIM_LOST = "claim_lost"


@dataclass(frozen=True, slots=True)
class DepartureResult:
    """One attempt's outcome, and the run sending the message when it left."""

    outcome: Departure
    stream_id: str | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    """The version of a waiting message a departure read, detached from its session."""

    id: UUID
    version: int
    conversation_id: UUID
    conversation_revision: int
    content: str
    rendering: dict[str, Any] | None


async def depart_after_release(owner_id: UUID, end: RunEnd) -> None:
    """Send the first waiting message that may leave after this release.

    Args:
        owner_id: The released account.
        end: How the releasing run ended; only a normal end lets a message the
            person did not ask to send now leave by itself.
    """
    for _ in range(WAITING_DEPARTURE_ROUNDS):
        for candidate in await _candidates(owner_id, end):
            outcome = (await depart(owner_id, candidate)).outcome
            if outcome in (Departure.SENT, Departure.BUSY):
                return
            if outcome is Departure.CLAIM_LOST:
                break
        else:
            return


async def depart(owner_id: UUID, candidate: Candidate) -> DepartureResult:
    """Reserve the account, claim the message, and start the person's turn.

    Args:
        owner_id: The account.
        candidate: The message, at the version read.

    Returns:
        What this attempt found, and the sending run when it left.
    """
    resolved = await _resolve(owner_id, candidate)
    if resolved is None:
        return DepartureResult(Departure.SKIPPED)
    target, user = resolved
    if await pending_run_id(str(target.runtime_id)) is not None:
        # A question asked there is answered by the person, never by what waited.
        return DepartureResult(Departure.SKIPPED)
    stream_id = generate_run_id()
    reserved = await reserve_execution(
        target, run_id=stream_id, stream_id=stream_id, relayed=True, cancellable=True
    )
    if isinstance(reserved, RunBusy):
        return DepartureResult(Departure.BUSY)
    transferred = False
    try:
        if await pending_run_id(str(target.runtime_id)) is not None:
            return DepartureResult(Departure.SKIPPED)
        async with get_db_context() as db:
            claimed = await WaitingMessageRepository(db).claim(
                candidate.id, candidate.version, stream_id=reserved.stream_id
            )
        if not claimed:
            return DepartureResult(Departure.CLAIM_LOST)
        _start_turn(reserved, user, candidate)
        transferred = True
    finally:
        if not transferred:
            # No turn started: the slot is released as unstarted, which gives a
            # claimed message back to the waiting state (ADR-384). Not announced:
            # this departure goes on with its own queue.
            await finish_owned_task(
                asyncio.create_task(release_unstarted_execution(reserved, announce=False))
            )
    chat_waiting_messages_total.labels(event="departed").inc()
    logger.info(
        "waiting_message_departed",
        user_id=str(owner_id),
        conversation_id=str(candidate.conversation_id),
        stream_id=reserved.stream_id,
        length=len(candidate.content),
    )
    return DepartureResult(Departure.SENT, reserved.stream_id)


async def _candidates(owner_id: UUID, end: RunEnd) -> list[Candidate]:
    """Read what may leave, detached, in a session that ends before any wait."""
    async with get_db_context() as db:
        rows = await WaitingMessageRepository(db).departure_candidates(owner_id, end)
        return [
            Candidate(
                id=row.id,
                version=row.version,
                conversation_id=row.conversation_id,
                conversation_revision=row.conversation_revision,
                content=row.content,
                rendering=row.rendering,
            )
            for row in rows
        ]


async def _resolve(owner_id: UUID, candidate: Candidate) -> tuple[ConversationRef, User] | None:
    """The generation the message was written for and the account sending it, or None.

    Read before anything is reserved: an inactive account sends nothing. A reset
    or a deletion removes the discussion's waiting message in its own transaction;
    a message whose generation is nevertheless gone can be sent nowhere, so it
    leaves the queue rather than blocking every later departure.
    """
    selection = ConversationSelection(
        conversation_id=candidate.conversation_id,
        conversation_revision=candidate.conversation_revision,
    )
    async with get_db_context() as db:
        user = await db.get(User, owner_id)
        if user is None or not user.is_active:
            return None
        try:
            target = await ConversationCatalogueService(db).resolve_target(owner_id, selection)
        except (ResourceConflictError, ResourceNotFoundError) as gone:
            await WaitingMessageRepository(db).withdraw(owner_id, candidate.conversation_id)
            logger.warning(
                "waiting_message_target_gone",
                user_id=str(owner_id),
                conversation_id=str(candidate.conversation_id),
                error_type=type(gone).__name__,
            )
            return None
    return (target, user) if target is not None else None


def _start_turn(admission: RunAdmission, user: User, candidate: Candidate) -> None:
    """Hand the claimed text to a supervised producer, as a browser turn would.

    The browser's live authority is never persisted, so the turn runs without it,
    like every turn the server starts for the person; its stream is relayed for the
    open tab to join.
    """
    request = ChatRequest(
        message=candidate.content,
        user_id=user.id,
        session_id=f"waiting_message_{candidate.id}",
        context=BrowserContext.model_validate(candidate.rendering) if candidate.rendering else None,
    )
    chat_stream = browser_chat_stream(
        AgentService(),
        request,
        user,
        PreparedChat(admission, None),
        client_user_agent=None,
        application_origin=None,
    )
    spawn_chat_run_producer(
        chat_stream=chat_stream,
        admission=admission,
        session_id=request.session_id,
        finalize_partial=partial_finalizer(admission),
    )


install_release_listener(depart_after_release)
