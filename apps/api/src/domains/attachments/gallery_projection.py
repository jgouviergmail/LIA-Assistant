"""One shared UI/native gallery page with exact filtered totals and keep ceilings."""

from typing import Literal, get_args
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.gallery_queries import GalleryFilters
from src.domains.attachments.keep import keep_usage
from src.domains.attachments.models import AttachmentOrigin
from src.domains.attachments.schemas import (
    GeneratedAssetKeepUsage,
    GeneratedAssetListResponse,
    GeneratedAssetSummary,
)
from src.domains.attachments.service import AttachmentService

GalleryFamily = Literal["images", "documents", "screenshots"]
GALLERY_FAMILIES: dict[str, AttachmentOrigin] = {
    "images": AttachmentOrigin.GENERATED_IMAGE,
    "documents": AttachmentOrigin.GENERATED_DOCUMENT,
    "screenshots": AttachmentOrigin.BROWSER_SCREENSHOT,
}
GALLERY_MIN_LIMIT, GALLERY_MAX_LIMIT, GALLERY_DEFAULT_LIMIT = 1, 100, 24
GALLERY_QUERY_MAX_LENGTH = 200
assert set(GALLERY_FAMILIES) == set(get_args(GalleryFamily))


async def read_gallery_page(
    db: AsyncSession, actor_id: UUID, filters: GalleryFilters
) -> GeneratedAssetListResponse:
    rows, total, total_bytes = await AttachmentService(db).list_generated(actor_id, filters)
    return GeneratedAssetListResponse(
        items=[GeneratedAssetSummary.model_validate(row) for row in rows],
        total=total,
        total_bytes=total_bytes,
        limit=filters.limit,
        offset=filters.offset,
        max_limit=GALLERY_MAX_LIMIT,
        keep=GeneratedAssetKeepUsage.model_validate(await keep_usage(db, actor_id)),
    )
