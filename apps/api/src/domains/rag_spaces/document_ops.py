"""Document operations on a knowledge space (ADR-259): download, archive, move, bulk delete.

A batch reports domain/file refusals per document. A move stages an exclusive
destination under owner/space/document fences BEFORE committing the row and
its chunks; originals remain on uncertain ACK, then cleanup follows known
success. File preparation failure reports ``document_move_failed`` without
moving rows. The archive is built
off the event loop and handed to the router as a temporary file it deletes
after sending.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from fastapi import status

from src.core.config import settings
from src.core.constants import RAG_SPACES_ARCHIVE_MISSING_MEMBER
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.archive_names import archive_name_reservations, unique_archive_name
from src.domains.rag_spaces.document_access import (
    document_file_path,
    managed_document_code,
    owned_document,
    raise_document_not_found,
)
from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.domains.rag_spaces.document_move_files import (
    StagedDocumentFile,
    rollback_staged_file,
    stage_document_file,
)
from src.domains.rag_spaces.models import is_terminal_document_status
from src.domains.rag_spaces.reindex import get_reindex_status
from src.domains.rag_spaces.schemas import (
    RAGBatchSkipped,
    RAGDocumentBatchResponse,
    RAGDocumentMoveRequest,
)
from src.domains.rag_spaces.service import raise_system_space_protected
from src.infrastructure.file_transfer import LocalFileRead
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.rag_spaces.models import RAGDocument, RAGSpace
    from src.domains.rag_spaces.service import RAGSpaceService

logger = get_logger(__name__)

__all__ = [
    "build_archive",
    "bulk_delete_documents",
    "document_file_path",
    "download_document",
    "document_move_refusal",
    "move_documents",
    "relocate_document_rows",
    "owned_document",
    "raise_document_not_found",
]


# ---------------------------------------------------------------------------
# Refusals (stable ``code`` the frontend localizes)
# ---------------------------------------------------------------------------


def raise_document_file_missing(document_id: uuid.UUID) -> NoReturn:
    """404: the row exists but its file is gone from the disk."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "document_file_missing"},
        log_event="rag_document_file_missing",
        document_id=str(document_id),
    )


def raise_archive_too_large(max_mb: int) -> NoReturn:
    """413: the selected files exceed the archive ceiling."""
    raise BaseAPIException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail={"code": "archive_too_large", "max_mb": max_mb},
        log_event="rag_archive_too_large",
        max_mb=max_mb,
    )


def raise_reindex_in_progress() -> NoReturn:
    """409: documents cannot move while the corpus is being re-embedded."""
    raise BaseAPIException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "reindex_in_progress"},
        log_event="rag_move_refused_reindex",
    )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


async def download_document(
    service: RAGSpaceService,
    space_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[Path, RAGDocument]:
    """The stored file of one document, with its row for the download name.

    Raises:
        BaseAPIException: 404 when the row is not the caller's or the file is gone.
    """
    document = await owned_document(service, space_id, document_id, user_id)
    path = document_file_path(document)
    if not await asyncio.to_thread(path.is_file):
        raise_document_file_missing(document_id)
    return path, document


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


def _write_archive(members: list[tuple[str, Path]], missing: list[str]) -> str:
    """Write the zip to a temporary file (blocking: runs in a thread)."""
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    handle.close()
    try:
        with zipfile.ZipFile(handle.name, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, path in members:
                archive.write(path, arcname=name)
            if missing:
                archive.writestr(RAG_SPACES_ARCHIVE_MISSING_MEMBER, "\n".join(missing) + "\n")
    except BaseException:
        # A half-written archive is never handed out — and never left behind.
        with contextlib.suppress(OSError):
            os.remove(handle.name)
        raise
    return handle.name


async def build_archive(
    service: RAGSpaceService,
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    ids: list[uuid.UUID],
) -> tuple[Path, str]:
    """A zip of the selected documents, named after their original filenames.

    Args:
        service: The space service.
        space_id: The space every id must belong to.
        user_id: The caller.
        ids: The documents to include (duplicates ignored).

    Returns:
        The temporary archive path (the caller deletes it) and the download name.

    Raises:
        BaseAPIException: 404 for a foreign document, 413 beyond the size ceiling.
    """
    space = await service.get_space(space_id, user_id)
    documents = [
        await owned_document(service, space_id, doc_id, user_id) for doc_id in dict.fromkeys(ids)
    ]
    max_bytes = settings.rag_spaces_archive_max_mb * 1024 * 1024
    if sum(doc.file_size for doc in documents) > max_bytes:
        raise_archive_too_large(settings.rag_spaces_archive_max_mb)

    members: list[tuple[str, Path]] = []
    missing: list[str] = []
    taken = archive_name_reservations()
    for doc in documents:
        path = document_file_path(doc)
        name = unique_archive_name(doc.original_filename, taken)
        if await asyncio.to_thread(path.is_file):
            members.append((name, path))
        else:
            missing.append(name)

    archive_path = await asyncio.to_thread(_write_archive, members, missing)
    logger.info(
        "rag_archive_built",
        space_id=str(space_id),
        members=len(members),
        missing=len(missing),
    )
    return Path(archive_path), f"{space.name}.zip"


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------


def document_move_refusal(document: RAGDocument, source: RAGSpace, target: RAGSpace) -> str | None:
    """The reason a document cannot move, or None."""
    if document.space_id != source.id or document.user_id != source.user_id:
        return "document_not_found"
    if source.id == target.id:
        return "same_space"
    managed = managed_document_code(document.source_type)
    if managed is not None:
        return managed
    if not is_terminal_document_status(document.status):
        return "document_busy"
    return None


async def relocate_document_rows(
    service: RAGSpaceService, document: RAGDocument, space_id: uuid.UUID, *, commit: bool = True
) -> None:
    """Point a validated document and its chunks at the target in one transaction.

    With commit=False, the caller owns validation/fences, acknowledgment and
    subsequent physical transfer; the original GUI retains its default commit.
    """
    await service.doc_repo.update(document, {"space_id": space_id})
    await service.chunk_repo.move_to_space(document.id, space_id)
    if commit:
        await service.db.commit()


async def _move_one(
    service: RAGSpaceService,
    source: RAGSpace,
    target: RAGSpace,
    document_id: uuid.UUID,
    room_left: int,
) -> str | None:
    """Move one document; None when done, else the skip reason."""
    owner_id = source.user_id
    if owner_id is None:
        return "document_not_found"
    locked = {}
    for space_id in sorted((source.id, target.id)):
        locked[space_id] = await service.get_space(space_id, owner_id, for_update=True)
    source, target = locked[source.id], locked[target.id]
    document = await service.doc_repo.get_by_id(document_id)
    if document is None:
        return "document_not_found"
    await service.db.refresh(document, with_for_update=True)
    refusal = document_move_refusal(document, source, target)
    if refusal is not None:
        return refusal
    current_room = settings.rag_spaces_max_docs_per_space - await service.doc_repo.count_for_space(
        target.id
    )
    if min(room_left, current_room) <= 0:
        return "document_limit_exceeded"
    try:
        staged, digest = await _stage_gui_file(document, target.id, owner_id)
    except OSError as exc:
        logger.warning(
            "rag_document_move_failed",
            document_id=str(document_id),
            target_space_id=str(target.id),
            error_type=type(exc).__name__,
        )
        return "document_move_failed"
    filename, source_id = document.filename, source.id
    committing = False
    try:
        await relocate_document_rows(service, document, target.id, commit=False)
        committing = True
        await service.db.commit()
    except BaseException:
        if not committing:
            await service.db.rollback()
            if staged is not None:
                await rollback_staged_file(staged)
        # Unknown ACK keeps source and prepared destination available.
        raise
    await cleanup_deleted_document_file(owner_id, source_id, filename, digest)
    return None


async def _stage_gui_file(
    document: RAGDocument, target_id: uuid.UUID, owner_id: uuid.UUID
) -> tuple[StagedDocumentFile | None, str | None]:
    try:
        reader = LocalFileRead.open(document_file_path(document))
    except FileNotFoundError:
        digest = None
    else:
        try:
            digest = reader.identity_digest
        finally:
            await reader.close()
    staged = await stage_document_file(
        owner_id,
        document.space_id,
        target_id,
        document.filename,
        digest,
        document.file_size,
    )
    return staged, digest


async def move_documents(
    service: RAGSpaceService,
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    request: RAGDocumentMoveRequest,
) -> RAGDocumentBatchResponse:
    """Move uploaded documents to another space of the same user.

    Refused wholesale while a reindex runs (a moved row would be re-embedded
    under the wrong space) and when the target is a system space; every other
    obstacle is reported per document.

    Args:
        service: The space service.
        space_id: The source space.
        user_id: The caller.
        request: The ids and the target space.

    Returns:
        The moved ids and the skipped ones with their reasons.
    """
    if (await get_reindex_status()).get("in_progress"):
        raise_reindex_in_progress()
    source = await service.get_space(space_id, user_id)
    target = await service.get_space(request.target_space_id, user_id)
    if target.is_system:
        raise_system_space_protected(target.id, "move")

    room = settings.rag_spaces_max_docs_per_space - await service.doc_repo.count_for_space(
        target.id
    )
    done: list[uuid.UUID] = []
    skipped: list[RAGBatchSkipped] = []
    for document_id in dict.fromkeys(request.ids):
        code = await _move_one(service, source, target, document_id, room - len(done))
        if code is None:
            done.append(document_id)
        else:
            skipped.append(RAGBatchSkipped(id=document_id, code=code))
    logger.info(
        "rag_documents_moved",
        source_space_id=str(space_id),
        target_space_id=str(target.id),
        moved=len(done),
        skipped=len(skipped),
    )
    return RAGDocumentBatchResponse(done=done, skipped=skipped)


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------


def _skip_code(exc: BaseAPIException) -> str:
    """The stable reason a refusal carries — its own ``code`` when it names one."""
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        return str(detail["code"])
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        return "document_not_found"
    return "delete_failed"


async def bulk_delete_documents(
    service: RAGSpaceService,
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    ids: list[uuid.UUID],
) -> RAGDocumentBatchResponse:
    """Delete several documents, reporting each id.

    Args:
        service: The space service.
        space_id: The space every id must belong to.
        user_id: The caller.
        ids: The documents to delete (duplicates ignored).

    Returns:
        The deleted ids and the skipped ones with their reasons.
    """
    done: list[uuid.UUID] = []
    skipped: list[RAGBatchSkipped] = []
    for document_id in dict.fromkeys(ids):
        try:
            await service.delete_document(space_id, document_id, user_id)
        except BaseAPIException as exc:
            skipped.append(RAGBatchSkipped(id=document_id, code=_skip_code(exc)))
        except Exception as exc:  # noqa: BLE001 - reported per document, never raised for the batch
            logger.warning(
                "rag_document_bulk_delete_failed", document_id=str(document_id), error=str(exc)
            )
            skipped.append(RAGBatchSkipped(id=document_id, code="delete_failed"))
        else:
            done.append(document_id)
    return RAGDocumentBatchResponse(done=done, skipped=skipped)
