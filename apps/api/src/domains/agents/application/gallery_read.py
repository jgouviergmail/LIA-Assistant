"""Observe the real gallery without generating cards, spending or changing retention."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.gallery_read_schemas import (
    GALLERY_READ_MAX_BYTES,
    GalleryReadProjection,
    GalleryReadQuery,
)
from src.domains.attachments.gallery_projection import GALLERY_FAMILIES, read_gallery_page
from src.domains.attachments.gallery_queries import GalleryFilters
from src.domains.attachments.models import Attachment


async def read_gallery(
    db: AsyncSession, actor_id: UUID, query: GalleryReadQuery
) -> GalleryReadProjection:
    selected = GalleryReadQuery.model_validate(query.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    page = await read_gallery_page(
        db,
        actor_id,
        GalleryFilters(
            origin=GALLERY_FAMILIES[selected.family],
            query=selected.q,
            created_after=selected.created_after,
            created_before=selected.created_before,
            expires_before=selected.expires_before,
            sort=selected.sort,
            limit=selected.limit,
            offset=selected.offset,
        ),
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    ids = [item.id for item in page.items]
    if ids and await db.scalar(
        select(func.count(Attachment.id)).where(
            Attachment.id.in_(ids),
            Attachment.user_id == actor_id,
            Attachment.origin == GALLERY_FAMILIES[selected.family].value,
        )
    ) != len(ids):
        raise CommandRejected("STALE_STATE")
    end = selected.offset + len(page.items)
    result = GalleryReadProjection(
        family=selected.family,
        observed_at=datetime.now(UTC),
        page=page,
        next_offset=end if page.items and end < page.total else None,
    )
    if len(result.model_dump_json().encode("utf-8")) > GALLERY_READ_MAX_BYTES:
        raise ValueError("Gallery page too large; request fewer items")
    return result
