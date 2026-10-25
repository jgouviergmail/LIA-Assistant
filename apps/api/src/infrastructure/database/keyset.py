"""Keyset pagination over several sources merged into one timeline.

A merged timeline orders every item by ``(instant, kind, id)``, newest first,
and its cursor is the last item served. Each source is then asked for its
rows strictly AFTER that cursor in that order — a condition that depends on
how the source's kind compares with the cursor's:

- an EARLIER kind at the cursor's instant comes after it: the whole instant
  is still to serve (``at <= cursor``);
- a LATER kind at that instant was served before it (``at < cursor``);
- the SAME kind continues by id (``(at, id) < (cursor at, cursor id)``).

An offset would skip or repeat rows as soon as one lands between two pages;
a keyset never does, and every ordering ends on the primary key (ADR-185).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import InstrumentedAttribute


@dataclass(frozen=True, slots=True)
class Keyset:
    """Where ONE source resumes after a merged timeline's cursor.

    Attributes:
        at: The cursor's instant.
        id: The cursor's id when it is this source's own row; None otherwise.
        inclusive: Whether rows AT the instant are still to serve (an earlier
            kind) — ignored when ``id`` is given.
    """

    at: datetime
    id: UUID | None = None
    inclusive: bool = False

    @classmethod
    def after(cls, kind: str, at: datetime, cursor_kind: str, cursor_id: UUID) -> Keyset:
        """The resumption of source ``kind`` after a cursor ``(at, cursor_kind, cursor_id)``."""
        if kind == cursor_kind:
            return cls(at=at, id=cursor_id)
        return cls(at=at, inclusive=kind < cursor_kind)


def older_than(
    at: InstrumentedAttribute[datetime] | InstrumentedAttribute[datetime | None],
    row_id: InstrumentedAttribute[UUID],
    keyset: Keyset,
) -> ColumnElement[bool]:
    """The rows of a source strictly after ``keyset`` in newest-first order.

    Args:
        at: The source's instant column.
        row_id: The source's primary key.
        keyset: Where it resumes.

    Returns:
        The SQL condition.
    """
    if keyset.id is not None:
        return or_(at < keyset.at, and_(at == keyset.at, row_id < keyset.id))
    return at <= keyset.at if keyset.inclusive else at < keyset.at


__all__ = ["Keyset", "older_than"]
