"""Bounded control pages and bounded effective root lookups, independent of history size."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.proactive_discussions.context_store.models import (
    ContextExclusionRecord,
    ContextItemRecord,
)
from src.domains.proactive_discussions.context_store.schemas import ContextExclusion, ContextItem


async def excluded_roots(db: AsyncSession, owner: UUID, roots: tuple[str, ...]) -> frozenset[str]:
    """Return which of these roots the person excluded.

    Args:
        db: The session to read with.
        owner: The account.
        roots: The roots to check.

    Returns:
        The excluded subset.
    """
    if not roots:
        return frozenset()
    return frozenset(
        (
            await db.scalars(
                select(ContextExclusionRecord.root)
                .where(
                    ContextExclusionRecord.user_id == owner,
                    ContextExclusionRecord.root.in_(roots),
                )
                .distinct()
            )
        ).all()
    )


@dataclass(frozen=True)
class ExclusionPage:
    """One page of the person's non-use choices, its exact total and the next cursor."""

    items: tuple[ContextExclusion, ...]
    total: int
    next_cursor: UUID | None


async def read_exclusion_page(
    db: AsyncSession, owner: UUID, *, limit: int, after_id: UUID | None
) -> ExclusionPage:
    """Return one page of non-use choices, grouped by the item they were made on.

    Args:
        db: The session to read with.
        owner: The account.
        limit: The page size.
        after_id: The cursor: the last item of the previous page.

    Returns:
        The page; its total counts every distinct item carrying a choice.
    """
    owned = ContextExclusionRecord.user_id == owner
    query = (
        select(ContextExclusionRecord.item_id)
        .where(owned)
        .distinct()
        .order_by(ContextExclusionRecord.item_id)
    )
    if after_id is not None:
        query = query.where(ContextExclusionRecord.item_id > after_id)
    origins = list((await db.scalars(query.limit(limit + 1))).all())
    total = await db.scalar(
        select(func.count(func.distinct(ContextExclusionRecord.item_id))).where(owned)
    )
    rows = (
        await db.execute(
            select(ContextExclusionRecord.item_id, ContextExclusionRecord.root)
            .where(
                owned,
                ContextExclusionRecord.item_id.in_(origins[:limit]),
            )
            .order_by(ContextExclusionRecord.item_id, ContextExclusionRecord.root)
        )
    ).all()
    grouped: dict[UUID, list[str]] = {}
    for item_id, root in rows:
        grouped.setdefault(item_id, []).append(root)
    return ExclusionPage(
        items=tuple(
            ContextExclusion(item_id=key, roots=tuple(values)) for key, values in grouped.items()
        ),
        total=total or 0,
        next_cursor=origins[limit - 1] if len(origins) > limit else None,
    )


async def present_items(
    db: AsyncSession, owner: UUID, rows: list[ContextItemRecord]
) -> tuple[ContextItem, ...]:
    """Present stored items with whether a non-use choice excludes them.

    Args:
        db: The session to read with.
        owner: The account.
        rows: The stored items.

    Returns:
        Each item, ``excluded`` when one of its roots is excluded and
        ``explicitly_excluded`` when the choice was made on the item itself.
    """
    roots = tuple({root for row in rows for root in row.root_keys})
    blocked = await excluded_roots(db, owner, roots)
    explicit = set(
        (
            await db.scalars(
                select(ContextExclusionRecord.item_id)
                .where(
                    ContextExclusionRecord.user_id == owner,
                    ContextExclusionRecord.item_id.in_([row.id for row in rows]),
                )
                .distinct()
            )
        ).all()
    )
    return tuple(
        ContextItem.model_validate(row.data).model_copy(
            update={
                "excluded": bool(set(row.root_keys) & blocked),
                "explicitly_excluded": row.id in explicit,
            }
        )
        for row in rows
    )
