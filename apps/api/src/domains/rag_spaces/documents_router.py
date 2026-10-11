"""The documents a person may attach to a message, listed across their spaces.

Mounted BEFORE the ``/{space_id}`` routes of the space router (a literal
``documents`` would otherwise be read as a space id); it inherits the prefix,
the tags and the capability gate. What it lists is what the composer's « + »
offers: the ``ready`` documents of every space the person owns, active or
not, with the space named beside each one and an exact total (ADR-185). The
page bound is published because it is enforced (ADR-184).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.rag_spaces.document_catalogue import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    AttachableDocument,
    AttachableDocumentsResponse,
    read_document_catalogue,
)
from src.domains.users.models import User

router = APIRouter()


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
    return await read_document_catalogue(db, user.id, q=q, limit=limit, offset=offset)


__all__ = ["AttachableDocument", "AttachableDocumentsResponse", "router"]
