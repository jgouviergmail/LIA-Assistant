"""The documents a person may attach to a message, listed across their spaces.

Mounted BEFORE the ``/{space_id}`` routes of the space router (a literal
``documents`` would otherwise be read as a space id); it inherits the prefix,
the tags and the capability gate. What it lists is what the composer's « + »
offers: the ``ready`` documents of every space the person owns, active or
not, with the space named beside each one and an exact total (ADR-185). The
page bound is published because it is enforced (ADR-184).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RAG_SPACES_BULK_MAX
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.rag_spaces.repository import RAGDocumentRepository
from src.domains.users.models import User

router = APIRouter()

#: Largest page the listing serves — published in every response.
MAX_LIMIT = RAG_SPACES_BULK_MAX
DEFAULT_LIMIT = 20


class AttachableDocument(BaseModel):
    """One document the composer may attach, with the space it lives in."""

    id: UUID = Field(description="The document id.")
    space_id: UUID = Field(description="The space the document belongs to.")
    space_name: str = Field(description="The space's name, shown beside the document.")
    space_is_active: bool = Field(description="Whether the space is searched by the chat.")
    original_filename: str = Field(description="Display name.")
    content_type: str = Field(description="MIME type of the stored file.")
    file_size: int = Field(description="Size in bytes.")
    created_at: datetime = Field(description="When the document was indexed.")


class AttachableDocumentsResponse(BaseModel):
    """A page of attachable documents and the exact total of the set."""

    items: list[AttachableDocument]
    total: int = Field(description="Exact total of the filtered set (ADR-185).")
    limit: int
    offset: int
    max_limit: int = Field(description="The page bound the API enforces (ADR-184).")


@router.get(
    "/documents",
    response_model=AttachableDocumentsResponse,
    summary="List the documents the composer may attach (every space, active or not)",
)
async def list_attachable_documents(
    q: str | None = Query(default=None, max_length=200, description="Name fragment."),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> AttachableDocumentsResponse:
    """The ``ready`` documents of the caller's spaces, a page and the exact total."""
    rows, total = await RAGDocumentRepository(db).search_ready_for_user(
        user.id, needle=(q or "").strip() or None, limit=limit, offset=offset
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


__all__ = ["AttachableDocument", "AttachableDocumentsResponse", "router"]
