"""Source mutation preview rolls back a savepoint; no alternate business rules or notifications."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_not_found_or_unauthorized
from src.domains.users.models import User
from src.domains.workboard.assignment_notifications import AssignmentNotice
from src.domains.workboard.models import WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.schemas import EventRow, MoveRequest, TicketRow, TicketUpdate
from src.domains.workboard.service import WorkboardService


@dataclass(frozen=True)
class TicketMutationPreview:
    ticket: dict[str, JsonValue]
    raw: dict[str, JsonValue]
    columns: list[dict[str, JsonValue]]
    events: list[dict[str, JsonValue]]


async def read_mutation_columns(
    db: AsyncSession, owner_id: UUID, statuses: tuple[str, ...]
) -> list[dict[str, JsonValue]]:
    rows = (
        await db.execute(
            select(WorkboardTicket.id, WorkboardTicket.status, WorkboardTicket.position)
            .where(WorkboardTicket.owner_user_id == owner_id, WorkboardTicket.status.in_(statuses))
            .order_by(WorkboardTicket.id)
        )
    ).all()
    return [{"id": str(row.id), "status": row.status, "position": row.position} for row in rows]


def mutation_event_value(event: WorkboardTicketEvent) -> dict[str, JsonValue]:
    return EventRow.model_validate(event).model_dump(mode="json", exclude={"id", "created_at"})


async def apply_ticket_mutation(
    db: AsyncSession,
    actor: User,
    ticket_id: UUID,
    changes: TicketUpdate,
    *,
    move: MoveRequest | None = None,
    run_now: bool = False,
    notices: list[AssignmentNotice],
    events: list[WorkboardTicketEvent] | None = None,
) -> WorkboardTicket:
    service = WorkboardService(db, assignment_notices=notices, mutation_events=events)
    ticket = await service.update(actor, ticket_id, changes)
    if move is not None:
        ticket = await service.move(actor, ticket_id, move.status, move.position)
    if run_now:
        ticket = await service.run_now(actor, ticket_id)
    await db.flush()
    return ticket


async def preview_ticket_mutation(
    db: AsyncSession,
    actor_id: UUID,
    ticket_id: UUID,
    changes: TicketUpdate,
    *,
    move: MoveRequest | None = None,
    run_now: bool = False,
    statuses: tuple[str, ...] = (),
) -> TicketMutationPreview:
    savepoint = await db.begin_nested()
    try:
        actor = await db.get(User, actor_id, populate_existing=True)
        if actor is None:
            raise_not_found_or_unauthorized("account", actor_id)
        events: list[WorkboardTicketEvent] = []
        ticket = await apply_ticket_mutation(
            db, actor, ticket_id, changes, move=move, run_now=run_now, notices=[], events=events
        )
        raw = await db.scalar(
            select(func.to_jsonb(WorkboardTicket.__table__.table_valued())).where(
                WorkboardTicket.id == ticket_id
            )
        )
        if not isinstance(raw, dict):
            raise ValueError("Source mutation preview did not produce a ticket")
        return TicketMutationPreview(
            ticket=TicketRow.model_validate(ticket).model_dump(mode="json"),
            raw=raw,
            columns=await read_mutation_columns(db, ticket.owner_user_id, statuses),
            events=[mutation_event_value(event) for event in events],
        )
    finally:
        await savepoint.rollback()
