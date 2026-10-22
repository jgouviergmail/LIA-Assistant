"""One SQL snapshot for a bounded native context page and its exact filtered total."""

from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from pydantic import StrictInt, TypeAdapter
from sqlalchemy import Select, func, literal, select, true, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.read_budget import mark_read_opened
from src.domains.shared.discussion_sources import (
    CoverageKind,
    DiscussionEvidence,
    SourceReadRequest,
    SourceSnapshot,
    source_snapshot,
)

_SqlRow = TypeVar("_SqlRow", bound=tuple[object, ...])
_COUNT = TypeAdapter(StrictInt)


@dataclass(frozen=True)
class NativeDiscussionPage:
    """One page of native rows (up to limit + 1) and the exact total of the selection."""

    rows: tuple[dict[str, object], ...]
    total: int


def native_page_snapshot(
    request: SourceReadRequest,
    page: NativeDiscussionPage,
    items: tuple[DiscussionEvidence, ...],
    *,
    coverage_kind: CoverageKind = "active_facts",
) -> SourceSnapshot:
    """Turn a native page into the read's snapshot.

    It is truncated when the page held one more row than the limit, complete only
    when nothing narrowed the read (no cursor, query or reference), and its cursor
    is the last item's id.

    Args:
        request: The read.
        page: The native page.
        items: The page's rows as evidence, within the limit.
        coverage_kind: What kind of coverage the page gives.

    Returns:
        The snapshot.
    """
    more = len(page.rows) > request.item_limit
    return source_snapshot(
        request,
        status="truncated" if more else "ok" if items else "empty",
        items=items,
        total=page.total,
        coverage_kind=coverage_kind,
        complete=not (more or request.cursor or request.request.query or request.request.reference),
        cursor=items[-1].object_id if more else None,
    )


async def native_discussion_page(
    db: AsyncSession,
    owner: UUID,
    statement: Select[_SqlRow],
    *,
    limit: int,
    after_id: UUID | None,
) -> NativeDiscussionPage:
    """Read one keyset page of an owner's rows and the exact total, in one query.

    Rows come newest first by ``recorded_at`` then id; the statement must expose
    both. The source is marked opened.

    Args:
        db: The session to read with.
        owner: The account.
        statement: The owner's filtered selection.
        limit: The page size (1 to 100); one more row reveals a next page.
        after_id: The last row of the previous page.

    Returns:
        The page and its total.

    Raises:
        ValueError: The limit is outside 1..100.
        ResourceConflictError: The cursor's row no longer exists
            (``STALE_CURSOR``).
    """
    if not 1 <= limit <= 100:
        raise ValueError("native discussion page limit outside 1..100")
    owned = statement.cte("discussion_owned")
    selection = select(owned)
    anchor_time = select(owned.c.recorded_at).where(owned.c.id == after_id).scalar_subquery()
    if after_id is not None:
        selection = selection.where(
            tuple_(owned.c.recorded_at, owned.c.id) < tuple_(anchor_time, literal(after_id))
        )
    page = (
        selection.order_by(owned.c.recorded_at.desc(), owned.c.id.desc())
        .limit(limit + 1)
        .cte("discussion_page")
    )
    anchor = select(literal(1)).subquery()
    total = select(func.count()).select_from(owned).scalar_subquery()
    query = (
        select(*page.c, total.label("_total"), anchor_time.label("_anchor"))
        .select_from(anchor.outerjoin(page, true()))
        .order_by(page.c.recorded_at.desc(), page.c.id.desc())
    )
    mark_read_opened(owner)
    rows = (await db.execute(query)).mappings().all()
    if after_id is not None and rows[0]["_anchor"] is None:
        raise ResourceConflictError("discussion_source", detail={"error_code": "STALE_CURSOR"})
    return NativeDiscussionPage(
        total=_COUNT.validate_python(rows[0]["_total"]),
        rows=tuple(
            {str(key): value for key, value in row.items() if key not in {"_total", "_anchor"}}
            for row in rows
            if row["id"] is not None
        ),
    )
