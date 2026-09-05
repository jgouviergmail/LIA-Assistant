"""Which rows a capped read actually returns (ADR-263).

Infrastructure rather than a domain module, and not by accident: five
repositories in two bounded contexts need it, and keeping it inside one of them
made the other import across the boundary — a runtime cycle the coupling
ratchet refused. The rule is generic (a ceiling keeps the END of a history), so
it belongs where both callers can reach it without knowing about each other.

A defect measured on the developer instance, 2026-09-05, and the reason this
module exists: every export read ordered oldest-first and then applied its
ceiling, so an export with no period returned **the beginning of history**. On
an eight-month table the exported window was 31 January to 5 March — the first
five weeks — and it showed eight models where the instance had since used
forty-three. The file was not lying (its header said ``truncated``), but the
answer it gave was the wrong five weeks, and nobody reading it would guess.

The rule, in one place because five repositories need it: **the window is the
most RECENT rows; the presentation is chronological.** ``ORDER BY … DESC LIMIT
n``, then reversed — one round trip, no subquery, and a reader still gets a
history that reads forward.

Two consequences worth stating rather than discovering:

- an export with a period is unaffected: the ceiling only bites when the period
  holds more rows than it, and then it keeps the end of that period;
- « the most recent » is what an operator and a regulator both mean by « what
  is this system doing », so this is also the honest default.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession


async def newest_window(
    db: AsyncSession,
    statement: Select[Any],
    *,
    newest_first: Sequence[Any],
    limit: int,
) -> list[Any]:
    """The most recent rows a filtered query matches, returned oldest first.

    Args:
        db: The session.
        statement: The already-filtered SELECT, with no ordering or limit of
            its own.
        newest_first: The ordering that puts the newest row first — the
            timestamp descending, plus a tie-break so two rows sharing an
            instant come back in the same order on every call.
        limit: The ceiling. Published by the caller in the file's header, never
            applied in silence.

    Returns:
        Up to ``limit`` rows, oldest first. A history reads forward; a ceiling
        keeps the end.
    """
    rows = await db.execute(statement.order_by(*newest_first).limit(limit))
    return list(reversed(rows.scalars().all()))


__all__ = ["newest_window"]
