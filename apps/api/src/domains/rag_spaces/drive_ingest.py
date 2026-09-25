"""Per-file Drive ingestion, shared by the full folder sync and the push reindex.

Extracted from ``drive_sync.py`` (frozen at its audited size) so that ONE
implementation downloads or exports a Drive file, writes it under the
space's storage tree and creates the PENDING ``RAGDocument`` the durable
processing pipeline claims — whether the caller walked a whole folder
(``sync_folder_background``) or received the changed file ids from a push
notification (``drive_push.reindex_from_push``, ADR-261 P2). Two readings of
"how a Drive file becomes a document" would diverge (ADR-255).

A download is a network call and never runs inside a transaction: the reads
that decide it end first (ADR-304 — a pooled connection held while Google
answers is the ``idle in transaction`` measured in production).

The two source-agnostic steps — storing bytes as a PENDING document
(``create_pending_document``) and discarding a synced document with its file
and chunks (``discard_document``) — are shared with the mail source
(``mail_sync.py``, ADR-262). Deletion of a Drive document keeps its single
implementation (``remove_drive_document``).
"""

from __future__ import annotations

import asyncio
import uuid as uuid_mod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import status
from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    RAG_DRIVE_GOOGLE_EXPORT_MAP,
    RAG_DRIVE_REGULAR_FILE_MAP,
)
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentSourceType,
    RAGDocumentStatus,
)
from src.domains.rag_spaces.processing import process_document
from src.domains.rag_spaces.repository import (
    RAGChunkRepository,
    RAGDocumentRepository,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import rag_drive_sync_files_total

logger = get_logger(__name__)

_PROCESS_CONCURRENCY = 5


def safe_storage_path(base_dir: Path, *segments: str) -> Path:
    """Build a storage path and verify it stays within the base directory.

    Prevents path-traversal attacks when segments originate from the database.

    Args:
        base_dir: Trusted root directory (e.g. ``/app/data/rag_uploads``).
        *segments: Untrusted path components (user_id, space_id, filename).

    Returns:
        Resolved absolute path guaranteed to be under *base_dir*.

    Raises:
        BaseAPIException: If the resolved path escapes *base_dir*.
    """
    target = (base_dir / Path(*segments)).resolve()
    if not target.is_relative_to(base_dir.resolve()):
        logger.error(
            "rag_path_traversal_blocked",
            base_dir=str(base_dir),
            segments=segments,
        )
        raise BaseAPIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
            log_event="rag_path_traversal_blocked",
        )
    return target


def is_supported_drive_file(drive_file: dict[str, Any]) -> bool:
    """Whether the pipeline knows how to read this MIME type."""
    mime_type = drive_file.get("mimeType", "")
    return mime_type in RAG_DRIVE_GOOGLE_EXPORT_MAP or mime_type in RAG_DRIVE_REGULAR_FILE_MAP


def is_unchanged(existing: RAGDocument, drive_file: dict[str, Any]) -> bool:
    """Whether a synced document is still current for its Drive file.

    ONE predicate, read by the ingest (skip) and by the preflight (count):
    current when both stamps exist and the stored one is not older. A missing
    stamp on either side reads as changed — re-downloading is the safe side.
    """
    drive_mod_dt = parse_rfc3339(drive_file.get("modifiedTime"))
    return (
        existing.drive_modified_time is not None
        and drive_mod_dt is not None
        and existing.drive_modified_time >= drive_mod_dt
    )


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of one file: ``queued`` carries the ``process_document`` kwargs.

    Attributes:
        outcome: ``queued`` | ``skipped`` (unchanged, limit, empty) | ``failed``.
        process_kwargs: The arguments the processing pipeline needs, when queued.
    """

    outcome: str
    process_kwargs: dict[str, Any] | None = None


# ============================================================================
# Source-agnostic document steps (Drive files, mail threads)
# ============================================================================


def _storage_path(user_id: UUID, space_id: UUID, filename: str) -> Path:
    return safe_storage_path(
        Path(settings.rag_spaces_storage_path), str(user_id), str(space_id), filename
    )


def _unlink_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _write_stored_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def parse_rfc3339(value: str | None) -> datetime | None:
    """A Google ``modifiedTime``/``updated`` stamp as an aware datetime (or None)."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def discard_document(
    db: AsyncSession, document: RAGDocument, *, user_id: UUID, space_id: UUID
) -> None:
    """Delete a synced document: its stored file, its chunks and its row (committed).

    Disk I/O runs off the event loop; the row and chunks go in one commit.
    """
    await asyncio.to_thread(_unlink_if_exists, _storage_path(user_id, space_id, document.filename))
    await RAGChunkRepository(db).delete_by_document(document.id)
    await RAGDocumentRepository(db).delete(document)
    await db.commit()


async def create_pending_document(
    db: AsyncSession,
    *,
    space_id: UUID,
    user_id: UUID,
    content: bytes,
    extension: str,
    original_name: str,
    content_type: str,
    source_fields: dict[str, Any],
) -> dict[str, Any]:
    """Store ``content`` under the space's tree and create its PENDING document.

    Shared by every synced source: the stored filename is a UUID
    (anti-traversal), the row is PENDING so the durable pipeline claims it
    atomically (audit F001) — this never embeds — and the returned kwargs are
    exactly what ``process_document`` needs.

    Args:
        db: Caller-owned session (committed here).
        space_id: Target space.
        user_id: Owner.
        content: The bytes to store.
        extension: Stored-file extension, dot included (``.md``, ``.pdf``).
        original_name: Display name (never used on disk).
        content_type: MIME type the extractor will read.
        source_fields: Provenance columns (``source_type``, the source id and
            the remote identifiers).

    Returns:
        The ``process_document`` kwargs for the created document.
    """
    stored_filename = f"{uuid_mod.uuid4().hex}{extension}"
    file_path = _storage_path(user_id, space_id, stored_filename)
    await asyncio.to_thread(_write_stored_file, file_path, content)
    document = await RAGDocumentRepository(db).create(
        {
            "space_id": space_id,
            "user_id": user_id,
            "filename": stored_filename,
            "original_filename": original_name,
            "file_size": len(content),
            "content_type": content_type,
            "status": RAGDocumentStatus.PENDING,
            **source_fields,
        }
    )
    await db.commit()
    return {
        "document_id": document.id,
        "space_id": space_id,
        "user_id": user_id,
        "filename": stored_filename,
        "original_filename": original_name,
        "content_type": content_type,
    }


async def process_queued(
    process_kwargs: list[dict[str, Any]], *, counter: Counter = rag_drive_sync_files_total
) -> tuple[int, int]:
    """Embed the queued documents (bounded concurrency); returns (synced, failed).

    ``counter`` is the source's per-item metric (``result`` label): Drive files
    by default, mail threads for the label source (ADR-262).
    """
    sem = asyncio.Semaphore(_PROCESS_CONCURRENCY)

    async def bounded(**kwargs: object) -> bool:
        async with sem:
            return await process_document(**kwargs)  # type: ignore[arg-type]

    results = await asyncio.gather(
        *(bounded(**kwargs) for kwargs in process_kwargs), return_exceptions=True
    )
    synced = sum(1 for r in results if r is True)
    for index, result in enumerate(results):
        if result is True:
            counter.labels(result="synced").inc()
        else:
            counter.labels(result="failed").inc()
            logger.error(
                "rag_drive_document_processing_failed",
                document_id=str(process_kwargs[index]["document_id"]),
                error=str(result),
            )
    return synced, len(results) - synced


# ============================================================================
# Drive files
# ============================================================================


async def _download(client: Any, file_id: str, mime_type: str) -> tuple[bytes, str, str]:
    """Export a Google-native file or download a regular one: (bytes, ext, type)."""
    if mime_type in RAG_DRIVE_GOOGLE_EXPORT_MAP:
        export_mime, ext, stored_type = RAG_DRIVE_GOOGLE_EXPORT_MAP[mime_type]
        return await client.export_google_doc(file_id, export_mime), ext, stored_type
    stored_type, ext = RAG_DRIVE_REGULAR_FILE_MAP[mime_type]
    max_bytes = settings.rag_spaces_max_file_size_mb * 1024 * 1024
    content = await client.get_file_content(file_id, max_size_bytes=max_bytes)
    return content, ext, stored_type


async def ingest_drive_file(
    db: AsyncSession,
    client: Any,
    *,
    space_id: UUID,
    source_id: UUID,
    user_id: UUID,
    drive_file: dict[str, Any],
) -> IngestResult:
    """Download or export one Drive file and create its PENDING document.

    Unchanged files (same ``modifiedTime``) are skipped; a modified file
    replaces its previous document, chunks and stored file. The document is
    created PENDING so the durable pipeline claims it atomically (audit
    F001) — this function never embeds.

    Args:
        db: Caller-owned session (committed here after each durable step).
        client: A GoogleDriveClient bound to the user.
        space_id: Target space.
        source_id: The linked folder source.
        user_id: Owner.
        drive_file: The Drive file resource (``id``, ``name``, ``mimeType``,
            ``modifiedTime``).

    Returns:
        The outcome; a failure is logged with its exception and never raises.
    """
    doc_repo = RAGDocumentRepository(db)
    file_id = str(drive_file["id"])
    mime_type = drive_file.get("mimeType", "")
    original_name = drive_file.get("name", "unknown")
    drive_mod_dt = parse_rfc3339(drive_file.get("modifiedTime"))
    try:
        existing = await doc_repo.get_by_drive_file_id(space_id, file_id)
        if existing is not None:
            if is_unchanged(existing, drive_file):
                rag_drive_sync_files_total.labels(result="skipped").inc()
                return IngestResult("skipped")
            await discard_document(db, existing, user_id=user_id, space_id=space_id)

        if await doc_repo.count_for_space(space_id) >= settings.rag_spaces_max_docs_per_space:
            logger.warning("rag_drive_sync_doc_limit", space_id=str(space_id))
            return IngestResult("skipped")

        # The reads above decided; end their transaction before the network
        # call, so no pooled connection waits on Google (ADR-304).
        await db.commit()
        content_bytes, ext, content_type = await _download(client, file_id, mime_type)
        if not content_bytes:
            logger.warning("rag_drive_sync_empty_content", file_id=file_id)
            return IngestResult("skipped")

        kwargs = await create_pending_document(
            db,
            space_id=space_id,
            user_id=user_id,
            content=content_bytes,
            extension=ext,
            original_name=original_name,
            content_type=content_type,
            source_fields={
                "source_type": RAGDocumentSourceType.DRIVE,
                "drive_source_id": source_id,
                "drive_file_id": file_id,
                "drive_modified_time": drive_mod_dt,
            },
        )
        return IngestResult("queued", kwargs)
    except Exception:
        rag_drive_sync_files_total.labels(result="failed").inc()
        logger.exception("rag_drive_sync_file_error", file_id=file_id)
        return IngestResult("failed")


async def remove_drive_document(
    db: AsyncSession,
    *,
    space_id: UUID,
    source_id: UUID,
    user_id: UUID,
    file_id: str,
) -> bool:
    """Delete the document (chunks, stored file) a Drive file produced, if any.

    Returns:
        True when a document was removed.
    """
    try:
        doc = await RAGDocumentRepository(db).get_by_drive_file_id(space_id, file_id)
        if not doc or doc.drive_source_id != source_id:
            return False
        await discard_document(db, doc, user_id=user_id, space_id=space_id)
        rag_drive_sync_files_total.labels(result="deleted").inc()
        return True
    except Exception:
        logger.exception("rag_drive_sync_delete_error", file_id=file_id)
        return False
