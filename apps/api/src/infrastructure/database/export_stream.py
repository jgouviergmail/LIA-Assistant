"""Reading a whole register out of the database, at constant memory (ADR-273).

Replaces ``export_window``, whose job was to decide which rows a CAPPED read
kept. There is no cap any more: an extraction of a register is complete or it
is not an extraction — a record that answers « what did this system do » with
an unexplained subset is a record nobody can rely on.

What replaced the ceiling is a **server-side cursor**. The rows are read in
partitions and handed to the renderer one at a time, so the memory a request
holds is the size of one partition rather than the size of the register. The
ceiling existed for a measured reason (a five-record, 5 000-row extraction
peaked at 33,9 MB on the Raspberry Pi 5 this project deploys to); that reason
is answered here by bounding the BUFFER, which is the thing that was actually
scarce, instead of bounding the truth, which was not.

Two properties this module owns, and both are load-bearing:

- **the order is chronological, and it is applied here.** ``export_window``
  existed because a ceiling had been applied to an unordered read and
  PostgreSQL returned the oldest rows; the lesson survives its cause — a
  register reads forward, and no caller composes that ordering itself.
- **each row is detached once it has been rendered.** A streamed ORM read
  still registers every instance in the session, so a session that survives
  the whole scan holds the whole register in memory and the cursor buys
  nothing. Rows are therefore expunged ONE BY ONE, after the consumer is done
  with each — never with ``expunge_all``, which replaces the session's
  identity map and KILLS the old one: the cursor is still loading into it, and
  the next partition dies on *"this identity map is no longer valid"*
  (measured against real PostgreSQL, 2026-09-07 — the unit tests could not see
  it, because a stubbed stream has no identity map at all). The session passed
  here is DEDICATED to the read all the same: the caller opens it
  (``get_db_context``), and a detached row is not what a shared session's other
  users expect.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession


async def stream_all(
    db: AsyncSession,
    statement: Select[Any],
    *,
    oldest_first: Sequence[Any],
    batch: int,
) -> AsyncIterator[Any]:
    """Every row a filtered query matches, oldest first, at constant memory.

    Args:
        db: A session DEDICATED to this read — every row it produces is
            detached once rendered, which is not what a shared session's other
            users expect.
        statement: The already-filtered SELECT, with no ordering or limit of
            its own.
        oldest_first: The ordering that puts the oldest row first — the
            timestamp ascending, plus a tie-break so two rows sharing an
            instant come back in the same order on every call.
        batch: How many rows the cursor buffers at a time. The only number
            that bounds memory here, and it bounds it whatever the register
            weighs.

    Yields:
        The matching rows, oldest first, all of them.
    """
    ordered = statement.order_by(*oldest_first).execution_options(yield_per=batch)
    result = await db.stream_scalars(ordered)
    async for partition in result.partitions(batch):
        for row in partition:
            yield row
            # Control returns here once the consumer has rendered the row, so
            # detaching it now is what keeps the cursor's promise. One row at a
            # time: `expunge_all` would kill the identity map the open cursor
            # is still loading into.
            with suppress(InvalidRequestError):
                db.expunge(row)


async def count_all(db: AsyncSession, statement: Select[Any]) -> int:
    """How many rows the same filtered query matches.

    The companion of :func:`stream_all`, and not a convenience: a streamed
    response sends its headers before its body, so the exact total cannot be
    counted while rendering. It is counted first, over a CLOSED window (the
    caller pins the upper bound to the moment it generates the file), so the
    number it publishes and the rows it then streams describe the same set.

    Args:
        db: Session.
        statement: The already-filtered SELECT.

    Returns:
        The exact number of matching rows. A count shown to a reader is exact
        or it does not exist (ADR-185).
    """
    total = await db.scalar(select(func.count()).select_from(statement.subquery()))
    return int(total or 0)


__all__ = ["count_all", "stream_all"]
