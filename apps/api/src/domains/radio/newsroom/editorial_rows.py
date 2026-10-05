"""Fill editorial DB bounds after filtering, including rows filed before the policy.

Each ordered batch has a finite size and at most twenty batches are inspected. The
reader makes no provider requests: it only replaces discarded stored promotions
with the next eligible stories. Concurrent inserts cannot yield duplicates.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

EDITORIAL_READ_PAGES_MAX: Final[int] = 20


async def editorial_rows(
    db: AsyncSession,
    query: Select[Any],
    *,
    limit: int,
    eligible: Callable[[Any], bool],
    identity: Callable[[Any], object],
) -> list[Any]:
    """Return at most ``limit`` eligible rows under a deterministic SQL ordering."""
    if limit <= 0:
        return []
    kept: list[Any] = []
    seen: set[object] = set()
    page_size = max(50, min(limit, 500))
    # One statement holds one PostgreSQL snapshot; separate OFFSET queries
    # could skip eligible rows deleted between READ COMMITTED statements.
    rows = await db.stream(
        query.limit(page_size * EDITORIAL_READ_PAGES_MAX).execution_options(yield_per=page_size)
    )
    try:
        async for batch in rows.partitions(page_size):
            for row in batch:
                key = identity(row)
                if key not in seen and eligible(row):
                    kept.append(row)
                    seen.add(key)
                    if len(kept) == limit:
                        return kept
    finally:
        await rows.close()
    return kept


__all__ = ["EDITORIAL_READ_PAGES_MAX", "editorial_rows"]
