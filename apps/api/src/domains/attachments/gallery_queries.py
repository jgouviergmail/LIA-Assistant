"""What the gallery asks the database (ADR-279).

The statement lives beside the repository rather than inside it for the reason
the workboard's `board_queries` was extracted: a listing with a search, two date
windows, five orderings and an exact total is a subject of its own, and the
repository is already at its size.

Three rules, each of which has cost this repository a defect before:

- **A page and its count come from ONE statement** (ADR-185). Building them
  apart lets the total describe a different set from the rows the moment a
  filter is added to one and not the other — so ``count=True`` returns the same
  ``WHERE``, with the ordering and the paging removed.
- **Every ordering ends on the primary key.** Two files created in the same
  millisecond otherwise repeat or vanish at a page boundary — there is no total
  order without a tie-breaker.
- **A search needle is DATA, never a pattern.** ``escape_like`` is applied to
  it: measured on PostgreSQL, an unescaped ``_`` matches every row, and ``100%``
  matches everything starting with ``100`` (the workboard paid for this on
  2026-09-10, `core/sql_search.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select

from src.core.sql_search import escape_like
from src.domains.attachments.models import Attachment, AttachmentOrigin

__all__ = ["GALLERY_SORTS", "GalleryFilters", "build_gallery_statement"]

#: How a gallery may be ordered. A key nobody declared is refused rather than
#: ignored: silently falling back would show a different order from the one the
#: reader picked, with nothing saying so.
GALLERY_SORTS: frozenset[str] = frozenset(
    {"created_desc", "created_asc", "expires_asc", "name_asc"}
)

_DEFAULT_SORT = "created_desc"

_ORDERINGS: dict[str, Any] = {
    "created_desc": Attachment.created_at.desc(),
    "created_asc": Attachment.created_at.asc(),
    "expires_asc": Attachment.expires_at.asc(),
    "name_asc": func.lower(func.coalesce(Attachment.title, Attachment.original_filename)).asc(),
}


@dataclass(frozen=True)
class GalleryFilters:
    """What the reader narrowed their gallery to.

    Attributes:
        origin: Which family — a generated one; ``upload`` is refused, because
            the gallery shows what LIA produced and a person's own uploads live
            in the conversation they were attached to.
        query: A needle matched against the title and the original filename.
        created_after: Inclusive lower bound on the creation instant.
        created_before: Inclusive upper bound on the creation instant.
        expires_before: Inclusive upper bound on the expiry instant — « what am
            I about to lose? ».
        sort: One of :data:`GALLERY_SORTS`.
        limit: Page size.
        offset: Page start.
    """

    origin: AttachmentOrigin
    query: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    expires_before: datetime | None = None
    sort: str = _DEFAULT_SORT
    limit: int = 24
    offset: int = 0

    def __post_init__(self) -> None:
        if self.origin is AttachmentOrigin.UPLOAD:
            raise ValueError(
                "the gallery lists what LIA produced; an upload belongs to its conversation"
            )
        if self.sort not in GALLERY_SORTS:
            raise ValueError(f"unknown sort {self.sort!r}; expected one of {sorted(GALLERY_SORTS)}")


def build_gallery_statement(
    user_id: uuid.UUID, filters: GalleryFilters, *, count: bool = False
) -> Select[Any]:
    """The rows of one gallery page, or the exact total behind them.

    Args:
        user_id: Whose gallery.
        filters: What it is narrowed to.
        count: True for the total over the WHOLE filtered set — the same
            ``WHERE`` as the rows, without ordering or paging.

    Returns:
        The statement.
    """
    columns = func.count() if count else Attachment
    statement = select(columns).where(
        Attachment.user_id == user_id,
        Attachment.origin == filters.origin.value,
    )

    needle = (filters.query or "").strip()
    if needle:
        # The needle is DATA: an unescaped `_` matches every row.
        pattern = f"%{escape_like(needle.lower())}%"
        statement = statement.where(
            or_(
                func.lower(Attachment.title).like(pattern, escape="\\"),
                func.lower(Attachment.original_filename).like(pattern, escape="\\"),
            )
        )
    if filters.created_after is not None:
        statement = statement.where(Attachment.created_at >= filters.created_after)
    if filters.created_before is not None:
        statement = statement.where(Attachment.created_at <= filters.created_before)
    if filters.expires_before is not None:
        statement = statement.where(Attachment.expires_at <= filters.expires_before)

    if count:
        return statement

    # The tie-breaker is not decoration: without a total order two rows sharing
    # the sort key repeat or vanish at a page boundary.
    return (
        statement.order_by(_ORDERINGS[filters.sort], Attachment.id.desc())
        .limit(filters.limit)
        .offset(filters.offset)
    )
