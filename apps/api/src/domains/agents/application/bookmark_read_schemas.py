"""UI paging and explicit character windows keep arbitrarily long answers reachable."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from src.core.constants import (
    BOOKMARKS_PAGE_DEFAULT_LIMIT,
    BOOKMARKS_PAGE_MAX_LIMIT,
    BOOKMARKS_PAGE_MIN_LIMIT,
)
from src.domains.bookmarks.schemas import BookmarkListResponse
from src.domains.bookmarks.ui_projection import BOOKMARK_QUERY_MAX_LENGTH

BOOKMARK_READ_MAX_BYTES = 64_000
BOOKMARK_CONTENT_WINDOW_MAX = 10_000


class BookmarkReadQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    q: str | None = Field(default=None, max_length=BOOKMARK_QUERY_MAX_LENGTH)
    limit: StrictInt = Field(
        default=BOOKMARKS_PAGE_DEFAULT_LIMIT,
        ge=BOOKMARKS_PAGE_MIN_LIMIT,
        le=BOOKMARKS_PAGE_MAX_LIMIT,
    )
    offset: StrictInt = Field(default=0, ge=0)
    content_offset: StrictInt = Field(default=0, ge=0)
    content_limit: StrictInt = Field(
        default=BOOKMARK_CONTENT_WINDOW_MAX, ge=1, le=BOOKMARK_CONTENT_WINDOW_MAX
    )


class BookmarkTextWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    total_chars: StrictInt
    offset: StrictInt
    next_offset: StrictInt | None


class BookmarkWindows(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    content: BookmarkTextWindow
    request_content: BookmarkTextWindow | None


class BookmarkReadProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_at: AwareDatetime
    page: BookmarkListResponse
    next_offset: StrictInt | None
    content_windows: dict[str, BookmarkWindows]
