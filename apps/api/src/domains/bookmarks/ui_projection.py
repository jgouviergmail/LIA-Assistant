"""One saved-answer projection shared by the UI and native reads, with batched costs."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import BOOKMARKS_PAGE_MAX_LIMIT
from src.domains.bookmarks.queries import BookmarkFilters
from src.domains.bookmarks.schemas import BookmarkListResponse, BookmarkResponse
from src.domains.bookmarks.service import BookmarkService

BOOKMARK_QUERY_MAX_LENGTH = 200


async def read_bookmark_page(
    db: AsyncSession, actor_id: UUID, filters: BookmarkFilters
) -> BookmarkListResponse:
    service = BookmarkService(db)
    rows, total = await service.list_page(actor_id, filters)
    documents = await service.documents_of(rows)
    summaries = await service.answer_costs_of(rows)
    return BookmarkListResponse(
        items=[BookmarkResponse.from_row(row, documents, summaries) for row in rows],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
        max_limit=BOOKMARKS_PAGE_MAX_LIMIT,
        max_per_user=settings.bookmarks_max_per_user,
    )
