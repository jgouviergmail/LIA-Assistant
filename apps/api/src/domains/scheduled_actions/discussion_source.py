"""Owner-fenced routine intentions, without running a routine or reading its private execution state."""

from uuid import UUID

from pydantic import AwareDatetime
from sqlalchemy import Select, select

from src.core.exceptions import ResourceNotFoundError
from src.core.recurrence import RecurrenceSpec
from src.domains.scheduled_actions.models import ScheduledAction, ScheduledActionStatus
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
from src.infrastructure.database.session import get_db_context


class RoutineContextRow(DiscussionValue):
    """One routine as a discussion reads it: its schedule, state and instruction."""

    id: UUID
    recorded_at: AwareDatetime
    title: str
    status: ScheduledActionStatus
    is_enabled: bool
    trigger_kind: str
    next_trigger_at: AwareDatetime | None
    recurrence: RecurrenceSpec | None
    user_timezone: str
    action_prompt: str


def _query(request: SourceReadRequest) -> Select[tuple[object, ...]]:
    row = ScheduledAction
    statement = select(
        row.id,
        row.created_at.label("recorded_at"),
        row.title,
        row.status,
        row.is_enabled,
        row.trigger_kind,
        row.next_trigger_at,
        row.recurrence,
        row.user_timezone,
        row.action_prompt,
    ).where(row.user_id == request.owner_id)
    if request.request.reference is not None:
        prefix, identifier = request.request.reference.split(":", 1)
        if prefix != SourceKey.SCHEDULED_ACTIONS.value:
            raise ValueError("routine reference source mismatch")
        statement = statement.where(row.id == UUID(identifier))
    if request.request.query is not None:
        statement = statement.where(
            row.title.icontains(request.request.query, autoescape=True)
            | row.action_prompt.icontains(request.request.query, autoescape=True)
        )
    if request.request.operation == "history":
        statement = statement.where(
            row.created_at >= request.window_start, row.created_at < request.window_end
        )
    elif request.request.operation == "future":
        statement = statement.where(
            row.is_enabled.is_(True),
            row.next_trigger_at >= request.window_start,
            row.next_trigger_at < request.window_end,
        )
    return statement


def _evidence(row: RoutineContextRow, request: SourceReadRequest) -> DiscussionEvidence:
    frame = row.model_dump_json()
    return DiscussionEvidence(
        reference=f"scheduled_actions:{row.id}",
        source=SourceKey.SCHEDULED_ACTIONS,
        object_id=str(row.id),
        version=semantic_version((frame,)),
        observed_at=request.now,
        recorded_at=row.recorded_at,
        assertion="planned",
        category="assistant_routine",
        recurrence_spec=row.recurrence,
        excerpt=frame[: request.item_max_chars],
        excerpt_truncated=len(frame) > request.item_max_chars,
    )


class ScheduledActionDiscussionSource:
    """The person's routines and their next runs."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of routines, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when routines are not consented.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.SCHEDULED_ACTIONS:
            raise ValueError("routine source mismatch")
        if SourceKey.SCHEDULED_ACTIONS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        async with get_db_context() as db:
            await require_active_owner_read(db, request.owner_id)
            page = await native_discussion_page(
                db,
                request.owner_id,
                _query(request),
                limit=request.item_limit,
                after_id=UUID(request.cursor) if request.cursor else None,
            )
        rows = tuple(RoutineContextRow.model_validate(value) for value in page.rows)
        if request.request.operation == "detail" and not rows:
            raise ResourceNotFoundError("routine", request.request.reference)
        items = tuple(_evidence(row, request) for row in rows[: request.item_limit])
        return native_page_snapshot(request, page, items)
