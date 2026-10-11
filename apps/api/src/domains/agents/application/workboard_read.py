"""Live account-owned UI observations, with source filters and strict current authority."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import raise_not_found_or_unauthorized
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.workboard_read_schemas import (
    DETAIL_SECTIONS,
    WorkboardUIProjection,
    WorkboardUIQuery,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.models import WorkboardComment, WorkboardTicketEvent
from src.domains.workboard.schemas import CommentRow, EventRow, TicketRow
from src.domains.workboard.service import WorkboardService


async def _read_access(db: AsyncSession, actor_id: UUID) -> User:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.WORKBOARD)
    return await load_actor(db, actor_id)


async def _detail(
    db: AsyncSession,
    service: WorkboardService,
    actor: User,
    query: WorkboardUIQuery,
    result: WorkboardUIProjection,
) -> None:
    assert query.ticket_id is not None
    ticket = await service.repo.get_visible(query.ticket_id, actor.id)
    if ticket is None:
        raise_not_found_or_unauthorized("ticket", query.ticket_id)
    if query.section == "ticket":
        result.ticket = TicketRow.model_validate(ticket)
        return
    options = {"limit": query.limit, "offset": query.offset}
    if query.section == "children":
        result.tickets = [
            TicketRow.model_validate(row)
            for row in await service.repo.list_children(query.ticket_id, **options)
        ]
        result.total = await service.repo.count_children(query.ticket_id)
    elif query.section == "comments":
        result.comments = [
            CommentRow.model_validate(row)
            for row in await service.repo.list_comments(query.ticket_id, **options)
        ]
        result.total = int(
            await db.scalar(
                select(func.count(WorkboardComment.id)).where(
                    WorkboardComment.ticket_id == query.ticket_id
                )
            )
            or 0
        )
    else:
        result.events = [
            EventRow.model_validate(row)
            for row in await service.repo.list_events(query.ticket_id, **options)
        ]
        result.total = int(
            await db.scalar(
                select(func.count(WorkboardTicketEvent.id)).where(
                    WorkboardTicketEvent.ticket_id == query.ticket_id
                )
            )
            or 0
        )


async def _board(
    service: WorkboardService, actor: User, query: WorkboardUIQuery, result: WorkboardUIProjection
) -> None:
    days = (
        settings.workboard_closed_hide_days_default
        if query.closed_days is None
        else query.closed_days
    )
    filters = BoardFilters(
        statuses=tuple(value.value for value in query.statuses) if query.statuses else None,
        priorities=tuple(value.value for value in query.priorities) if query.priorities else None,
        assignee=query.assignee,
        overdue=query.overdue,
        due_before=query.due_before,
        query=query.query,
        include_closed_before=datetime.now(UTC) - timedelta(days=days),
        sort=query.sort,
    )
    rows, result.total, result.counts_by_status = await service.board(
        actor, filters, limit=query.limit, offset=query.offset
    )
    result.tickets = [TicketRow.model_validate(row) for row in rows]


async def _verify_observed_visibility(
    service: WorkboardService,
    actor_id: UUID,
    selected: WorkboardUIQuery,
    result: WorkboardUIProjection,
) -> None:
    if selected.section in {"board", "needs_me"} and result.tickets:
        identities = [ticket.id for ticket in result.tickets]
        visible = await service.repo.count_visible(identities, actor_id)
        if visible != len(identities):
            raise_not_found_or_unauthorized("workboard", actor_id)
    if selected.section in DETAIL_SECTIONS:
        assert selected.ticket_id is not None
        if await service.repo.get_visible(selected.ticket_id, actor_id) is None:
            raise_not_found_or_unauthorized("ticket", selected.ticket_id)


async def read_workboard_ui(
    db: AsyncSession, actor_id: UUID, query: WorkboardUIQuery
) -> WorkboardUIProjection:
    selected = WorkboardUIQuery.model_validate(query.model_dump(exclude_unset=True))
    actor = await _read_access(db, actor_id)
    service = WorkboardService(db)
    result = WorkboardUIProjection(section=selected.section, observed_at=datetime.now(UTC))
    if selected.section == "summary":
        result.summary = await service.summary(actor)
    elif selected.section == "board":
        await _board(service, actor, selected, result)
    elif selected.section == "needs_me":
        rows, result.total = await service.needs_me(
            actor, limit=selected.limit, offset=selected.offset
        )
        result.tickets = [TicketRow.model_validate(row) for row in rows]
    else:
        await _detail(db, service, actor, selected, result)
    await _read_access(db, actor_id)
    await _verify_observed_visibility(service, actor_id, selected, result)
    next_offset = selected.offset + selected.limit
    result.next_offset = (
        next_offset if result.total is not None and next_offset < result.total else None
    )
    if len(result.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Workboard UI page too large; request a smaller page or narrower filters")
    return WorkboardUIProjection.model_validate(result.model_dump(mode="json"))
