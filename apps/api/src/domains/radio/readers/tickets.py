"""The workboard's tickets, as drafts for the listener's journal.

Two reads. The tickets that WAIT on the listener (the day): the workboard's own
« needs me » predicate decides which (ADR-276): a run of LIA stopped on a question
or an action to confirm for THIS person, or a ticket on their board past its due
date — so the radio and the board can never disagree about what waits on the person
(ADR-185). A ticket is named by its title and the one reason it waits; its lateness
is counted in the listener's own days. And the tickets CLOSED today (the journal's
« done », ADR-324 decision 41): the closed statuses of the board's own vocabulary,
on the board's own visibility predicate, their closing instant the status change's.

Each read opens its own short session and closes it before returning (ADR-304):
nothing is held while the station talks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, tzinfo
from uuid import UUID

from sqlalchemy import select

from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.personal import MAX_PER_SOURCE, JournalPart, PersonalDraft, PersonalSource
from src.domains.workboard.board_queries import visible_predicate
from src.domains.workboard.constants import CLOSED_STATUSES, TicketPriority, TicketStatus
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository
from src.infrastructure.database.session import get_db_context

#: What a priority adds to a ticket's line (the others add nothing).
_PRIORITY_WORDS = {
    TicketPriority.URGENT.value: "urgent",
    TicketPriority.HIGH.value: "high priority",
}


@dataclass(frozen=True, slots=True)
class TicketLine:
    """What the radio reads of one ticket.

    Attributes:
        id: The ticket.
        title: Its title.
        status: Its column.
        priority: Its priority.
        due_at: Its due instant, if any (aware).
    """

    id: UUID
    title: str
    status: str
    priority: str
    due_at: datetime | None


def _reason(ticket: TicketLine, *, now: datetime, tz: tzinfo) -> tuple[str, str]:
    """Why the ticket waits on the listener: its words, and its part of the ledger key."""
    if ticket.status == TicketStatus.CONFIRMING.value:
        return "LIA is waiting for the listener to confirm an action", "confirm"
    if ticket.status == TicketStatus.WAITING.value:
        return "LIA asked the listener a question and is waiting for the answer", "question"
    if ticket.due_at is None:
        return "is waiting on the listener", "waiting"
    late_days = (now.astimezone(tz).date() - ticket.due_at.astimezone(tz).date()).days
    if late_days <= 0:
        return "was due earlier today", "late"
    if late_days == 1:
        return "was due yesterday", "late"
    return f"was due {late_days} days ago", "late"


def ticket_drafts(
    tickets: Sequence[TicketLine], *, now: datetime, tz: tzinfo
) -> list[PersonalDraft]:
    """The tickets as drafts, in the order the board ranks them.

    Args:
        tickets: What « needs me » returned.
        now: The current instant (aware).
        tz: The listener's timezone (days are counted in it).

    Returns:
        One draft per ticket.
    """
    drafts: list[PersonalDraft] = []
    for ticket in tickets:
        why, part = _reason(ticket, now=now, tz=tz)
        joint = ": " if part in ("confirm", "question") else " "
        text = f'Ticket "{ticket.title}"{joint}{why}'
        if ticket.priority in _PRIORITY_WORDS:
            text += f" ({_PRIORITY_WORDS[ticket.priority]})"
        drafts.append(
            PersonalDraft(FactKind.TICKET, text, f"ticket:{ticket.id}:{part}", Sensitivity.PERSONAL)
        )
    return drafts


async def read_tickets(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The tickets that wait on the listener, read from the workboard.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    async with get_db_context() as db:
        rows, _total = await WorkboardRepository(db).needs_me(
            user_id, now, limit=MAX_PER_SOURCE[PersonalSource.TICKETS]
        )
        lines = [
            TicketLine(
                id=row.id,
                title=row.title,
                status=row.status,
                priority=row.priority,
                due_at=row.due_at,
            )
            for row in rows
        ]
    return ticket_drafts(lines, now=now, tz=tz)


@dataclass(frozen=True, slots=True)
class ClosedTicket:
    """What the radio reads of one ticket closed today.

    Attributes:
        id: The ticket.
        title: Its title.
        closed_at: When its status became a closed one (aware).
    """

    id: UUID
    title: str
    closed_at: datetime


def closed_ticket_drafts(tickets: Sequence[ClosedTicket], *, tz: tzinfo) -> list[PersonalDraft]:
    """The tickets closed today as drafts, in the order given.

    Args:
        tickets: The closed tickets, oldest closing first.
        tz: The listener's timezone.

    Returns:
        One draft per ticket.
    """
    return [
        PersonalDraft(
            FactKind.TICKET,
            f'Ticket "{ticket.title}" was closed today at {ticket.closed_at.astimezone(tz):%H:%M}',
            f"done:ticket:{ticket.id}",
            Sensitivity.PERSONAL,
            JournalPart.DONE,
        )
        for ticket in tickets
    ]


async def read_closed_tickets(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The tickets of the listener's board closed today, oldest closing first.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    since = datetime.combine(now.astimezone(tz).date(), time(), tzinfo=tz)
    stmt = (
        select(WorkboardTicket)
        .where(
            visible_predicate(user_id),
            WorkboardTicket.status.in_(tuple(sorted(CLOSED_STATUSES))),
            WorkboardTicket.status_changed_at >= since,
        )
        .order_by(WorkboardTicket.status_changed_at.asc(), WorkboardTicket.id.asc())
        .limit(MAX_PER_SOURCE[PersonalSource.TICKETS])
    )
    async with get_db_context() as db:
        rows = (await db.execute(stmt)).scalars().all()
        tickets = [
            ClosedTicket(id=row.id, title=row.title, closed_at=row.status_changed_at)
            for row in rows
        ]
    return closed_ticket_drafts(tickets, tz=tz)


__all__ = [
    "ClosedTicket",
    "TicketLine",
    "closed_ticket_drafts",
    "read_closed_tickets",
    "read_tickets",
    "ticket_drafts",
]
