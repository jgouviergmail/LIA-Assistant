"""Read the real owned saved-answer view without indexing or loading chat history."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.bookmark_read_schemas import (
    BOOKMARK_READ_MAX_BYTES,
    BookmarkReadProjection,
    BookmarkReadQuery,
    BookmarkTextWindow,
    BookmarkWindows,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.queries import BookmarkFilters
from src.domains.bookmarks.ui_projection import read_bookmark_page


def _window(text: str, query: BookmarkReadQuery) -> tuple[str, BookmarkTextWindow]:
    start = query.content_offset
    selected = text[start : start + query.content_limit]
    end = start + len(selected)
    return selected, BookmarkTextWindow(
        total_chars=len(text), offset=start, next_offset=end if end < len(text) else None
    )


async def read_bookmarks(
    db: AsyncSession, actor_id: UUID, query: BookmarkReadQuery
) -> BookmarkReadProjection:
    selected = BookmarkReadQuery.model_validate(query.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    page = await read_bookmark_page(
        db,
        actor_id,
        BookmarkFilters(query=selected.q, limit=selected.limit, offset=selected.offset),
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    ids = [item.id for item in page.items]
    if ids and await db.scalar(
        select(func.count(MessageBookmark.id)).where(
            MessageBookmark.id.in_(ids), MessageBookmark.user_id == actor_id
        )
    ) != len(ids):
        raise CommandRejected("STALE_STATE")
    windows = {}
    items = []
    for item in page.items:
        content, content_window = _window(item.content, selected)
        request, request_window = None, None
        if item.request_content is not None:
            request, request_window = _window(item.request_content, selected)
        items.append(item.model_copy(update={"content": content, "request_content": request}))
        windows[str(item.id)] = BookmarkWindows(
            content=content_window, request_content=request_window
        )
    end = selected.offset + len(items)
    result = BookmarkReadProjection(
        observed_at=datetime.now(UTC),
        page=page.model_copy(update={"items": items}),
        next_offset=end if items and end < page.total else None,
        content_windows=windows,
    )
    if len(result.model_dump_json().encode("utf-8")) > BOOKMARK_READ_MAX_BYTES:
        raise ValueError(
            "Saved-answer page exceeds the result bound; use fewer items or smaller content windows"
        )
    return result
