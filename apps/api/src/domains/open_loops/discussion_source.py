"""Current commitment states, without reusing notification nudge candidates."""

from uuid import UUID

from src.core.exceptions import ResourceNotFoundError
from src.core.read_budget import mark_read_opened
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.open_loops.management_read import OpenLoopPage, read_open_loop_page
from src.domains.open_loops.schemas import OpenLoopResponse
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


def loop_evidence(row: OpenLoopResponse, request: SourceReadRequest) -> DiscussionEvidence:
    """Project an extracted commitment into derived evidence.

    Args:
        row: The commitment.
        request: The read.

    Returns:
        The evidence; a deadline is advisory, and closing it proves no completion.
    """
    due = row.due_hint.isoformat() if row.due_hint else "unknown"
    lines = evidence_lines()
    text = (
        row.subject
        + "\n"
        + lines["commitment_frame"].format(
            direction=row.direction,
            status=row.status,
            closed_reason=row.closed_reason or "unknown",
            counterparty=row.counterparty or "unknown",
            due=due,
        )
    )
    return DiscussionEvidence(
        reference=f"open_loops:{row.id}",
        source=SourceKey.OPEN_LOOPS,
        object_id=str(row.id),
        version=semantic_version((text,)),
        observed_at=request.now,
        recorded_at=row.created_at,
        assertion="inferred",
        derived=True,
        category=row.direction,
        excerpt=text[: request.item_max_chars],
        excerpt_truncated=len(text) > request.item_max_chars,
        usage_nuance=lines["commitment_nuance"],
    )


def _detail_id(reference: str | None) -> UUID | None:
    if reference is None:
        return None
    source, value = reference.split(":", 1)
    if source != SourceKey.OPEN_LOOPS.value:
        raise ValueError("commitment reference source mismatch")
    return UUID(value)


def _page_result(page: OpenLoopPage, request: SourceReadRequest) -> SourceSnapshot:
    if request.request.operation == "detail" and not page.rows:
        raise ResourceNotFoundError("commitment discussion evidence", request.request.reference)
    items = tuple(loop_evidence(row, request) for row in page.rows[: request.item_limit])
    more = len(page.rows) > request.item_limit
    return source_snapshot(
        request,
        items=items,
        total=page.total,
        status="truncated" if more else ("ok" if items else "empty"),
        complete=not (more or request.cursor or request.request.query or request.request.reference),
        coverage_kind="active_facts",
        cursor=items[-1].object_id if more else None,
    )


class OpenLoopDiscussionSource:
    """The commitments LIA extracted from the person's conversations."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of commitments, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when commitments are not consented.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.OPEN_LOOPS:
            raise ValueError("commitment source mismatch")
        if SourceKey.OPEN_LOOPS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        temporal = request.request.operation in {"history", "future"}
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.OPEN_LOOPS)
            await require_active_owner_read(db, request.owner_id)
            after_id = UUID(request.cursor) if request.cursor else None
            loop_id = _detail_id(request.request.reference)
            mark_read_opened(request.owner_id)
            page = await read_open_loop_page(
                db,
                request.owner_id,
                status=None,
                limit=request.item_limit,
                after_id=after_id,
                loop_id=loop_id,
                query=request.request.query,
                start=request.window_start if temporal else None,
                end=request.window_end if temporal else None,
                future=request.request.operation == "future",
            )
        return _page_result(page, request)
