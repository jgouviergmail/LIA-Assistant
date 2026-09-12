"""What the bookmarks tab asks the database (ADR-282).

The gallery's rules (`attachments/gallery_queries.py`), applied to a table of
answers:

- **A page and its count come from ONE statement** (ADR-185): ``count=True``
  returns the same ``WHERE`` with the ordering and the paging removed.
- **The ordering ends on the primary key**: two answers written in the same
  millisecond otherwise repeat or vanish at a page boundary.
- **A search needle is DATA, never a pattern** — ``escape_like`` is applied.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select

from src.core.constants import BOOKMARKS_PAGE_DEFAULT_LIMIT
from src.core.sql_search import escape_like
from src.domains.bookmarks.models import MessageBookmark

__all__ = ["BookmarkFilters", "build_bookmarks_statement"]


@dataclass(frozen=True)
class BookmarkFilters:
    """What the reader narrowed their bookmarks to.

    Attributes:
        query: A needle matched against the answer and the request.
        limit: Page size.
        offset: Page start.
    """

    query: str | None = None
    limit: int = BOOKMARKS_PAGE_DEFAULT_LIMIT
    offset: int = 0


def build_bookmarks_statement(
    user_id: uuid.UUID, filters: BookmarkFilters, *, count: bool = False
) -> Select[Any]:
    """The rows of one page of bookmarks, or the exact total behind them.

    Args:
        user_id: Whose bookmarks.
        filters: What they are narrowed to.
        count: True for the total over the WHOLE filtered set.

    Returns:
        The statement.
    """
    columns = func.count() if count else MessageBookmark
    statement = select(columns).where(MessageBookmark.user_id == user_id)

    needle = (filters.query or "").strip()
    if needle:
        pattern = f"%{escape_like(needle.lower())}%"
        statement = statement.where(
            or_(
                func.lower(MessageBookmark.content).like(pattern, escape="\\"),
                func.lower(MessageBookmark.request_content).like(pattern, escape="\\"),
            )
        )

    if count:
        return statement

    return (
        statement.order_by(MessageBookmark.answered_at.desc(), MessageBookmark.id.desc())
        .limit(filters.limit)
        .offset(filters.offset)
    )
