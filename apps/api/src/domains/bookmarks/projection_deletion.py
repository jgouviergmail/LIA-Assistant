"""A bookmark can remove only its exact owned projection, parent and owned chunks."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.bookmarks.models import MessageBookmark
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDocumentSourceType, RAGSpace


async def require_owned_projection(
    db: AsyncSession, bookmark: MessageBookmark, document: RAGDocument, *, lock: bool = True
) -> None:
    await db.refresh(document)
    space_id = document.space_id
    statement = select(RAGSpace.user_id).where(RAGSpace.id == space_id)
    owner = await db.scalar(statement.with_for_update() if lock else statement)
    if lock:
        await db.execute(
            select(RAGDocument.id).where(RAGDocument.id == document.id).with_for_update()
        )
    await db.refresh(document)
    if (
        owner != bookmark.user_id
        or document.user_id != bookmark.user_id
        or document.space_id != space_id
        or document.source_type != RAGDocumentSourceType.BOOKMARK
    ):
        raise ResourceConflictError("bookmark", detail={"error_code": "STALE_STATE"})
    invalid = await db.scalar(
        select(func.count(RAGChunk.id)).where(
            RAGChunk.document_id == document.id,
            or_(
                RAGChunk.user_id.is_distinct_from(bookmark.user_id),
                RAGChunk.space_id.is_distinct_from(space_id),
            ),
        )
    )
    if invalid:
        raise ResourceConflictError("bookmark", detail={"error_code": "STALE_STATE"})
    shared = await db.scalar(
        select(func.count(MessageBookmark.id)).where(
            MessageBookmark.rag_document_id == document.id,
            MessageBookmark.id != bookmark.id,
        )
    )
    if shared:
        raise ResourceConflictError("bookmark", detail={"error_code": "STALE_STATE"})
    shared_file = await db.scalar(
        select(func.count(RAGDocument.id)).where(
            RAGDocument.id != document.id,
            RAGDocument.user_id == document.user_id,
            RAGDocument.space_id == space_id,
            RAGDocument.filename == document.filename,
        )
    )
    if shared_file:
        raise ResourceConflictError("bookmark", detail={"error_code": "STALE_STATE"})
