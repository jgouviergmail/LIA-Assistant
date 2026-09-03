"""Document operations on a knowledge space (ADR-259): download, archive, move, bulk delete.

A batch never fails as a whole for one document: every id is reported as done
or skipped with a stable reason. A move commits the row and its chunks BEFORE
touching the disk, then moves the file; a rename that fails reverts both and
reports ``document_move_failed`` for that document only. The archive is built
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
from src.domains.rag_spaces.document_access import (
    document_file_path,
    owned_document,
    raise_document_not_found,
)
from src.domains.rag_spaces.models import (
    RAGDocumentSourceType,
    is_terminal_document_status,
)
from src.domains.rag_spaces.reindex import get_reindex_status
from src.domains.rag_spaces.schemas import (
    RAGBatchSkipped,
    RAGDocumentBatchResponse,
    RAGDocumentMoveRequest,
)
from src.domains.rag_spaces.service import raise_system_space_protected
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
    "move_documents",
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


def _unique_member_name(original: str, taken: set[str]) -> str:
    """``report.pdf`` → ``report (2).pdf`` while the name is already a member."""
    if original not in taken:
        taken.add(original)
        return original
    stem, suffix = os.path.splitext(original)
    counter = 2
    while f"{stem} ({counter}){suffix}" in taken:
        counter += 1
    name = f"{stem} ({counter}){suffix}"
    taken.add(name)
    return name


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
    taken: set[str] = set()
    for doc in documents:
        path = document_file_path(doc)
        if await asyncio.to_thread(path.is_file):
            members.append((_unique_member_name(doc.original_filename, taken), path))
        else:
            missing.append(doc.original_filename)

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


def _move_refusal(document: RAGDocument, source: RAGSpace, target: RAGSpace) -> str | None:
    """The reason a document cannot move, or None."""
    if document.space_id != source.id or document.user_id != source.user_id:
        return "document_not_found"
    if source.id == target.id:
        return "same_space"
    if document.source_type == RAGDocumentSourceType.DRIVE:
        return "document_managed_by_drive"
    if document.source_type == RAGDocumentSourceType.MEETING:
        return "document_managed_by_meetings"
    if not is_terminal_document_status(document.status):
        return "document_busy"
    return None


def _rename(old_path: Path, new_path: Path) -> None:
    """Move the file into the target space directory (blocking: runs in a thread).

    A file already gone from the disk is not an obstacle: the index is what
    retrieval reads, the file only serves downloads — the row moves, and the
    download will say ``document_file_missing`` as it did before the move.
    """
    if not old_path.is_file():
        logger.warning("rag_document_file_missing_on_move", path=old_path.name)
        return
    new_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(old_path, new_path)


async def _relocate(service: RAGSpaceService, document: RAGDocument, space_id: uuid.UUID) -> None:
    """Point the row and its chunks at ``space_id`` and commit."""
    await service.doc_repo.update(document, {"space_id": space_id})
    await service.chunk_repo.move_to_space(document.id, space_id)
    await service.db.commit()


async def _move_one(
    service: RAGSpaceService,
    source: RAGSpace,
    target: RAGSpace,
    document_id: uuid.UUID,
    room_left: int,
) -> str | None:
    """Move one document; None when done, else the skip reason."""
    document = await service.doc_repo.get_by_id(document_id)
    if document is None:
        return "document_not_found"
    refusal = _move_refusal(document, source, target)
    if refusal is not None:
        return refusal
    if room_left <= 0:
        return "document_limit_exceeded"

    old_path = document_file_path(document)
    await _relocate(service, document, target.id)
    new_path = document_file_path(document)
    try:
        await asyncio.to_thread(_rename, old_path, new_path)
    except OSError as exc:
        # The row already points at the target: put it back so the file and
        # the row agree, then report — the batch goes on.
        logger.warning(
            "rag_document_move_failed",
            document_id=str(document_id),
            target_space_id=str(target.id),
            error=str(exc),
        )
        await _relocate(service, document, source.id)
        return "document_move_failed"
    return None


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
            code = (
                "document_not_found"
                if exc.status_code == status.HTTP_404_NOT_FOUND
                else "delete_failed"
            )
            skipped.append(RAGBatchSkipped(id=document_id, code=code))
        except Exception as exc:  # noqa: BLE001 - reported per document, never raised for the batch
            logger.warning(
                "rag_document_bulk_delete_failed", document_id=str(document_id), error=str(exc)
            )
            skipped.append(RAGBatchSkipped(id=document_id, code="delete_failed"))
        else:
            done.append(document_id)
    return RAGDocumentBatchResponse(done=done, skipped=skipped)
