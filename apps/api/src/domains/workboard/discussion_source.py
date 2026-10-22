"""The same visible board as the UI, projected as record state, never personal completion."""

from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import Select, select

from src.core.exceptions import ResourceNotFoundError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    DiscussionValue,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
)
from src.domains.shared.discussion_sql import native_discussion_page, native_page_snapshot
from src.domains.users.active_reader import require_active_owner_read
from src.domains.workboard.board_queries import visible_predicate
from src.domains.workboard.constants import AssigneeKind, TicketPriority, TicketStatus
from src.domains.workboard.models import WorkboardTicket
from src.infrastructure.database.session import get_db_context


class TicketContextRow(DiscussionValue):
    """One workboard ticket as a discussion reads it: who holds it, its state and dates."""

    id: UUID
    recorded_at: AwareDatetime
    owner_user_id: UUID
    assignee_kind: AssigneeKind
    assignee_user_id: UUID | None
    title: str
    status: TicketStatus
    priority: TicketPriority
    start_at: AwareDatetime | None
    due_at: AwareDatetime | None
    status_changed_at: AwareDatetime
    description: str | None


def _query(request: SourceReadRequest) -> Select[tuple[object, ...]]:
    row = WorkboardTicket
    statement = select(
        row.id,
        row.created_at.label("recorded_at"),
        row.owner_user_id,
        row.assignee_kind,
        row.assignee_user_id,
        row.title,
        row.status,
        row.priority,
        row.start_at,
        row.due_at,
        row.status_changed_at,
        row.description,
    ).where(visible_predicate(request.owner_id))
    if request.request.reference is not None:
        prefix, identifier = request.request.reference.split(":", 1)
        if prefix != SourceKey.WORKBOARD.value:
            raise ValueError("workboard reference source mismatch")
        statement = statement.where(row.id == UUID(identifier))
    if request.request.query is not None:
        statement = statement.where(
            row.title.icontains(request.request.query, autoescape=True)
            | row.description.icontains(request.request.query, autoescape=True)
        )
    if request.request.operation == "history":
        statement = statement.where(
            row.created_at >= request.window_start, row.created_at < request.window_end
        )
    elif request.request.operation == "future":
        statement = statement.where(
            row.due_at >= request.window_start, row.due_at < request.window_end
        )
    return statement


def _evidence(row: TicketContextRow, request: SourceReadRequest) -> DiscussionEvidence:
    frame = row.model_dump_json()
    return DiscussionEvidence(
        reference=f"workboard:{row.id}",
        source=SourceKey.WORKBOARD,
        object_id=str(row.id),
        version=semantic_version((frame,)),
        observed_at=request.now,
        recorded_at=row.recorded_at,
        assertion="planned",
        category="workboard_record",
        excerpt=frame[: request.item_max_chars],
        excerpt_truncated=len(frame) > request.item_max_chars,
    )


class WorkboardDiscussionSource:
    """The person's workboard tickets."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of tickets, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when the workboard is not consented.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.WORKBOARD:
            raise ValueError("workboard source mismatch")
        if SourceKey.WORKBOARD not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        async with get_db_context() as db:
            await require_active_owner_read(db, request.owner_id)
            await require_capability_fresh(db, PlatformCapability.WORKBOARD)
            page = await native_discussion_page(
                db,
                request.owner_id,
                _query(request),
                limit=request.item_limit,
                after_id=UUID(request.cursor) if request.cursor else None,
            )
        rows = tuple(TicketContextRow.model_validate(value) for value in page.rows)
        if request.request.operation == "detail" and not rows:
            raise ResourceNotFoundError("workboard", request.request.reference)
        items = tuple(_evidence(row, request) for row in rows[: request.item_limit])
        return native_page_snapshot(request, page, items)
