"""
RAG Drive Sync service.

Manages Google Drive folder sources linked to RAG Spaces. Handles
listing, downloading/exporting, and processing files through the
existing RAG pipeline.

Phase: evolution — RAG Spaces (Google Drive Integration)
Created: 2026-03-17
"""

from __future__ import annotations

import asyncio
import time
import uuid as uuid_mod
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn
from uuid import UUID

from fastapi import status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    RAG_DRIVE_GOOGLE_EXPORT_MAP,
    RAG_DRIVE_MAX_FILES_PER_SYNC,
    RAG_DRIVE_REGULAR_FILE_MAP,
)
from src.core.exceptions import BaseAPIException
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.rag_spaces.models import (
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
    RAGSpaceRepository,
)
from src.domains.rag_spaces.service import raise_space_not_found
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_drive_sources_total_count,
    rag_drive_sync_duration_seconds,
    rag_drive_sync_files_total,
    rag_drive_sync_runs_total,
)

logger = get_logger(__name__)


# ============================================================================
# Path Safety
# ============================================================================


def _safe_storage_path(base_dir: Path, *segments: str) -> Path:
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


# ============================================================================
# Exception Helpers
# ============================================================================


def _raise_drive_source_not_found(source_id: UUID, space_id: UUID) -> NoReturn:
    """Raise 404 when a Drive source is not found."""
    raise BaseAPIException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Drive source not found",
        log_event="rag_drive_source_not_found",
        source_id=str(source_id),
        space_id=str(space_id),
    )


def _raise_drive_source_limit(max_sources: int) -> NoReturn:
    """Raise 400 when space exceeds max Drive sources limit."""
    raise BaseAPIException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Maximum number of Drive sources per space reached ({max_sources})",
        log_event="rag_drive_source_limit_exceeded",
        max_sources=max_sources,
    )


def _raise_drive_source_duplicate(folder_id: str) -> NoReturn:
    """Raise 409 when Drive folder is already linked to the space."""
    raise BaseAPIException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This Drive folder is already linked to this space",
        log_event="rag_drive_source_duplicate",
        folder_id=folder_id,
    )


class RAGDriveSyncService:
    """Service for managing Google Drive folder sources linked to RAG spaces."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.space_repo = RAGSpaceRepository(db)
        self.doc_repo = RAGDocumentRepository(db)
        self.source_repo = RAGDriveSourceRepository(db)
        self.chunk_repo = RAGChunkRepository(db)

    async def _verify_space_ownership(self, space_id: UUID, user_id: UUID) -> None:
        """Verify space exists and belongs to user, or raise 404."""
        space = await self.space_repo.get_by_id(space_id)
        if not space or space.user_id != user_id:
            raise_space_not_found(space_id)

    async def _get_source_or_404(self, source_id: UUID, space_id: UUID) -> RAGDriveSource:
        """Get a Drive source or raise 404."""
        source = await self.source_repo.get_by_id_and_space(source_id, space_id)
        if not source:
            _raise_drive_source_not_found(source_id, space_id)
        return source

    # ========================================================================
    # Link / Unlink
    # ========================================================================

    async def link_folder(
        self,
        space_id: UUID,
        user_id: UUID,
        folder_id: str,
        folder_name: str,
    ) -> RAGDriveSource:
        """Link a Google Drive folder to a RAG space for sync.

        Args:
            space_id: Target RAG space ID.
            user_id: Owning user ID.
            folder_id: Google Drive folder ID.
            folder_name: Human-readable folder name.

        Returns:
            Created RAGDriveSource record.

        Raises:
            BaseAPIException: On ownership, limit, uniqueness, or connector errors.
        """
        if not settings.rag_spaces_drive_sync_enabled:
            raise BaseAPIException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Drive sync is disabled",
                log_event="rag_drive_sync_disabled",
            )

        await self._verify_space_ownership(space_id, user_id)

        # Check source limit
        source_count = await self.source_repo.count_for_space(space_id)
        if source_count >= settings.rag_drive_max_sources_per_space:
            _raise_drive_source_limit(settings.rag_drive_max_sources_per_space)

        # Check uniqueness
        if await self.source_repo.exists_for_space_and_folder(space_id, folder_id):
            _raise_drive_source_duplicate(folder_id)

        # Verify Google Drive connector is active
        client = await self._get_drive_client(user_id)
        try:
            # Verify folder exists and is actually a folder
            metadata = await client.get_file_metadata(folder_id)
            if "folder" not in metadata.get("mimeType", ""):
                raise BaseAPIException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The specified Drive ID is not a folder",
                    log_event="rag_drive_not_a_folder",
                    folder_id=folder_id,
                )
        finally:
            await client.close()

        # Create source record
        source = await self.source_repo.create(
            {
                "space_id": space_id,
                "user_id": user_id,
                "folder_id": folder_id,
                "folder_name": folder_name,
                "sync_status": RAGDriveSyncStatus.IDLE,
            }
        )
        await self.db.commit()

        rag_drive_sources_total_count.inc()

        logger.info(
            "rag_drive_source_linked",
            source_id=str(source.id),
            space_id=str(space_id),
            folder_id=folder_id,
            folder_name=folder_name,
        )
        return source

    async def unlink_folder(
        self,
        space_id: UUID,
        source_id: UUID,
        user_id: UUID,
        delete_documents: bool = False,
    ) -> None:
        """Unlink a Drive folder from a space.

        Args:
            space_id: Parent RAG space ID.
            source_id: Drive source ID to remove.
            user_id: Owning user ID.
            delete_documents: If True, delete all documents originating from this
                source. If False, documents are kept but unlinked (drive_source_id
                set to NULL).
        """
        await self._verify_space_ownership(space_id, user_id)
        source = await self._get_source_or_404(source_id, space_id)

        if delete_documents:
            docs = await self.doc_repo.get_drive_documents_for_source(source_id)
            for doc in docs:
                # Delete chunks
                await self.chunk_repo.delete_by_document(doc.id)
                # Delete physical file
                file_path = _safe_storage_path(
                    Path(settings.rag_spaces_storage_path),
                    str(user_id),
                    str(space_id),
                    doc.filename,
                )
                if file_path.exists():
                    file_path.unlink()
                # Delete document record
                await self.doc_repo.delete(doc)
        else:
            # Unlink documents from source without deleting them
            await self.db.execute(
                text(
                    "UPDATE rag_documents SET drive_source_id = NULL "
                    "WHERE drive_source_id = :source_id"
                ),
                {"source_id": str(source_id)},
            )

        await self.source_repo.delete(source)
        await self.db.commit()

        rag_drive_sources_total_count.dec()

        logger.info(
            "rag_drive_source_unlinked",
            source_id=str(source_id),
            space_id=str(space_id),
            delete_documents=delete_documents,
        )

    # ========================================================================
    # Status & Lock
    # ========================================================================

    async def get_sync_status(
        self,
        space_id: UUID,
        source_id: UUID,
        user_id: UUID,
    ) -> RAGDriveSource:
        """Get the sync status for a Drive source with ownership verification.

        Args:
            space_id: Parent RAG space ID.
            source_id: Drive source ID.
            user_id: Owning user ID.

        Returns:
            RAGDriveSource instance.

        Raises:
            BaseAPIException: If space or source is not found.
        """
        await self._verify_space_ownership(space_id, user_id)
        return await self._get_source_or_404(source_id, space_id)

    async def try_acquire_sync_lock(self, source_id: UUID) -> bool:
        """Atomically acquire a sync lock on a Drive source.

        Sets sync_status to 'syncing' only if it is not already 'syncing'.

        Args:
            source_id: Drive source ID.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        result = await self.db.execute(
            text(
                "UPDATE rag_drive_sources "
                "SET sync_status = :syncing, error_message = NULL "
                "WHERE id = :id AND sync_status != :syncing"
            ),
            {"syncing": RAGDriveSyncStatus.SYNCING, "id": str(source_id)},
        )
        await self.db.commit()
        return (getattr(result, "rowcount", 0) or 0) > 0

    # ========================================================================
    # Browse
    # ========================================================================

    async def browse_drive_contents(
        self,
        user_id: UUID,
        folder_id: str = "root",
        page_token: str | None = None,
    ) -> dict:
        """Browse contents of a Google Drive folder for the folder picker.

        Returns both folders (navigable) and files (preview only) so the user
        can see what will be synced before selecting a folder.

        Args:
            user_id: Owning user ID.
            folder_id: Parent folder ID (default: "root").
            page_token: Pagination token from a previous response.

        Returns:
            Dict with 'files' list and optional 'nextPageToken'.
        """
        client = await self._get_drive_client(user_id)
        try:
            return await client.list_files(
                folder_id=folder_id,
                content_type=None,
                page_token=page_token,
                max_results=100,
            )
        finally:
            await client.close()

    # ========================================================================
    # Helpers
    # ========================================================================

    async def _get_drive_client(self, user_id: UUID) -> GoogleDriveClient:
        """Get an authenticated Google Drive client for the user.

        Args:
            user_id: User UUID.

        Returns:
            Authenticated GoogleDriveClient.

        Raises:
            BaseAPIException: If Drive connector is not active.
        """
        connector_service = ConnectorService(self.db)
        credentials = await connector_service.get_connector_credentials(
            user_id, ConnectorType.GOOGLE_DRIVE
        )
        if not credentials:
            raise BaseAPIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google Drive connector is not active",
                log_event="rag_drive_connector_not_active",
                user_id=str(user_id),
            )
        return GoogleDriveClient(user_id, credentials, connector_service)


# ============================================================================
# Background Sync
# ============================================================================


async def sync_folder_background(
    space_id: UUID,
    source_id: UUID,
    user_id: UUID,
) -> None:
    """Background coroutine for Drive folder sync.

    Creates its own DB session and drive client. Downloads or exports
    supported files, creates RAGDocument records, and launches document
    processing tasks.

    Args:
        space_id: Target RAG space ID.
        source_id: Drive source to sync.
        user_id: Owning user ID.
    """
    start_time = time.time()
    rag_drive_sync_runs_total.labels(status="started").inc()

    try:
        async with get_db_context() as db:
            source_repo = RAGDriveSourceRepository(db)
            doc_repo = RAGDocumentRepository(db)
            chunk_repo = RAGChunkRepository(db)

            # Get source
            source = await source_repo.get_by_id(source_id)
            if not source:
                logger.warning(
                    "rag_drive_sync_source_not_found",
                    source_id=str(source_id),
                )
                return

            # Get drive client
            connector_service = ConnectorService(db)
            credentials = await connector_service.get_connector_credentials(
                user_id, ConnectorType.GOOGLE_DRIVE
            )
            if not credentials:
                await source_repo.update(
                    source,
                    {
                        "sync_status": RAGDriveSyncStatus.ERROR,
                        "error_message": "Google Drive connector not active",
                    },
                )
                await db.commit()
                rag_drive_sync_runs_total.labels(status="error").inc()
                return

            client = GoogleDriveClient(user_id, credentials, connector_service)
            try:
                # List files with pagination cap
                all_files: list[dict] = []
                page_token: str | None = None
                while len(all_files) < RAG_DRIVE_MAX_FILES_PER_SYNC:
                    try:
                        result = await client.list_files(
                            folder_id=source.folder_id,
                            max_results=min(
                                100,
                                RAG_DRIVE_MAX_FILES_PER_SYNC - len(all_files),
                            ),
                            page_token=page_token,
                            content_type="files_only",
                        )
                    except Exception as e:
                        await source_repo.update(
                            source,
                            {
                                "sync_status": RAGDriveSyncStatus.ERROR,
                                "error_message": f"Folder not accessible: {e}",
                            },
                        )
                        await db.commit()
                        rag_drive_sync_runs_total.labels(status="error").inc()
                        return

                    all_files.extend(result.get("files", []))
                    page_token = result.get("nextPageToken")
                    if not page_token:
                        break

                if len(all_files) >= RAG_DRIVE_MAX_FILES_PER_SYNC:
                    logger.warning(
                        "rag_drive_sync_pagination_cap",
                        source_id=str(source_id),
                        file_count=len(all_files),
                    )

                # Filter supported files
                supported_files = [
                    f
                    for f in all_files
                    if f.get("mimeType", "") in RAG_DRIVE_GOOGLE_EXPORT_MAP
                    or f.get("mimeType", "") in RAG_DRIVE_REGULAR_FILE_MAP
                ]

                # Process each file
                synced = 0
                skipped = 0
                failed = 0
                docs_to_process: list[dict] = []
                seen_file_ids: set[str] = set()

                for drive_file in supported_files:
                    file_id = drive_file["id"]
                    seen_file_ids.add(file_id)
                    mime_type = drive_file.get("mimeType", "")
                    modified_time = drive_file.get("modifiedTime")
                    original_name = drive_file.get("name", "unknown")

                    try:
                        # Check if already synced
                        existing = await doc_repo.get_by_drive_file_id(space_id, file_id)
                        if existing:
                            # Compare modified time
                            if existing.drive_modified_time and modified_time:
                                drive_mod = datetime.fromisoformat(
                                    modified_time.replace("Z", "+00:00")
                                )
                                if existing.drive_modified_time >= drive_mod:
                                    skipped += 1
                                    rag_drive_sync_files_total.labels(result="skipped").inc()
                                    continue
                            # Modified — delete old doc + chunks + file
                            old_file = _safe_storage_path(
                                Path(settings.rag_spaces_storage_path),
                                str(user_id),
                                str(space_id),
                                existing.filename,
                            )
                            if old_file.exists():
                                old_file.unlink()
                            await chunk_repo.delete_by_document(existing.id)
                            await doc_repo.delete(existing)
                            await db.commit()

                        # Check doc limit
                        doc_count = await doc_repo.count_for_space(space_id)
                        if doc_count >= settings.rag_spaces_max_docs_per_space:
                            logger.warning(
                                "rag_drive_sync_doc_limit",
                                space_id=str(space_id),
                            )
                            skipped += 1
                            continue

                        # Download/export content
                        if mime_type in RAG_DRIVE_GOOGLE_EXPORT_MAP:
                            export_mime, ext, stored_type = RAG_DRIVE_GOOGLE_EXPORT_MAP[mime_type]
                            content_bytes = await client.export_google_doc(file_id, export_mime)
                            content_type = stored_type
                        else:
                            stored_type, ext = RAG_DRIVE_REGULAR_FILE_MAP[mime_type]
                            max_bytes = settings.rag_spaces_max_file_size_mb * 1024 * 1024
                            content_bytes = await client.get_file_content(
                                file_id, max_size_bytes=max_bytes
                            )
                            content_type = stored_type

                        if not content_bytes:
                            skipped += 1
                            logger.warning(
                                "rag_drive_sync_empty_content",
                                file_id=file_id,
                                name=original_name,
                            )
                            continue

                        file_size = len(content_bytes)

                        # Write to disk
                        stored_filename = f"{uuid_mod.uuid4().hex}{ext}"
                        base_dir = Path(settings.rag_spaces_storage_path)
                        storage_dir = _safe_storage_path(
                            base_dir,
                            str(user_id),
                            str(space_id),
                        )
                        storage_dir.mkdir(parents=True, exist_ok=True)
                        file_path = _safe_storage_path(
                            base_dir,
                            str(user_id),
                            str(space_id),
                            stored_filename,
                        )
                        file_path.write_bytes(content_bytes)

                        # Parse modified time
                        drive_mod_dt = None
                        if modified_time:
                            drive_mod_dt = datetime.fromisoformat(
                                modified_time.replace("Z", "+00:00")
                            )

                        # Create RAGDocument
                        document = await doc_repo.create(
                            {
                                "space_id": space_id,
                                "user_id": user_id,
                                "filename": stored_filename,
                                "original_filename": original_name,
                                "file_size": file_size,
                                "content_type": content_type,
                                "status": RAGDocumentStatus.PROCESSING,
                                "source_type": RAGDocumentSourceType.DRIVE,
                                "drive_source_id": source_id,
                                "drive_file_id": file_id,
                                "drive_modified_time": drive_mod_dt,
                            }
                        )
                        await db.commit()

                        # Queue for processing
                        docs_to_process.append(
                            {
                                "document_id": document.id,
                                "space_id": space_id,
                                "user_id": user_id,
                                "filename": stored_filename,
                                "original_filename": original_name,
                                "content_type": content_type,
                            }
                        )

                        synced += 1
                        rag_drive_sync_files_total.labels(result="synced").inc()

                    except Exception:
                        failed += 1
                        rag_drive_sync_files_total.labels(result="failed").inc()
                        logger.exception(
                            "rag_drive_sync_file_error",
                            file_id=file_id,
                            name=original_name,
                        )
                        continue

                # Detect and delete removed files
                existing_file_ids = await doc_repo.get_drive_file_ids_for_source(source_id)
                removed_ids = existing_file_ids - seen_file_ids
                for removed_file_id in removed_ids:
                    try:
                        doc = await doc_repo.get_by_drive_file_id(space_id, removed_file_id)
                        if doc and doc.drive_source_id == source_id:
                            old_file = _safe_storage_path(
                                Path(settings.rag_spaces_storage_path),
                                str(user_id),
                                str(space_id),
                                doc.filename,
                            )
                            if old_file.exists():
                                old_file.unlink()
                            await chunk_repo.delete_by_document(doc.id)
                            await doc_repo.delete(doc)
                            await db.commit()
                            rag_drive_sync_files_total.labels(result="deleted").inc()
                    except Exception:
                        logger.exception(
                            "rag_drive_sync_delete_error",
                            file_id=removed_file_id,
                        )

                # Launch processing with throttle
                sem = asyncio.Semaphore(5)

                async def bounded_process(**kwargs: object) -> None:
                    async with sem:
                        await process_document(**kwargs)  # type: ignore[arg-type]

                for doc_args in docs_to_process:
                    safe_fire_and_forget(
                        bounded_process(**doc_args),
                        name=f"rag_drive_{doc_args['document_id']}",
                    )

                # Update source status
                await source_repo.update(
                    source,
                    {
                        "sync_status": RAGDriveSyncStatus.COMPLETED,
                        "last_sync_at": datetime.now(UTC),
                        "file_count": len(supported_files),
                        "synced_file_count": synced,
                        "error_message": None,
                    },
                )
                await db.commit()

                duration = time.time() - start_time
                rag_drive_sync_runs_total.labels(status="completed").inc()
                rag_drive_sync_duration_seconds.observe(duration)

                logger.info(
                    "rag_drive_sync_complete",
                    source_id=str(source_id),
                    synced=synced,
                    skipped=skipped,
                    failed=failed,
                    removed=len(removed_ids),
                    duration=round(duration, 2),
                )
            finally:
                await client.close()

    except Exception as e:
        logger.exception(
            "rag_drive_sync_fatal",
            source_id=str(source_id),
        )
        rag_drive_sync_runs_total.labels(status="error").inc()
        try:
            async with get_db_context() as db:
                source_repo = RAGDriveSourceRepository(db)
                source = await source_repo.get_by_id(source_id)
                if source:
                    await source_repo.update(
                        source,
                        {
                            "sync_status": RAGDriveSyncStatus.ERROR,
                            "error_message": f"Sync failed: {e}",
                        },
                    )
                    await db.commit()
        except Exception:
            logger.exception(
                "rag_drive_sync_error_update_failed",
                source_id=str(source_id),
            )
