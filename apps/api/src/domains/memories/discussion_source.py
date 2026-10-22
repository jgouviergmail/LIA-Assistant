"""Bounded active facts, through the memory owner's existing SQL page contract."""

from uuid import UUID

from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.core.read_budget import mark_read_opened
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.memories.management_queries import MemoryManagementPage, read_management_page
from src.domains.memories.models import Memory, MemoryCategory
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
    source_snapshot,
)
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


def _reference_id(value: str | None) -> UUID | None:
    if value is None:
        return None
    prefix, identifier = value.split(":", 1)
    if prefix != SourceKey.MEMORIES.value:
        raise ValueError("memory reference source mismatch")
    return UUID(identifier)


def memory_evidence(
    row: Memory, request: SourceReadRequest, *, biometric: bool = False
) -> DiscussionEvidence:
    """Project a memory into reported evidence; a biometric one is a health fact.

    Args:
        row: The memory.
        request: The read.
        biometric: Whether the memory states a health measurement, which then
            needs the health source and topic too.

    Returns:
        The evidence.
    """
    return DiscussionEvidence(
        reference=f"memories:{row.id}",
        source=SourceKey.MEMORIES,
        object_id=str(row.id),
        version=semantic_version(
            (
                row.content,
                row.category,
                row.usage_nuance,
                row.trigger_topic,
                str(row.emotional_weight),
                row.created_at.isoformat(),
                str(biometric),
            )
        ),
        observed_at=request.now,
        recorded_at=row.created_at,
        excerpt=row.content[: request.item_max_chars],
        excerpt_truncated=len(row.content) > request.item_max_chars,
        category=row.category,
        usage_nuance=row.usage_nuance,
        emotional_weight=row.emotional_weight,
        sensitive_topics=("health",) if biometric else (),
        required_sources=(SourceKey.HEALTH,) if biometric else (),
        assertion="reported",
    )


def _page_result(page: MemoryManagementPage, request: SourceReadRequest) -> SourceSnapshot:
    if request.request.operation == "detail" and not page.rows:
        raise ResourceNotFoundError("memory discussion evidence", request.request.reference)
    selected = page.rows[: request.item_limit]
    items = tuple(
        memory_evidence(row, request, biometric=row.id in page.biometric_ids) for row in selected
    )
    more = len(page.rows) > request.item_limit
    return source_snapshot(
        request,
        status="truncated" if more else ("ok" if items else "empty"),
        complete=not (more or request.cursor or request.request.query or request.request.reference),
        total=sum(page.by_category.values()),
        items=items,
        coverage_kind="active_facts",
        cursor=str(selected[-1].id) if more else None,
    )


class MemoryDiscussionSource:
    """The person's long-term memories, when they keep automatic memory on."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of memories, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when memories are not consented or the person switched automatic memory
            off.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.MEMORIES:
            raise ValueError("memory source mismatch")
        if SourceKey.MEMORIES not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.MEMORY)
            access = (
                await db.execute(
                    select(User.memory_enabled, User.health_metrics_agents_enabled).where(
                        User.id == request.owner_id,
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if access is None or not access.memory_enabled:
                return closed_source(request, disabled=True, reason="consent")
            health_allowed = bool(
                settings.health_metrics_enabled
                and access.health_metrics_agents_enabled
                and SourceKey.HEALTH in request.allowed_sources
                and "health" in request.sensitive_topics
            )
            memory_id = _reference_id(request.request.reference)
            after_id = UUID(request.cursor) if request.cursor is not None else None
            mark_read_opened(request.owner_id)
            page = await read_management_page(
                db,
                request.owner_id,
                limit=request.item_limit,
                exclude_categories=(MemoryCategory.PROCEDURAL.value,),
                exclude_biometric=not health_allowed,
                query=request.request.query,
                memory_id=memory_id,
                after_id=after_id,
                recorded_start=(
                    request.window_start if request.request.operation == "history" else None
                ),
                recorded_end=(
                    request.window_end if request.request.operation == "history" else None
                ),
            )
            return _page_result(page, request)
