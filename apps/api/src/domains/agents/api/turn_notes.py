"""The answer being written takes the person's notes (ADR-385).

A ReAct loop a person waits for opens its notes at its first model call, reads what
joined at each later one, and closes them at its exit. Each step is ONE short
transaction, held by no model call:

- **open**: the running invocation says it takes notes
  (``conversation_executions.accepts_notes``), which the join route reads under
  the account's lock;
- **read**: the notes addressed to this invocation's stream are deleted and
  archived as the person's messages in the same transaction, so a note is in the
  discussion or still joining, never both and never neither;
- **close**: the loop calls its model no more; a note that joins afterwards is
  refused, and one that joined unread goes back at the release.

The invocation is the CURRENT one (``current_run_authority``), never a discussion
an argument names. Opening and closing tell the open tabs only when a message waits
in the discussion: its bubble offers, or stops offering, to join.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.core.conversation_publication import PinnedRunPublication
from src.core.run_authority import current_run_authority
from src.domains.agents.api.archive_metadata import build_turn_note_metadata
from src.domains.agents.services.streaming.latency_sli import a_person_is_waiting
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.service import ConversationService
from src.domains.conversations.sync_signal import CONVERSATION_UPDATED, arm_conversation_signal
from src.domains.conversations.waiting_models import WaitingMessage
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.metrics_agents import chat_waiting_messages_total

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TakenNote:
    """A note the loop read, as it entered the discussion."""

    #: The archived row of the person's message.
    message_id: UUID
    #: The person's words, as they last wrote them.
    text: str
    #: When they last wrote them (the waiting message's last change).
    written_at: datetime


def _admission() -> RunAdmission | None:
    """The invocation whose loop takes notes, or None when none may."""
    authority = current_run_authority()
    if authority is None or not a_person_is_waiting():
        return None
    return authority.admission


async def read_turn_notes() -> list[TakenNote]:
    """Open the notes, then archive and hand over what joined, in one transaction.

    Called at the start of each model call of the loop. A failure that is not a
    lost authority reads nothing this call: the transaction rolls back, so what
    joined is still joining and the next call (or the release) settles it.

    Returns:
        The notes read, oldest first; empty when nobody waits, nothing joined, or
        the read failed.

    Raises:
        ExecutionRevoked: The invocation no longer runs under its identity.
    """
    admission = _admission()
    if admission is None:
        return []
    try:
        async with get_db_context() as db:
            if await ConversationExecutionRepository(db).open_notes(admission):
                await _tell_tabs_if_something_waits(db, admission)
            rows = await WaitingMessageRepository(db).take_joining(
                admission.target.owner_id, admission.stream_id
            )
            notes = [await _archive(db, admission, row) for row in rows]
    except ExecutionRevoked:
        raise
    except Exception as error:
        logger.warning(
            "turn_notes_unread",
            user_id=str(admission.target.owner_id),
            stream_id=admission.stream_id,
            error_type=type(error).__name__,
        )
        return []
    if notes:
        chat_waiting_messages_total.labels(event="note_read").inc(len(notes))
        logger.info(
            "turn_notes_read",
            user_id=str(admission.target.owner_id),
            conversation_id=str(admission.target.id),
            stream_id=admission.stream_id,
            count=len(notes),
            lengths=[len(note.text) for note in notes],
        )
    return notes


async def close_turn_notes() -> None:
    """Stop taking notes: the loop has reached one of its exits.

    A failure is logged and leaves the flag to the close, which withdraws it with
    every transition away from running; a note that joins meanwhile goes back at
    the release (ADR-385).
    """
    admission = _admission()
    if admission is None:
        return
    try:
        async with get_db_context() as db:
            if await ConversationExecutionRepository(db).close_notes(admission):
                await _tell_tabs_if_something_waits(db, admission)
    except Exception as error:
        logger.warning(
            "turn_notes_close_failed",
            user_id=str(admission.target.owner_id),
            stream_id=admission.stream_id,
            error_type=type(error).__name__,
        )


async def _archive(db: AsyncSession, admission: RunAdmission, row: WaitingMessage) -> TakenNote:
    """Archive one note as the person's message of this invocation."""
    message = await ConversationService().archive_message(
        PinnedRunPublication(admission),
        "user",
        row.content,
        build_turn_note_metadata(run_id=admission.run_id),
        db,
    )
    return TakenNote(message_id=message.id, text=row.content, written_at=row.updated_at)


async def _tell_tabs_if_something_waits(db: AsyncSession, admission: RunAdmission) -> None:
    """Tell the open tabs, once this transaction commits, when a message waits there."""
    waiting = await WaitingMessageRepository(db).for_discussion(
        admission.target.owner_id, admission.target.id
    )
    if waiting is None:
        return
    arm_conversation_signal(
        db,
        user_id=admission.target.owner_id,
        conversation_id=admission.target.id,
        kind=CONVERSATION_UPDATED,
    )


__all__ = ["TakenNote", "close_turn_notes", "read_turn_notes"]
