"""What the person does with the message that waits for its turn (ADR-384, ADR-385).

Whether the account is busy is read under the owner lock admission and every
close take, in the transaction that keeps the words: a message is never kept
behind a release that has already settled what waited.
"""

from __future__ import annotations

from typing import NoReturn
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import CHAT_MESSAGE_MAX_LENGTH, CONVERSATION_OWNER_LOCK_SCOPE
from src.core.conversation_execution import ExecutionPhase, RunEnd
from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationRef
from src.core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    UnprocessableEntityError,
)
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.api.hitl_pending import pending_run_id
from src.domains.agents.api.run_controls import read_target
from src.domains.agents.api.waiting_departure import Candidate, Departure, depart
from src.domains.agents.api.waiting_schemas import (
    WaitingMessageEdit,
    WaitingMessageJoin,
    WaitingMessageRequest,
    WaitingMessageResponse,
    WaitingQueueResponse,
    WaitingSendResponse,
)
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.domains.conversations.waiting_repository import (
    WaitingMessageDeparting,
    WaitingMessageRepository,
    WaitingMessageTooLong,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database import get_db_context
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.observability.metrics_agents import chat_waiting_messages_total
from src.infrastructure.streaming.run_stream_broker import request_cancel

logger = structlog.get_logger(__name__)


async def read_waiting(
    owner_id: UUID, selection: ConversationSelection
) -> WaitingMessageResponse | None:
    """The selected discussion's waiting message, whatever its status.

    Args:
        owner_id: The authenticated account.
        selection: The discussion displayed.

    Returns:
        The message, or None.
    """
    target = await read_target(owner_id, selection)
    if target is None:
        return None
    async with get_db_context() as db:
        row = await WaitingMessageRepository(db).for_discussion(owner_id, target.id)
        if row is None:
            return None
        note_stream = await ConversationExecutionRepository(db).note_stream(owner_id, target)
        return WaitingMessageResponse.of(row, note_stream=note_stream)


async def keep_waiting(
    owner_id: UUID, selection: ConversationSelection, request: WaitingMessageRequest
) -> WaitingQueueResponse:
    """Keep the words with the discussion; when the account is free, they may leave now.

    Args:
        owner_id: The authenticated account.
        selection: The discussion the words were written in.
        request: The words, and the run they were written behind.

    Returns:
        The waiting message, or the run sending it when it left at once.
    """
    async with get_db_context() as db:
        target = await ConversationCatalogueService(db).resolve_target(
            owner_id, selection, create_primary=True
        )
    assert target is not None
    rendering = request.rendering.model_dump(exclude_none=True) if request.rendering else None
    async with get_db_context() as db:
        await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, owner_id)
        executions = ConversationExecutionRepository(db)
        busy = await executions.active_for_owner(owner_id) is not None
        status = WaitingStatus.WAITING
        if not busy and request.behind_stream_id is not None:
            # Written behind a run that has since ended: its end decides (ADR-384).
            if await executions.ended_as(owner_id, request.behind_stream_id) != RunEnd.NORMAL:
                status = WaitingStatus.HELD
        row, appended = await _keep(db, target, request.message, rendering, status)
        note_stream = await executions.note_stream(owner_id, target)
        candidate = _candidate(row)
        view = WaitingMessageResponse.of(row, note_stream=note_stream)
    chat_waiting_messages_total.labels(event="added" if appended else "kept").inc()
    logger.info(
        "waiting_message_kept",
        user_id=str(owner_id),
        conversation_id=str(target.id),
        appended=appended,
        busy=busy,
        status=status.value,
        length=len(view.content),
    )
    if busy or status is WaitingStatus.HELD:
        return WaitingQueueResponse(waiting=view, departed=False)
    result = await depart(owner_id, candidate)
    if result.outcome is Departure.SENT:
        return WaitingQueueResponse(waiting=None, departed=True, stream_id=result.stream_id)
    return WaitingQueueResponse(waiting=await read_waiting(owner_id, selection), departed=False)


async def edit_waiting(
    owner_id: UUID, selection: ConversationSelection, edit: WaitingMessageEdit
) -> WaitingMessageResponse:
    """Replace the words the person last saw.

    Args:
        owner_id: The authenticated account.
        selection: The discussion.
        edit: The new words and the version they replace.

    Returns:
        The edited message.
    """
    target = await _require_target(owner_id, selection)
    async with get_db_context() as db:
        repository = WaitingMessageRepository(db)
        try:
            row = await repository.replace_text(
                owner_id, target.id, edit.message, version=edit.version
            )
        except WaitingMessageTooLong:
            _too_long()
        if row is None:
            if await repository.for_discussion(owner_id, target.id) is None:
                _not_found()
            _conflict("waiting_message_changed", APIMessages.waiting_message_changed())
        note_stream = await ConversationExecutionRepository(db).note_stream(owner_id, target)
        view = WaitingMessageResponse.of(row, note_stream=note_stream)
    chat_waiting_messages_total.labels(event="edited").inc()
    return view


async def join_waiting(
    owner_id: UUID, selection: ConversationSelection, join: WaitingMessageJoin
) -> WaitingMessageResponse:
    """Add the waiting message to the answer being written in its discussion (ADR-385).

    Decided under the owner lock admission and every close take: a message never
    joins a run whose close already settled what waited, and a note that joined is
    either read by the loop's next call or given back at the release.

    Args:
        owner_id: The authenticated account.
        selection: The discussion.
        join: The version the person saw.

    Returns:
        The message, now joining.
    """
    target = await _require_target(owner_id, selection)
    if await pending_run_id(str(target.runtime_id)) is not None:
        _conflict("waiting_question_pending", APIMessages.waiting_question_pending())
    async with get_db_context() as db:
        await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, owner_id)
        repository = WaitingMessageRepository(db)
        current = await repository.for_discussion(owner_id, target.id)
        if current is None:
            _not_found()
        stream_id = await ConversationExecutionRepository(db).note_stream(owner_id, target)
        if stream_id is None:
            _conflict("waiting_note_closed", APIMessages.waiting_note_closed())
        row = await repository.join(owner_id, target.id, version=join.version, stream_id=stream_id)
        if row is None:
            _refuse_by_status(current)
        view = WaitingMessageResponse.of(row)
    chat_waiting_messages_total.labels(event="joined").inc()
    logger.info(
        "waiting_message_joined",
        user_id=str(owner_id),
        conversation_id=str(target.id),
        stream_id=stream_id,
        length=len(view.content),
    )
    return view


async def withdraw_waiting(owner_id: UUID, selection: ConversationSelection) -> None:
    """Remove the waiting message, unless it is already being sent.

    Args:
        owner_id: The authenticated account.
        selection: The discussion.
    """
    target = await _require_target(owner_id, selection)
    async with get_db_context() as db:
        repository = WaitingMessageRepository(db)
        if not await repository.withdraw(owner_id, target.id):
            if await repository.for_discussion(owner_id, target.id) is None:
                _not_found()
            _conflict("waiting_message_departing", APIMessages.waiting_message_departing())
    chat_waiting_messages_total.labels(event="withdrawn").inc()


async def send_waiting_now(owner_id: UUID, selection: ConversationSelection) -> WaitingSendResponse:
    """« Send now »: stop this discussion's running answer, then send (ADR-384).

    The message is marked to leave first at the next release, whatever its end;
    on a free account it leaves at once. A run in another discussion is never
    stopped from here: the marked message leaves first when it ends.

    Marked, and the account read, under the owner lock every close takes: beside
    a close that has not committed, « the next release » would be the very one
    settling what waited, and the words would stay behind it.

    Args:
        owner_id: The authenticated account.
        selection: The discussion.

    Returns:
        Whether it left at once, and whether the running answer was asked to stop.
    """
    target = await _require_target(owner_id, selection)
    if await pending_run_id(str(target.runtime_id)) is not None:
        _conflict("waiting_question_pending", APIMessages.waiting_question_pending())
    async with get_db_context() as db:
        await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, owner_id)
        repository = WaitingMessageRepository(db)
        row = await repository.request_send(owner_id, target.id)
        if row is None:
            current = await repository.for_discussion(owner_id, target.id)
            if current is None:
                _not_found()
            _refuse_by_status(current)
        candidate = _candidate(row)
        active = await ConversationExecutionRepository(db).snapshot_for_owner(owner_id)
    chat_waiting_messages_total.labels(event="sent_now").inc()
    if active is None:
        result = await depart(owner_id, candidate)
        sent = result.outcome is Departure.SENT
        return WaitingSendResponse(departed=sent, stopping=False, stream_id=result.stream_id)
    stopping = (
        active.busy.target == target
        and active.busy.phase == ExecutionPhase.RUNNING
        and active.busy.cancellable
    )
    if stopping:
        await request_cancel(await get_redis_cache(), active.stream_id)
    return WaitingSendResponse(departed=False, stopping=stopping)


async def _keep(
    db: AsyncSession,
    target: ConversationRef,
    text: str,
    rendering: dict[str, object] | None,
    status: WaitingStatus,
) -> tuple[WaitingMessage, bool]:
    """Keep the words, translating the repository's refusals into the HTTP contract."""
    try:
        return await WaitingMessageRepository(db).keep(
            target, text, rendering=rendering, status=status
        )
    except WaitingMessageTooLong:
        _too_long()
    except WaitingMessageDeparting:
        _conflict("waiting_message_departing", APIMessages.waiting_message_departing())


async def _require_target(owner_id: UUID, selection: ConversationSelection) -> ConversationRef:
    """A control request validates ownership and revision without creating Main."""
    target = await read_target(owner_id, selection)
    if target is None:
        _not_found()
    return target


def _candidate(row: WaitingMessage) -> Candidate:
    """Detach the version read, for a departure that runs after this session."""
    return Candidate(
        id=row.id,
        version=row.version,
        conversation_id=row.conversation_id,
        conversation_revision=row.conversation_revision,
        content=row.content,
        rendering=row.rendering,
    )


def _refuse_by_status(current: WaitingMessage) -> NoReturn:
    """Say why a message that exists was left as it was: it is leaving, or it changed.

    « Changed » covers another edit that won and a message that joined the answer
    being written meanwhile (ADR-385): reading it again shows which.
    """
    if current.status == WaitingStatus.DEPARTING:
        _conflict("waiting_message_departing", APIMessages.waiting_message_departing())
    _conflict("waiting_message_changed", APIMessages.waiting_message_changed())


def _too_long() -> NoReturn:
    raise UnprocessableEntityError(APIMessages.waiting_message_too_long(CHAT_MESSAGE_MAX_LENGTH))


def _not_found() -> NoReturn:
    raise ResourceNotFoundError(resource_type="waiting_message")


def _conflict(error: str, message: str) -> NoReturn:
    raise ResourceConflictError(
        resource_type="waiting_message", detail={"error": error, "message": message}
    )
