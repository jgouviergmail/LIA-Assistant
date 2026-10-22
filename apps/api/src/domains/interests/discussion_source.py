"""Saved active interests; notification delivery switches do not erase the record."""

from uuid import UUID

from src.core.exceptions import ResourceNotFoundError
from src.core.read_budget import mark_read_opened
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.interests.management_queries import read_interest_management_page
from src.domains.interests.models import InterestStatus, UserInterest
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


def interest_evidence(row: UserInterest, request: SourceReadRequest) -> DiscussionEvidence:
    """Project a learned interest into derived evidence, with its signal counts.

    Args:
        row: The interest.
        request: The read.

    Returns:
        The evidence; a learned interest is no proof of a recent activity.
    """
    lines = evidence_lines()
    text = lines["interest_frame"].format(
        topic=row.topic, category=row.category, subject=row.subject or ""
    )
    return DiscussionEvidence(
        reference=f"interests:{row.id}",
        source=SourceKey.INTERESTS,
        object_id=str(row.id),
        version=semantic_version(
            (
                text,
                row.status,
                str(row.positive_signals),
                str(row.negative_signals),
                row.last_mentioned_at.isoformat(),
            )
        ),
        observed_at=request.now,
        recorded_at=row.created_at,
        assertion="inferred",
        derived=True,
        category=row.category,
        excerpt=text[: request.item_max_chars],
        excerpt_truncated=len(text) > request.item_max_chars,
        usage_nuance=lines["interest_nuance"].format(
            positive=row.positive_signals,
            negative=row.negative_signals,
            mentioned=row.last_mentioned_at.isoformat(),
        ),
    )


def _detail_id(reference: str | None) -> UUID | None:
    if reference is None:
        return None
    source, value = reference.split(":", 1)
    if source != SourceKey.INTERESTS.value:
        raise ValueError("interest reference source mismatch")
    return UUID(value)


class InterestDiscussionSource:
    """The interests LIA learned the person follows."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of learned interests, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when interests are not consented.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.INTERESTS:
            raise ValueError("interest source mismatch")
        if SourceKey.INTERESTS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        async with get_db_context() as db:
            await require_capability_fresh(db, PlatformCapability.INTERESTS)
            await require_active_owner_read(db, request.owner_id)
            interest_id = _detail_id(request.request.reference)
            after_id = UUID(request.cursor) if request.cursor else None
            mark_read_opened(request.owner_id)
            page = await read_interest_management_page(
                db,
                request.owner_id,
                limit=request.item_limit,
                status=InterestStatus.ACTIVE.value,
                interest_id=interest_id,
                query=request.request.query,
                after_id=after_id,
            )
            items = tuple(
                interest_evidence(row, request) for row in page.rows[: request.item_limit]
            )
        if request.request.operation == "detail" and not items:
            raise ResourceNotFoundError("interest discussion evidence", request.request.reference)
        more = len(page.rows) > request.item_limit
        return source_snapshot(
            request,
            items=items,
            total=page.matching_count,
            status="truncated" if more else ("ok" if items else "empty"),
            complete=not (
                more or request.cursor or request.request.query or request.request.reference
            ),
            coverage_kind="active_facts",
            cursor=items[-1].object_id if more else None,
        )
