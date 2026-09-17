"""Per-file Drive ingestion, shared by the full folder sync and the push reindex.

Extracted from ``drive_sync.py`` (frozen at its audited size) so that ONE
implementation downloads or exports a Drive file, writes it under the
space's storage tree and creates the PENDING ``RAGDocument`` the durable
processing pipeline claims — whether the caller walked a whole folder
(``sync_folder_background``) or received the changed file ids from a push
notification (``reindex_from_push``, ADR-261 P2). Two readings of "how a
Drive file becomes a document" would diverge (ADR-255).

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import status
from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    GOOGLE_DRIVE_FOLDER_MIME,
    RAG_DRIVE_GOOGLE_EXPORT_MAP,
    RAG_DRIVE_REGULAR_FILE_MAP,
)
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentSourceType,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGDriveSyncStatus,
)
from src.domains.rag_spaces.processing import process_document
from src.domains.rag_spaces.repository import (
    RAGChunkRepository,
    RAGDocumentRepository,
    RAGDriveSourceRepository,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_push_channels import rag_drive_push_reindex_total
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

        content_bytes, ext, content_type = await _download(client, file_id, mime_type)
        if not content_bytes:
            logger.warning("rag_drive_sync_empty_content", file_id=file_id, name=original_name)
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
        logger.exception("rag_drive_sync_file_error", file_id=file_id, name=original_name)
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


# ============================================================================
# Push-driven targeted reindex (ADR-261 P2)
# ============================================================================


async def _drain_changes(client: Any, page_token: str) -> tuple[list[dict[str, Any]], str | None]:
    """Every change since ``page_token`` and the new baseline token."""
    changes: list[dict[str, Any]] = []
    token: str | None = page_token
    while token:
        page = await client.list_changes(token)
        changes.extend(page.get("changes", []))
        new_start = page.get("newStartPageToken")
        token = page.get("nextPageToken")
        if not token:
            return changes, str(new_start) if new_start else None
    return changes, None


def routed_folder_ids(source: RAGDriveSource) -> list[str]:
    """The folders a push change is routed on: the walked tree, the root alone before it."""
    walked = list(source.folder_ids or [])
    return walked if source.folder_id in walked else [source.folder_id, *walked]


def _is_folder(file: dict[str, Any]) -> bool:
    return file.get("mimeType") == GOOGLE_DRIVE_FOLDER_MIME


@dataclass(slots=True)
class TouchedSource:
    """One linked tree a drained feed touched, and what it must apply."""

    source: RAGDriveSource
    changes: list[dict[str, Any]]
    #: The routing set after the feed: sub-folders created under the tree
    #: joined it, trashed ones left it. Persisted with the completion.
    folder_ids: list[str]


def _route_folder_change(
    entry: TouchedSource, *, file_id: str, parents: set[str], gone: bool
) -> None:
    """A folder joins the tree when created under it, leaves it when trashed."""
    known = entry.folder_ids
    if gone:
        if file_id in known and file_id != entry.source.folder_id:
            entry.folder_ids = [f for f in known if f != file_id]
        return
    if file_id not in known and parents & set(known):
        entry.folder_ids = [*known, file_id]


@dataclass(frozen=True, slots=True)
class _FeedChange:
    """One entry of the Drive changes feed, read once for every source."""

    file_id: str
    parents: frozenset[str]
    gone: bool
    is_folder: bool
    raw: dict[str, Any]


def _read_change(change: dict[str, Any]) -> _FeedChange:
    """The routing facts of a feed entry: id, parents, removal, kind."""
    file = change.get("file") or {}
    return _FeedChange(
        file_id=str(change.get("fileId") or file.get("id") or ""),
        parents=frozenset(file.get("parents") or []),
        gone=bool(change.get("removed") or file.get("trashed")),
        is_folder=_is_folder(file),
        raw=change,
    )


def _route_change(entry: TouchedSource, change: _FeedChange) -> None:
    """Route one feed entry on a source: a folder moves the set, a file is applied."""
    if change.is_folder or (change.gone and change.file_id in entry.folder_ids):
        _route_folder_change(
            entry, file_id=change.file_id, parents=set(change.parents), gone=change.gone
        )
    elif change.parents & set(entry.folder_ids):
        entry.changes.append(change.raw)


def _touched_sources(
    changes: list[dict[str, Any]], sources: list[RAGDriveSource]
) -> dict[UUID, TouchedSource]:
    """Group the changes by the linked TREE their file sits in.

    A change is routed on its file's parents against each source's walked
    folder set (``routed_folder_ids``). The set grows as the feed is read: a
    folder created under the tree joins it so the files created inside it,
    later in the same feed, route too; a trashed or removed sub-folder leaves
    it (its documents are pruned by the next full synchronisation — Drive
    reports the folder, not each descendant). Only a source whose set changed
    or that has a file change to apply is returned.
    """
    entries: dict[UUID, TouchedSource] = {
        s.id: TouchedSource(s, [], routed_folder_ids(s)) for s in sources
    }
    initial = {s.id: list(routed_folder_ids(s)) for s in sources}
    for change in map(_read_change, changes):
        for entry in entries.values():
            _route_change(entry, change)
    return {
        source_id: entry
        for source_id, entry in entries.items()
        if entry.changes or entry.folder_ids != initial[source_id]
    }


async def _apply_change(
    db: AsyncSession,
    client: Any,
    jobs: Any,
    *,
    source: RAGDriveSource,
    change: dict[str, Any],
    user_id: UUID,
) -> dict[str, Any] | None:
    """One change → a removal, a queued ingestion (its kwargs) or nothing."""
    file = change.get("file") or {}
    file_id = str(change.get("fileId") or file.get("id") or "")
    if not file_id:
        return None
    if change.get("removed") or file.get("trashed"):
        await remove_drive_document(
            db, space_id=source.space_id, source_id=source.id, user_id=user_id, file_id=file_id
        )
        return None
    if not is_supported_drive_file(file):
        return None
    await jobs.heartbeat_source(source.id, settings.rag_job_lease_ttl_seconds)
    result = await ingest_drive_file(
        db, client, space_id=source.space_id, source_id=source.id, user_id=user_id, drive_file=file
    )
    return result.process_kwargs if result.outcome == "queued" else None


async def _reindex_source(
    db: AsyncSession,
    client: Any,
    *,
    touched: TouchedSource,
    user_id: UUID,
) -> str:
    """Apply one source's changes under its sync lock; embed; complete.

    Returns:
        ``reindexed`` | ``locked`` (a sync already holds the source) | ``error``
        (the source is set to ERROR and released — it never stays locked).
    """
    from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
    from src.domains.rag_spaces.jobs_repository import RAGJobsRepository

    source = touched.source
    if not await RAGDriveSyncService(db).try_acquire_sync_lock(source.id):
        return "locked"
    source_repo = RAGDriveSourceRepository(db)
    jobs = RAGJobsRepository(db)
    try:
        queued: list[dict[str, Any]] = []
        for change in touched.changes:
            kwargs = await _apply_change(
                db, client, jobs, source=source, change=change, user_id=user_id
            )
            if kwargs is not None:
                queued.append(kwargs)
        synced, _failed = await process_queued(queued)
        await source_repo.update(
            source,
            {
                "sync_status": RAGDriveSyncStatus.COMPLETED,
                "last_sync_at": datetime.now(UTC),
                "synced_file_count": (source.synced_file_count or 0) + synced,
                # A NEW list: the routing set the feed left behind.
                "folder_ids": list(touched.folder_ids),
                "error_message": None,
                "lease_expires_at": None,
                "worker_id": None,
                "attempts": 0,
                "heartbeat_at": None,
            },
        )
        await db.commit()
        return "reindexed"
    except Exception as exc:  # noqa: BLE001 — the source must not stay locked
        await source_repo.update(
            source,
            {
                "sync_status": RAGDriveSyncStatus.ERROR,
                "error_message": str(exc)[:500],
                "lease_expires_at": None,
                "worker_id": None,
            },
        )
        await db.commit()
        logger.exception("rag_drive_push_reindex_source_failed", source_id=str(source.id))
        return "error"


def _aggregate(outcomes: list[str]) -> str:
    """The sweep's single outcome over the touched sources (work done first)."""
    for outcome in ("reindexed", "error", "locked"):
        if outcome in outcomes:
            return outcome
    return "no_linked_folder"


async def reindex_from_push(user_id: UUID, page_token: str | None) -> str:
    """Turn a Drive change notification into targeted reindexations (ADR-261 P2).

    Drains the changes feed from the channel's token, keeps the changes whose
    file sits under a linked TREE (the folder set the last walk persisted), and — per linked source, under
    the same sync lock the manual sync uses — ingests the changed files and
    removes the trashed ones. The channel's token advances to the new
    baseline only after the feed was drained.

    Args:
        user_id: The channel owner.
        page_token: The changes token stored with the Drive channel.

    Returns:
        A bounded outcome: ``reindexed`` | ``no_linked_folder`` | ``locked``
        | ``error``.
    """
    from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
    from src.domains.connectors.models import ConnectorType
    from src.domains.connectors.service import ConnectorService
    from src.domains.push_channels.models import PushChannelProvider
    from src.domains.push_channels.repository import PushChannelRepository
    from src.domains.push_channels.service import DRIVE_WATCH_TARGET
    from src.domains.rag_spaces.consultations import SECTION_DRIVE, space_read
    from src.infrastructure.database.session import get_db_context

    outcome = "error"
    try:
        async with get_db_context() as db:
            sources = await RAGDriveSourceRepository(db).get_all_for_user(user_id)
            connector_service = ConnectorService(db)
            credentials = (
                await connector_service.get_connector_credentials(
                    user_id, ConnectorType.GOOGLE_DRIVE
                )
                if sources
                else None
            )
            channel = (
                await PushChannelRepository(db).get_for_user(
                    user_id, PushChannelProvider.GOOGLE_DRIVE.value, DRIVE_WATCH_TARGET
                )
                if credentials is not None
                else None
            )
            token = page_token or (channel.page_token if channel is not None else None)
            if not sources or credentials is None or not token:
                outcome = "no_linked_folder"
                return outcome

            client = GoogleDriveClient(user_id, credentials, connector_service)
            try:
                # A Google push can trigger this at four in the morning; before
                # it was recorded, the person had no way to learn their Drive
                # had been opened.
                async with space_read(user_id=user_id, section=SECTION_DRIVE):
                    changes, new_start = await _drain_changes(client, token)
                touched = _touched_sources(changes, sources)
                if channel is not None and new_start:
                    channel.page_token = new_start
                    await db.commit()
                outcomes = [
                    await _reindex_source(db, client, touched=entry, user_id=user_id)
                    for entry in touched.values()
                ]
                outcome = _aggregate(outcomes)
                return outcome
            finally:
                await client.close()
    except Exception:
        logger.exception("rag_drive_push_reindex_failed", user_id=str(user_id))
        outcome = "error"
        return outcome
    finally:
        rag_drive_push_reindex_total.labels(outcome=outcome).inc()
