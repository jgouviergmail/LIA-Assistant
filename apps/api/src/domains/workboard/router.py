"""Workboard API (ADR-276).

Every read carries the EXACT total behind its page, and the board carries one
exact count per column from the same filter (ADR-185) — a header disagreeing
with the column under it is worse than no header at all.

Ownership is decided in the service and answered as a neutral 404, so a
stranger cannot learn that a ticket id exists. The router owns the HTTP shape,
the dependencies and the transaction boundary; it decides nothing else.

``/needs-me`` sits OUTSIDE the ``/tickets`` namespace rather than beside the
parameterised read: a literal path declared after a parameterised sibling is
swallowed by it, and disjoint paths cannot be swallowed at all — a stronger
guarantee than a declaration order somebody could reshuffle.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.core.time_utils import now_utc
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.schemas import (
    BoardPage,
    BoardSummary,
    CommentCreate,
    CommentRow,
    DeleteResult,
    EventRow,
    MoveRequest,
    NeedsMePage,
    TicketCreate,
    TicketDetail,
    TicketRow,
    TicketUpdate,
)
from src.domains.workboard.service import WorkboardService

router = APIRouter(
    prefix="/workboard",
    tags=["Workboard"],
    # The deployment ceiling already decides whether this router is
    # mounted at all; this is the operator's switch inside it (B7).
    dependencies=capability_dependencies(PlatformCapability.WORKBOARD),
)


@router.get(
    "/tickets",
    response_model=BoardPage,
    summary="One page of the board, with exact totals",
    description=(
        "The caller's board — the tickets they own plus the ones they hold — "
        "with the EXACT total the filter matches and one exact count per "
        "column, both computed over the page's own filter."
    ),
)
async def list_board(
    status: list[str] | None = Query(default=None, description="Columns to keep."),
    assignee: Literal["me", "lia", "peer", "all"] = Query(
        default="all", description="Who holds it."
    ),
    priority: list[str] | None = Query(default=None, description="Priorities to keep."),
    overdue: bool = Query(default=False, description="Only what is past due and still open."),
    due_before: datetime | None = Query(default=None, description="Only what is due by then."),
    q: str | None = Query(default=None, max_length=200, description="Fragment of the title."),
    closed_days: int | None = Query(
        default=None,
        ge=0,
        le=3650,
        description="Show closed tickets closed within N days; omitted uses the instance default.",
    ),
    sort: Literal["position", "priority", "due", "updated", "created"] = Query(default="position"),
    limit: int = Query(default=200, ge=1, le=500, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> BoardPage:
    """One page of the caller's board.

    Args:
        status: Columns to keep; omitted means every column.
        assignee: ``me``, ``lia``, ``peer`` or ``all``.
        priority: Priorities to keep; omitted means all four.
        overdue: Only tickets past their due date and still open.
        due_before: Only tickets due at or before this instant.
        q: Case-insensitive fragment of the title.
        closed_days: How far back closed tickets stay visible.
        sort: Ordering of the page.
        limit: Page size.
        offset: Page offset.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The page, the exact total, and one exact count per column.
    """
    days = settings.workboard_closed_hide_days_default if closed_days is None else closed_days
    filters = BoardFilters(
        statuses=tuple(status) if status else None,
        assignee=assignee,
        priorities=tuple(priority) if priority else None,
        overdue=overdue,
        due_before=due_before,
        query=q,
        include_closed_before=now_utc() - timedelta(days=days),
        sort=sort,
    )
    rows, total, counts = await WorkboardService(db).board(
        user, filters, limit=limit, offset=offset
    )
    return BoardPage(
        tickets=[TicketRow.model_validate(row) for row in rows],
        total=total,
        counts_by_status=counts,
    )


@router.get(
    "/needs-me",
    response_model=NeedsMePage,
    summary="Tickets waiting on the caller",
    description=(
        "What is stopped on this account — a run waiting for a decision — plus "
        "what is late on their board."
    ),
)
async def needs_me(
    limit: int = Query(default=20, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> NeedsMePage:
    """Tickets waiting on the caller, or late on their board.

    Args:
        limit: Page size.
        offset: Page offset.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The page and the exact total behind it.
    """
    rows, total = await WorkboardService(db).needs_me(user, limit=limit, offset=offset)
    return NeedsMePage(tickets=[TicketRow.model_validate(row) for row in rows], total=total)


@router.get(
    "/summary",
    response_model=BoardSummary,
    summary="The board at a glance",
    description=(
        "Exact counts over the caller's whole board — per column, late, held by "
        "LIA, waiting on them — what they own against the cap, and what their "
        "tickets have cost."
    ),
)
async def board_summary(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> BoardSummary:
    """The board at a glance (lot 18).

    Args:
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        Every figure an aggregate over its whole set.
    """
    return await WorkboardService(db).summary(user)


@router.get(
    "/tickets/{ticket_id}",
    response_model=TicketDetail,
    summary="One ticket, with its children, thread and history",
)
async def get_ticket(
    ticket_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketDetail:
    """One ticket in full.

    Args:
        ticket_id: The ticket.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The ticket, its children, its comments and its history.
    """
    bundle = await WorkboardService(db).get(user, ticket_id)
    return TicketDetail(
        ticket=TicketRow.model_validate(bundle.ticket),
        children=[TicketRow.model_validate(child) for child in bundle.children],
        comments=[CommentRow.model_validate(comment) for comment in bundle.comments],
        events=[EventRow.model_validate(event) for event in bundle.events],
    )


@router.post(
    "/tickets",
    response_model=TicketRow,
    status_code=status.HTTP_201_CREATED,
    summary="Create a ticket",
)
async def create_ticket(
    payload: TicketCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketRow:
    """Create a ticket on the caller's board.

    Args:
        payload: The request.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The created ticket.
    """
    ticket = await WorkboardService(db).create(user, payload)
    await db.commit()
    return TicketRow.model_validate(ticket)


@router.patch(
    "/tickets/{ticket_id}",
    response_model=TicketRow,
    summary="Change a ticket, under the caller's rights",
)
async def update_ticket(
    ticket_id: UUID,
    payload: TicketUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketRow:
    """Apply a partial update.

    Args:
        ticket_id: The ticket.
        payload: What to change; absent means unchanged.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The updated ticket.
    """
    ticket = await WorkboardService(db).update(user, ticket_id, payload)
    await db.commit()
    return TicketRow.model_validate(ticket)


@router.post(
    "/tickets/{ticket_id}/move",
    response_model=TicketRow,
    summary="Move a ticket to a column and a place in it",
)
async def move_ticket(
    ticket_id: UUID,
    payload: MoveRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketRow:
    """The drag-and-drop write.

    Args:
        ticket_id: The ticket.
        payload: The destination column and index.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The moved ticket.
    """
    ticket = await WorkboardService(db).move(user, ticket_id, payload.status, payload.position)
    await db.commit()
    return TicketRow.model_validate(ticket)


@router.post(
    "/tickets/{ticket_id}/run-now",
    response_model=TicketRow,
    summary="Offer a LIA-assigned ticket to the next sweep",
)
async def run_ticket_now(
    ticket_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> TicketRow:
    """Arm a ticket for the sweep now, ignoring its start date.

    Args:
        ticket_id: The ticket.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The armed ticket.
    """
    ticket = await WorkboardService(db).run_now(user, ticket_id)
    await db.commit()
    return TicketRow.model_validate(ticket)


@router.post(
    "/tickets/{ticket_id}/comments",
    response_model=CommentRow,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a ticket",
)
async def add_comment(
    ticket_id: UUID,
    payload: CommentCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> CommentRow:
    """Append a comment.

    Args:
        ticket_id: The ticket.
        payload: The comment.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The created comment.
    """
    comment = await WorkboardService(db).comment(user, ticket_id, payload)
    await db.commit()
    return CommentRow.model_validate(comment)


@router.delete(
    "/tickets/{ticket_id}",
    response_model=DeleteResult,
    summary="Delete a ticket and its children (the owner only)",
)
async def delete_ticket(
    ticket_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DeleteResult:
    """Delete a ticket.

    Args:
        ticket_id: The ticket.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        How many rows went, so the caller can say what it took.
    """
    removed = await WorkboardService(db).delete(user, ticket_id)
    await db.commit()
    return DeleteResult(removed=removed)
