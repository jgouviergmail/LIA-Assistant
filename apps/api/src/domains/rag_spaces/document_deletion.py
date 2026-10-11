"""Exact bounded row deletion joins the caller's transaction without filesystem effects."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RAG_SPACES_BULK_MAX
from src.domains.rag_spaces.document_access import (
    raise_document_not_found,
    require_deletable_document,
)
from src.domains.rag_spaces.models import RAGChunk, RAGDocument
from src.domains.rag_spaces.ui_queries import owned_space


async def delete_selected_document_rows(
    db: AsyncSession, space_id: UUID, document_ids: tuple[UUID, ...], user_id: UUID
) -> None:
    """Caller holds owner/space/job fences and owns ACK, cleanup and telemetry."""
    identities = tuple(dict.fromkeys(document_ids))
    if not 1 <= len(identities) <= RAG_SPACES_BULK_MAX:
        raise ValueError("Choose a bounded nonempty document selection")
    await owned_space(db, user_id, space_id)
    documents = list(
        (
            await db.scalars(
                select(RAGDocument)
                .where(
                    RAGDocument.id.in_(identities),
                    RAGDocument.space_id == space_id,
                    RAGDocument.user_id == user_id,
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    present = {document.id for document in documents}
    if len(present) != len(identities):
        raise_document_not_found(
            next(identifier for identifier in identities if identifier not in present)
        )
    for document in documents:
        require_deletable_document(document)
    await db.execute(delete(RAGChunk).where(RAGChunk.document_id.in_(identities)))
    await db.execute(
        delete(RAGDocument).where(
            RAGDocument.id.in_(identities),
            RAGDocument.space_id == space_id,
            RAGDocument.user_id == user_id,
        )
    )
    await db.flush()
