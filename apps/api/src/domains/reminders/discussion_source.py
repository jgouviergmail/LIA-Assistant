"""Remaining reminder intentions; no firing history exists in this source."""

from uuid import UUID

from src.core.constants import RECURRENCE_REMINDER_LIMITS
from src.core.exceptions import ResourceNotFoundError
from src.core.read_budget import mark_read_opened
from src.domains.reminders.context_read import (
    ReminderContextItem,
    ReminderContextPage,
    read_context_page,
)
from src.domains.shared.discussion_lines import evidence_lines
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
    source_snapshot,
)
from src.domains.users.active_reader import require_active_owner_read
from src.infrastructure.database.session import get_db_context


def reminder_evidence(row: ReminderContextItem, request: SourceReadRequest) -> DiscussionEvidence:
    """Project a pending reminder into planned evidence, its recurrence validated.

    Args:
        row: The reminder.
        request: The read.

    Returns:
        The evidence; an intention, never proof its action happened.
    """
    row.recurrence.validate_against(RECURRENCE_REMINDER_LIMITS)
    lines = evidence_lines()
    frame = (
        lines["reminder_intention"].format(content=row.content)
        + "\n"
        + lines["reminder_firing"].format(
            trigger_at=row.trigger_at.isoformat(), timezone=row.user_timezone
        )
    )
    return DiscussionEvidence(
        reference=f"reminders:{row.id}",
        source=SourceKey.REMINDERS,
        object_id=str(row.id),
        version=semantic_version((frame, row.recurrence.model_dump_json())),
        observed_at=request.now,
        recorded_at=row.created_at,
        occurred_at=row.trigger_at,
        assertion="planned",
        recurrence_spec=row.recurrence,
        series_id=str(row.id) if row.recurrence.freq != "once" else None,
        original_start=row.trigger_at,
        excerpt=frame[: request.item_max_chars],
        excerpt_truncated=len(frame) > request.item_max_chars,
        usage_nuance=lines["reminder_nuance"],
    )


def _detail_id(reference: str | None) -> UUID | None:
    if reference is None:
        return None
    source, value = reference.split(":", 1)
    if source != SourceKey.REMINDERS.value:
        raise ValueError("reminder reference source mismatch")
    return UUID(value)


def _page_result(page: ReminderContextPage, request: SourceReadRequest) -> SourceSnapshot:
    if request.request.operation == "detail" and not page.items:
        raise ResourceNotFoundError("reminder discussion evidence", request.request.reference)
    items = tuple(reminder_evidence(row, request) for row in page.items[: request.item_limit])
    more = len(page.items) > request.item_limit
    return source_snapshot(
        request,
        items=items,
        total=page.total,
        status="truncated" if more else ("ok" if items else "empty"),
        complete=not (more or request.cursor or request.request.query or request.request.reference),
        cursor=items[-1].object_id if more else None,
    )


class ReminderDiscussionSource:
    """The person's pending reminders; a fired one leaves no history to read."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of pending reminders firing in the window, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when reminders are not consented, or a history is asked (fired
            reminders are deleted).

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.REMINDERS:
            raise ValueError("reminder source mismatch")
        if SourceKey.REMINDERS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        if request.request.operation == "history":
            return closed_source(request, disabled=False, reason="expired")
        reminder_id = _detail_id(request.request.reference)
        after_id = UUID(request.cursor) if request.cursor else None
        async with get_db_context() as db:
            await require_active_owner_read(db, request.owner_id)
            mark_read_opened(request.owner_id)
            page = await read_context_page(
                db,
                request.owner_id,
                start=request.window_start,
                end=request.window_end,
                limit=request.item_limit,
                after_id=after_id,
                reminder_id=reminder_id,
                query=request.request.query,
            )
        return _page_result(page, request)
