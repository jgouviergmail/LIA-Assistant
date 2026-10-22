"""Active mirror rows only; paused, blocked or disabled habits cannot be consumed."""

from uuid import UUID

from sqlalchemy import select

from src.core.exceptions import ResourceNotFoundError
from src.core.read_budget import mark_read_opened
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.habits.discussion_projection import habit_evidence
from src.domains.habits.management_read import HabitPage, read_habit_page
from src.domains.habits.models import HabitStatus
from src.domains.shared.discussion_sources import (
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    source_snapshot,
)
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


def _detail_id(reference: str | None) -> UUID | None:
    if reference is None:
        return None
    source, value = reference.split(":", 1)
    if source != SourceKey.HABITS.value:
        raise ValueError("habit reference source mismatch")
    return UUID(value)


def _page_result(page: HabitPage, request: SourceReadRequest) -> SourceSnapshot:
    if request.request.operation == "detail" and not page.rows:
        raise ResourceNotFoundError("habit discussion evidence", request.request.reference)
    items = tuple(habit_evidence(row, request) for row in page.rows[: request.item_limit])
    more = len(page.rows) > request.item_limit
    return source_snapshot(
        request,
        items=items,
        total=page.total,
        status="truncated" if more else ("ok" if items else "empty"),
        complete=not (more or request.cursor or request.request.reference),
        coverage_kind="active_facts",
        cursor=items[-1].object_id if more else None,
    )


class HabitDiscussionSource:
    """The person's active learned habits; paused, blocked or disabled ones never enter."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of active habits, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when habits are not consented or the person switched habit learning
            off.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.HABITS:
            raise ValueError("habit source mismatch")
        if SourceKey.HABITS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.HABITS)
            enabled = await db.scalar(
                select(User.habits_enabled)
                .where(
                    User.id == request.owner_id, User.is_active.is_(True), User.deleted_at.is_(None)
                )
                .with_for_update(read=True)
            )
            if not enabled:
                return closed_source(request, disabled=True, reason="consent")
            after_id = UUID(request.cursor) if request.cursor else None
            habit_id = _detail_id(request.request.reference)
            mark_read_opened(request.owner_id)
            page = await read_habit_page(
                db,
                request.owner_id,
                limit=request.item_limit,
                after_id=after_id,
                status=HabitStatus.ACTIVE,
                habit_id=habit_id,
            )
        return _page_result(page, request)
