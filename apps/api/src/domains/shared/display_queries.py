"""Exact display pages from one SQL snapshot, without alternate Unicode rules."""

from collections.abc import Callable, Sequence
from heapq import heappush_max, heapreplace_max
from uuid import UUID

from sqlalchemy import Row, Select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DISPLAY_READ_BATCH_ROWS
from src.domains.shared.text_normalization import normalize_search_text

type Ranked[T] = tuple[tuple[str, str], int, T]


def _keep_smallest[T](heap: list[Ranked[T]], entry: Ranked[T], capacity: int) -> None:
    """Retain a bounded prefix in logarithmic time, caching each normalized key."""
    if len(heap) < capacity:
        heappush_max(heap, entry)
    elif entry[:2] < heap[0][:2]:
        heapreplace_max(heap, entry)


def display_name_key(name: str | None, identity: UUID | str) -> tuple[str, str]:
    """Literal display ordering, ending on the row's stable identity."""
    return normalize_search_text(name or ""), str(identity)


async def _counted_page[T, Columns: tuple[object, ...]](
    db: AsyncSession,
    statement: Select[Columns],
    decode: Callable[[Row[Columns]], T],
    *,
    limit: int,
    offset: int,
) -> tuple[list[T], int]:
    """A window count remains exact even when the requested offset is past the end."""
    counted = statement.add_columns(func.count().over().label("_display_total"))
    stream = await db.stream(
        counted.limit(offset + limit).execution_options(yield_per=DISPLAY_READ_BATCH_ROWS)
    )
    rows: list[T] = []
    total = 0
    position = 0
    try:
        async for row in stream:
            total = int(row._mapping["_display_total"])
            if position >= offset:
                rows.append(decode(row))
            position += 1
    finally:
        await stream.close()
    return rows, total


async def read_display_page[T, Columns: tuple[object, ...]](
    db: AsyncSession,
    statement: Select[Columns],
    *,
    decode: Callable[[Row[Columns]], T],
    query: str,
    text_of: Callable[[T], Sequence[str | None]],
    limit: int,
    offset: int = 0,
    name_key: Callable[[T], tuple[str, str]] | None = None,
) -> tuple[list[T], int]:
    """Filter the whole owned selection before paging, retaining only its prefix.

    Args:
        db: The owning reader's session, with no network operation inside it.
        statement: Owned, ordered selection; limits and offsets are applied here.
        decode: Typed projection of a source row into the reader's output.
        query: Literal fragment, matched against each displayed field separately.
        text_of: Only the fields actually displayed to this reader.
        limit: Page size, positive.
        offset: Number of matching rows to skip, nonnegative.
        name_key: Canonical name and identity key, when alphabetical order is requested.

    Returns:
        The requested page and the exact matching total from the same statement.

    Raises:
        ValueError: Invalid internal paging arguments.
    """
    if limit < 1 or offset < 0:
        raise ValueError("Invalid display pagination")
    base = statement.limit(None).offset(None)
    needle = normalize_search_text(query.strip())
    if not needle and name_key is None:
        return await _counted_page(db, base, decode, limit=limit, offset=offset)
    retained: list[T] = []
    named: list[Ranked[T]] = []
    total = 0
    capacity = offset + limit
    stream = await db.stream(base.execution_options(yield_per=DISPLAY_READ_BATCH_ROWS))
    try:
        async for raw in stream:
            row = decode(raw)
            if needle and not any(
                needle in normalize_search_text(text or "") for text in text_of(row)
            ):
                continue
            total += 1
            if name_key is not None:
                _keep_smallest(named, (name_key(row), total, row), capacity)
            elif len(retained) < capacity:
                retained.append(row)
    finally:
        await stream.close()
    if name_key is not None:
        retained = [entry[2] for entry in sorted(named)]
    return retained[offset:], total


async def read_display_rows[T](
    db: AsyncSession,
    statement: Select[tuple[T]],
    *,
    query: str,
    text_of: Callable[[T], str | None],
    cap: int,
) -> tuple[list[T], int]:
    """Scalar-source compatibility door for the bounded activity timeline pools."""
    return await read_display_page(
        db,
        statement,
        decode=lambda row: row[0],
        query=query,
        text_of=lambda row: (text_of(row),),
        limit=cap,
    )
