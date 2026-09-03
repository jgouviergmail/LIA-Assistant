"""Where a document lives, and whether the caller may touch it (ADR-259).

The only place that turns a ``RAGDocument`` row into a file path: the storage
root, the owner, the space, then the stored filename, each segment resolved
and checked to stay inside the space directory. The ownership check is the
one every document operation shares — reading, deleting, downloading, moving.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from fastapi import status

from src.core.config import settings
from src.core.exceptions import BaseAPIException

if TYPE_CHECKING:
    from src.domains.rag_spaces.models import RAGDocument
    from src.domains.rag_spaces.service import RAGSpaceService


def raise_document_not_found(document_id: uuid.UUID) -> NoReturn:
    """Raise 404 when document is not found."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Document not found",
        log_event="rag_document_not_found",
        document_id=str(document_id),
    )


def document_file_path(document: RAGDocument) -> Path:
    """The on-disk path of a document's stored file.

    Args:
        document: The row; ``user_id``, ``space_id`` and ``filename`` locate the file.

    Returns:
        The resolved path under the storage root.

    Raises:
        RuntimeError: When the filename would escape the space directory.
    """
    root = Path(settings.rag_spaces_storage_path).resolve()
    scope = (root / str(document.user_id) / str(document.space_id)).resolve()
    path = (scope / document.filename).resolve()
    if not path.is_relative_to(scope):
        raise RuntimeError(
            "RAG storage path integrity violation: resolved file escapes the space directory"
        )
    return path


async def owned_document(
    service: RAGSpaceService,
    space_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> RAGDocument:
    """The document, once the space is the user's and the row belongs to it.

    Args:
        service: The space service (space ownership + document repository).
        space_id: The space the caller addresses.
        document_id: The document the caller addresses.
        user_id: The caller.

    Returns:
        The document row.

    Raises:
        BaseAPIException: 404 when the space or the document is not the caller's.
    """
    await service.get_space(space_id, user_id)
    document = await service.doc_repo.get_by_id(document_id)
    if not document or document.space_id != space_id or document.user_id != user_id:
        raise_document_not_found(document_id)
    return document
