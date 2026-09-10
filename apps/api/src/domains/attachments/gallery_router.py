"""The gallery of what LIA produced — list, download, delete (ADR-279).

A separate router from ``attachments`` for one reason that is not cosmetic:
that one carries ``capability_dependencies(ATTACHMENTS)`` on the ROUTER, so an
administrator switching UPLOADS off would also close the door on files the
person can no longer produce but can still legitimately keep, read and delete.
Uploads and the gallery are two capabilities that happen to share a table.

Everything here reads the person's own rows: ``user_id`` is a filter of every
statement, and the two mutating routes go through the service, which verifies
ownership before touching disk.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input
from src.core.session_dependencies import get_current_active_session
from src.domains.attachments.gallery_queries import GALLERY_SORTS, GalleryFilters
from src.domains.attachments.models import AttachmentOrigin
from src.domains.attachments.schemas import (
    GeneratedAssetListResponse,
    GeneratedAssetsDeleteRequest,
    GeneratedAssetsDeleteResponse,
    GeneratedAssetSummary,
)
from src.domains.attachments.service import AttachmentService
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/generated-assets", tags=["Generated assets"])

#: What a reader may list. Deliberately the GENERATED origins only — the enum
#: member is resolved from this map, never built from a raw query string.
_LISTABLE: dict[str, AttachmentOrigin] = {
    "images": AttachmentOrigin.GENERATED_IMAGE,
    "documents": AttachmentOrigin.GENERATED_DOCUMENT,
    "screenshots": AttachmentOrigin.BROWSER_SCREENSHOT,
}

#: Page size bounds. Published to the client through the response (ADR-184).
_MIN_LIMIT, _MAX_LIMIT, _DEFAULT_LIMIT = 1, 100, 24


@router.get(
    "",
    response_model=GeneratedAssetListResponse,
    summary="List the files LIA produced for the current user",
)
async def list_generated_assets(
    family: Annotated[str, Query(description="images | documents | screenshots")],
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    q: Annotated[str | None, Query(max_length=200)] = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    expires_before: datetime | None = None,
    sort: Annotated[str, Query()] = "created_desc",
    limit: Annotated[int, Query(ge=_MIN_LIMIT, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GeneratedAssetListResponse:
    """One page of one family, and the EXACT total behind it.

    Args:
        family: Which gallery.
        user: The authenticated account.
        db: Session.
        q: Needle matched against the title and the original filename.
        created_after: Inclusive lower bound on the creation instant.
        created_before: Inclusive upper bound on the creation instant.
        expires_before: Inclusive upper bound on the expiry instant.
        sort: One of :data:`GALLERY_SORTS`.
        limit: Page size.
        offset: Page start.

    Returns:
        The page, its exact total (ADR-185) and the bounds the caller must
        respect — an enforced bound the producer cannot read is a trap
        (ADR-184).

    Raises:
        HTTPException: 400 when the family or the sort is not one this API
            offers. A silent fallback would show a different set from the one
            asked for, with nothing saying so.
    """
    origin = _LISTABLE.get(family)
    if origin is None:
        raise_invalid_input(f"unknown family {family!r}; expected one of {sorted(_LISTABLE)}")
    if sort not in GALLERY_SORTS:
        raise_invalid_input(f"unknown sort {sort!r}; expected one of {sorted(GALLERY_SORTS)}")

    assert origin is not None  # narrowed by the raiser above (NoReturn)
    filters = GalleryFilters(
        origin=origin,
        query=q,
        created_after=created_after,
        created_before=created_before,
        expires_before=expires_before,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    service = AttachmentService(db)
    rows, total, total_bytes = await service.list_generated(user.id, filters)
    return GeneratedAssetListResponse(
        items=[GeneratedAssetSummary.model_validate(row) for row in rows],
        total=total,
        total_bytes=total_bytes,
        limit=limit,
        offset=offset,
        max_limit=_MAX_LIMIT,
    )


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one generated file",
)
async def delete_generated_asset(
    asset_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove one file the person owns, from disk and from the database.

    Args:
        asset_id: The file.
        user: The authenticated account.
        db: Session.
    """
    await AttachmentService(db).delete_for_user_single(attachment_id=asset_id, user_id=user.id)


@router.post(
    "/delete",
    response_model=GeneratedAssetsDeleteResponse,
    summary="Delete several generated files at once",
)
async def delete_generated_assets(
    payload: GeneratedAssetsDeleteRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> GeneratedAssetsDeleteResponse:
    """Remove a selection, and say EXACTLY what went.

    A file the caller does not own, or that expired between the listing and the
    click, is reported as skipped rather than counted as deleted: « three
    deleted » when two are gone is the class of claim ADR-185 forbids.

    Args:
        payload: The ids to remove.
        user: The authenticated account.
        db: Session.

    Returns:
        What was deleted and what was not.
    """
    deleted, skipped = await AttachmentService(db).delete_generated_batch(user.id, payload.ids)
    logger.info(
        "generated_assets_bulk_deleted",
        user_id=str(user.id),
        deleted=len(deleted),
        skipped=len(skipped),
    )
    return GeneratedAssetsDeleteResponse(deleted=deleted, skipped=skipped)
