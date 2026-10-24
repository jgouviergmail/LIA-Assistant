"""Where a document lives, and whether the caller may touch it (ADR-259).

The place that turns a ``RAGDocument`` row into a file path: the storage
root, the owner, the space, then the stored filename, each segment resolved
and checked to stay inside the space directory — and, for the callers that
delete, move or fingerprint a file, the stricter :func:`owned_document_path`
that refuses a link anywhere on the way. The ownership check is the one every
document operation shares — reading, deleting, downloading, moving.
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


#: Documents another surface manages, and the stable ``code`` the frontend
#: localises when the person tries to move one (every kind) or to delete one
#: by hand (a kept answer only — the bookmark is the record, its document the
#: projection; a synced or meeting document is re-created by its owner and may
#: be dropped). ONE table, so the two refusals cannot name a kind two ways.
MANAGED_DOCUMENT_CODES: dict[str, str] = {
    "drive": "document_managed_by_drive",
    "meeting": "document_managed_by_meetings",
    "mail": "document_managed_by_mail",
    "bookmark": "document_managed_by_bookmarks",
}

#: The kinds whose deletion by hand is refused (their record lives elsewhere).
UNDELETABLE_DOCUMENT_KINDS: frozenset[str] = frozenset({"bookmark"})


def managed_document_code(source_type: str) -> str | None:
    """The refusal code for a document another surface manages, or None."""
    return MANAGED_DOCUMENT_CODES.get(source_type)


def raise_document_managed(source_type: str) -> NoReturn:
    """409: the document is a projection its owning surface alone may remove."""
    raise BaseAPIException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": MANAGED_DOCUMENT_CODES[source_type]},
        log_event="rag_document_managed",
        source_type=source_type,
    )


def raise_document_not_found(document_id: uuid.UUID) -> NoReturn:
    """Raise 404 when document is not found."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Document not found",
        log_event="rag_document_not_found",
        document_id=str(document_id),
    )


def require_deletable_document(document: RAGDocument) -> None:
    """One source rule for single and exact batch deletion of domain projections."""
    if document.source_type in UNDELETABLE_DOCUMENT_KINDS:
        raise_document_managed(document.source_type)


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


def owned_document_path(actor_id: uuid.UUID, space_id: uuid.UUID, filename: str) -> Path | None:
    """The exact stored path of ``filename`` in the actor's space, or None when it is not that.

    Stricter than :func:`document_file_path`, for the callers that delete, move or
    fingerprint a file: a link on the account, the space or the file is refused
    outright, and so is a filename that resolves outside its space — the two
    ``resolve`` checks are what refuse a Windows junction, which ``is_symlink``
    does not see. A file already gone keeps its exact path: the caller's open says so.
    Every check is a filesystem call — an async caller runs this in a worker thread.

    Args:
        actor_id: The owner of the space.
        space_id: The space holding the document.
        filename: The stored filename, taken literally.

    Returns:
        The path, unresolved, or None when any check refuses it.
    """
    root = Path(settings.rag_spaces_storage_path).resolve()
    account = root / str(actor_id)
    scope = account / str(space_id)
    path = scope / filename
    if account.is_symlink() or scope.is_symlink() or path.is_symlink():
        return None
    if scope.resolve() != scope or path.resolve().parent != scope or path.name != filename:
        return None
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
