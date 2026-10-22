"""Current ready minutes only; no recording, generated fallback, raw audio or GPS."""

from uuid import UUID

from src.core.exceptions import ResourceNotFoundError
from src.core.read_budget import mark_read_opened
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.meetings.context_read import (
    MeetingContextItem,
    MeetingContextPage,
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


def meeting_evidence(row: MeetingContextItem, request: SourceReadRequest) -> DiscussionEvidence:
    """Project a meeting's current minutes into derived, dated evidence.

    Args:
        row: The meeting.
        request: The read.

    Returns:
        The evidence; named action items are plans, not proof of completion.
    """
    frame = row.report.model_dump_json()
    return DiscussionEvidence(
        reference=f"meetings:{row.id}",
        source=SourceKey.MEETINGS,
        object_id=str(row.id),
        version=semantic_version((frame, row.started_at.isoformat())),
        observed_at=request.now,
        recorded_at=row.created_at,
        occurred_at=row.started_at,
        assertion="inferred",
        derived=True,
        category="minutes",
        excerpt=frame[: request.item_max_chars],
        excerpt_truncated=len(frame) > request.item_max_chars,
        usage_nuance=evidence_lines()["meeting_nuance"],
    )


def _detail_id(reference: str | None) -> UUID | None:
    if reference is None:
        return None
    source, value = reference.split(":", 1)
    if source != SourceKey.MEETINGS.value:
        raise ValueError("meeting reference source mismatch")
    return UUID(value)


def _page_result(page: MeetingContextPage, request: SourceReadRequest) -> SourceSnapshot:
    if request.request.operation == "detail" and not page.items:
        raise ResourceNotFoundError("meeting discussion evidence", request.request.reference)
    items = tuple(meeting_evidence(row, request) for row in page.items[: request.item_limit])
    more = len(page.items) > request.item_limit
    return source_snapshot(
        request,
        items=items,
        total=page.total,
        status="truncated" if more else ("ok" if items else "empty"),
        complete=not (more or request.cursor or request.request.query or request.request.reference),
        coverage_kind="dated_synthesis",
        cursor=items[-1].object_id if more else None,
    )


class MeetingDiscussionSource:
    """The minutes of the person's recorded meetings."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of ready minutes in the window, or one meeting by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when meetings are not consented.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.MEETINGS:
            raise ValueError("meeting source mismatch")
        if SourceKey.MEETINGS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        meeting_id = _detail_id(request.request.reference)
        after_id = UUID(request.cursor) if request.cursor else None
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.MEETINGS)
            await require_active_owner_read(db, request.owner_id)
            mark_read_opened(request.owner_id)
            page = await read_context_page(
                db,
                request.owner_id,
                start=request.window_start,
                end=request.window_end,
                limit=request.item_limit,
                after_id=after_id,
                meeting_id=meeting_id,
                query=request.request.query,
            )
        return _page_result(page, request)
