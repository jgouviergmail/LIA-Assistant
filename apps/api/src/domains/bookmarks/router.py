"""The answers a person keeps — keep, list, state, remove (ADR-282).

Everything here reads the person's own rows: ``user_id`` is a filter of every
statement. The operator's switch (``PlatformCapability.BOOKMARKS``) guards the
act of KEEPING alone — the route-level shape uploads took in ADR-279 — so an
administrator switching the act off does not close the door on what a person
already kept.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    BOOKMARKS_PAGE_DEFAULT_LIMIT,
    BOOKMARKS_PAGE_MAX_LIMIT,
    BOOKMARKS_PAGE_MIN_LIMIT,
)
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.bookmarks.errors import raise_bookmark_not_found
from src.domains.bookmarks.queries import BookmarkFilters
from src.domains.bookmarks.schemas import (
    BookmarkKeepRequest,
    BookmarkListResponse,
    BookmarkResponse,
    BookmarkStateResponse,
)
from src.domains.bookmarks.service import BookmarkService
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User

router = APIRouter(prefix="/bookmarks", tags=["Bookmarks"])

#: The guard of the ACT. Module-level so the unit suite can let it through and
#: the wiring guard can find it on the route.
KEEP_GUARD = capability_dependencies(PlatformCapability.BOOKMARKS)


@router.post(
    "",
    response_model=BookmarkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=KEEP_GUARD,
    summary="Keep one assistant answer",
)
async def keep_bookmark(
    payload: BookmarkKeepRequest,
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> BookmarkResponse:
    """Copy the answer, the request that produced it and its date.

    Idempotent: a message already kept answers 200 with its bookmark rather
    than a conflict — the bubble's toggle asked for a state, not for a row.

    Args:
        payload: The archived message the bubble carries.
        response: Used to say 200 when the row already existed.
        user: The authenticated account.
        db: Session.

    Returns:
        The bookmark.
    """
    bookmark, created = await BookmarkService(db).keep(
        user.id, payload.message_id, language=user.language
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return BookmarkResponse.model_validate(bookmark)


@router.get(
    "",
    response_model=BookmarkListResponse,
    summary="List the answers the current user kept",
)
async def list_bookmarks(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[
        int, Query(ge=BOOKMARKS_PAGE_MIN_LIMIT, le=BOOKMARKS_PAGE_MAX_LIMIT)
    ] = BOOKMARKS_PAGE_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BookmarkListResponse:
    """One page, newest answer first, and the EXACT total behind it.

    Args:
        user: The authenticated account.
        db: Session.
        q: Needle matched against the answer and the request.
        limit: Page size.
        offset: Page start.

    Returns:
        The page, its total (ADR-185) and the bounds the caller must respect
        (ADR-184).
    """
    filters = BookmarkFilters(query=q, limit=limit, offset=offset)
    rows, total = await BookmarkService(db).list_page(user.id, filters)
    return BookmarkListResponse(
        items=[BookmarkResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        max_limit=BOOKMARKS_PAGE_MAX_LIMIT,
        max_per_user=settings.bookmarks_max_per_user,
    )


@router.get(
    "/state",
    response_model=BookmarkStateResponse,
    summary="Which archived messages the current user kept",
)
async def bookmark_state(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> BookmarkStateResponse:
    """What every bubble needs to draw its toggle — one small payload.

    Args:
        user: The authenticated account.
        db: Session.

    Returns:
        ``message_id → bookmark_id`` for every bookmark still attached.
    """
    return BookmarkStateResponse(
        message_ids=await BookmarkService(db).attached_message_ids(user.id)
    )


@router.delete(
    "/by-message/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Drop the bookmark taken from one message",
)
async def remove_bookmark_by_message(
    message_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """The bubble's second click.

    Args:
        message_id: The archived message.
        user: The authenticated account.
        db: Session.

    Raises:
        HTTPException: 404 when no bookmark was attached to that message.
    """
    if not await BookmarkService(db).remove_by_message(user.id, message_id):
        raise_bookmark_not_found(message_id)


@router.delete(
    "/{bookmark_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one bookmark",
)
async def remove_bookmark(
    bookmark_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove one bookmark the person owns.

    Args:
        bookmark_id: The bookmark.
        user: The authenticated account.
        db: Session.
    """
    await BookmarkService(db).remove(user.id, bookmark_id)
