"""One public DTO and source projection for the composer's cross-space ready documents."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RAG_SPACES_BULK_MAX
from src.domains.rag_spaces.repository import RAGDocumentRepository

MAX_LIMIT = RAG_SPACES_BULK_MAX
DEFAULT_LIMIT = 20


class AttachableDocument(BaseModel):
    """One attachable document, with its actual owning space."""

    id: UUID = Field(description="The document id.")
    space_id: UUID = Field(description="The space the document belongs to.")
    space_name: str = Field(description="The space's name, shown beside the document.")
    space_is_active: bool = Field(description="Whether the space is searched by the chat.")
    original_filename: str = Field(description="Display name.")
    content_type: str = Field(description="MIME type of the stored file.")
    file_size: int = Field(description="Size in bytes.")
    created_at: datetime = Field(description="When the document was indexed.")


class AttachableDocumentsResponse(BaseModel):
    """A source page and exact whole-set count, including inactive personal spaces."""

    items: list[AttachableDocument]
    total: int = Field(description="Exact total of the filtered set (ADR-185).")
    limit: int
    offset: int
    max_limit: int = Field(description="The page bound the API enforces (ADR-184).")


async def read_document_catalogue(
    db: AsyncSession, user_id: UUID, *, q: str | None, limit: int, offset: int
) -> AttachableDocumentsResponse:
    rows, total = await RAGDocumentRepository(db).search_ready_for_user(
        user_id, needle=(q or "").strip() or None, limit=limit, offset=offset
    )
    return AttachableDocumentsResponse(
        items=[
            AttachableDocument(
                id=row.id,
                space_id=row.space_id,
                space_name=row.space.name,
                space_is_active=row.space.is_active,
                original_filename=row.original_filename,
                content_type=row.content_type,
                file_size=row.file_size,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
        max_limit=MAX_LIMIT,
    )
