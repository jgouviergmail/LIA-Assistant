"""Assignment notices have an immutable source snapshot and an explicit dispatch boundary."""

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n import normalize_language
from src.domains.shared import proactive_sink
from src.domains.users.models import User
from src.domains.workboard.constants import NOTIFICATION_TASK_TYPE
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.notifications import (
    WorkboardEvent,
    board_url,
    event_run_id,
    notification_body,
    notification_metadata,
    recipients_for,
    ticket_url,
)
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AssignmentNotice:
    recipient_id: UUID
    ticket_id: UUID
    event_id: UUID
    content: str
    metadata: dict[str, str]


async def collect_assignment_notices(
    db: AsyncSession, ticket: WorkboardTicket, actor_id: UUID, event_id: UUID
) -> list[AssignmentNotice]:
    notices: list[AssignmentNotice] = []
    for identity in recipients_for(WorkboardEvent.ASSIGNED, ticket, actor_user_id=actor_id):
        recipient = await db.get(User, identity, populate_existing=True)
        if recipient is None:
            continue
        notices.append(
            AssignmentNotice(
                recipient_id=identity,
                ticket_id=ticket.id,
                event_id=event_id,
                content=notification_body(
                    WorkboardEvent.ASSIGNED, ticket, language=normalize_language(recipient.language)
                ),
                metadata=notification_metadata(
                    WorkboardEvent.ASSIGNED,
                    ticket,
                    board_url=board_url(),
                    ticket_url=ticket_url(ticket),
                ),
            )
        )
    return notices


async def dispatch_assignment_notices(db: AsyncSession, notices: list[AssignmentNotice]) -> bool:
    delivered = True
    for notice in notices:
        recipient = await db.get(User, notice.recipient_id, populate_existing=True)
        if recipient is None or not recipient.is_active or recipient.deleted_at is not None:
            delivered = False
            continue
        ticket = await db.get(WorkboardTicket, notice.ticket_id, populate_existing=True)
        if ticket is None or ticket.assignee_user_id != recipient.id:
            delivered = False
            continue
        reported = await proactive_sink.send_proactive_notification(
            db=db,
            user=recipient,
            content=notice.content,
            task_type=NOTIFICATION_TASK_TYPE,
            target_id=str(notice.ticket_id),
            metadata=notice.metadata,
            run_id=event_run_id(notice.event_id),
            occurrence=WorkboardEvent.ASSIGNED.value,
        )
        delivered = delivered and reported
    return delivered


async def dispatch_committed_assignment_notices(notices: list[AssignmentNotice]) -> bool:
    """Send the notices of a mutation that has COMMITTED, on a short session of their own.

    Never inside the mutation's transaction. The mutation fence holds the
    accounts' ``users`` rows FOR UPDATE (ADR-335), and a notice claims its act in
    ``agent_effects`` on a connection of its own (ADR-263), whose foreign key
    needs a share lock on the recipient's row: sent under the fence, the request
    waited for a claim that waited for the request, and every later write of the
    account queued behind them (production, 2026-10-21).

    Args:
        notices: What the committed mutation collected.

    Returns:
        True when every notice was delivered, or none was due; False otherwise.
        The assignment is committed either way: a notice never undoes it.
    """
    if not notices:
        return True
    try:
        async with get_db_context() as db:
            return await dispatch_assignment_notices(db, notices)
    except Exception as exc:  # noqa: BLE001 — the committed assignment stands without its notice
        logger.warning(
            "workboard_assignment_notices_failed",
            count=len(notices),
            error_type=type(exc).__name__,
        )
        return False
