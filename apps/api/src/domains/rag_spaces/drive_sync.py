"""
RAG Drive Sync service.

Manages Google Drive folder sources linked to RAG Spaces. Handles
listing, downloading/exporting, and processing files through the
existing RAG pipeline.

Phase: evolution — RAG Spaces (Google Drive Integration)
Created: 2026-03-17
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NoReturn
from uuid import UUID

from fastapi import status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    RAG_DRIVE_MAX_ANCESTOR_DEPTH,
    RAG_DRIVE_MAX_FILES_PER_SYNC,
    RAG_DRIVE_MAX_FOLDERS_PER_WALK,
)
from src.core.exceptions import BaseAPIException
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.rag_spaces.consultations import SECTION_DRIVE, space_read
from src.domains.rag_spaces.drive_ingest import (
    ingest_drive_file,
    is_supported_drive_file,
    is_unchanged,
    process_queued,
    remove_drive_document,
)
from src.domains.rag_spaces.drive_ingest import (
    safe_storage_path as _safe_storage_path,
)
from src.domains.rag_spaces.drive_sync_outcome import sync_result_values
from src.domains.rag_spaces.drive_walk import DriveWalkError, walk_drive_tree
from src.domains.rag_spaces.jobs_repository import RAGJobsRepository, validate_source_worker_id
from src.domains.rag_spaces.models import (
    RAGDriveSource,
    RAGDriveSyncStatus,
)
from src.domains.rag_spaces.native_job_abandonment import record_source_failure
from src.domains.rag_spaces.processing import process_document
from src.domains.rag_spaces.repository import (
    RAGChunkRepository,
    RAGDocumentRepository,
    RAGDriveSourceRepository,
    RAGSpaceRepository,
)
from src.domains.rag_spaces.service import raise_space_not_found
from src.domains.rag_spaces.source_link_observation import (
    DriveLinkRoot,
    SourceLinkObservation,
    linked_drive_roots,
    observed_source_name,
)
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    current_source_worker,
    native_source_limit,
    require_source_worker,
)
from src.domains.rag_spaces.source_worker_runtime import source_worker_external
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_drive_sources_total_count,
    rag_drive_sync_duration_seconds,
    rag_drive_sync_runs_total,
)
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_drive_sync_files_total as rag_drive_sync_files_total,
)

logger = get_logger(__name__)

# Per-process worker identity for the durable sync lease (audit F001).
_DRIVE_WORKER_ID = f"rag-sync-{os.getpid()}"


# ============================================================================
# Path Safety
# ============================================================================


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


#: The stable code the frontend translates when a folder sits inside — or
#: above — a tree already linked to the same space (ADR-184: a refusal names
#: itself).
DRIVE_FOLDER_NESTED_CODE = "drive_folder_nested"


def _raise_drive_folder_nested(folder_id: str, other_folder_id: str) -> NoReturn:
    """409: the folder and a linked one share a tree, so files would be indexed twice."""
    raise BaseAPIException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": DRIVE_FOLDER_NESTED_CODE},
        log_event="rag_drive_folder_nested",
        folder_id=folder_id,
        other_folder_id=other_folder_id,
    )


async def ancestor_ids(client: GoogleDriveClient, folder_id: str) -> list[str]:
    """The parent chain of a folder, nearest first, bounded in depth.

    Drive files have ONE parent today (legacy multi-parent items keep the
    first); the chain ends at the root, which has none.
    """
    chain: list[str] = []
    current = folder_id
    seen: set[str] = {folder_id}
    while len(chain) < RAG_DRIVE_MAX_ANCESTOR_DEPTH:
        metadata = await client.get_file_metadata(current, fields=["id", "parents"])
        parents = [str(p) for p in metadata.get("parents") or []]
        if not parents or parents[0] in seen:
            break
        current = parents[0]
        seen.add(current)
        chain.append(current)
    return chain


@dataclass(frozen=True, slots=True)
class DrivePreflight:
    """What one synchronisation would do to the linked tree, counted exactly.

    Every figure is computed by the code the synchronisation runs — the same
    walk, the same ``is_unchanged`` and ``is_supported_drive_file`` — under
    the space's document cap, and the walk's bounds travel with them: a cut
    walk (``truncated``) makes every count a floor.
    """

    total_files: int
    unsupported: int
    unchanged: int
    modified: int
    new: int
    #: New files the space has no room for (``rag_spaces_max_docs_per_space``).
    over_capacity: int
    #: ``modified + new`` within capacity — the files a synchronisation writes.
    to_index: int
    folders: int
    unreadable_folders: int
    truncated: bool
    #: Published bounds and threshold (ADR-184: what is enforced is read).
    threshold: int
    max_files: int
    max_folders: int
    requires_confirmation: bool


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
        *,
        observation: SourceLinkObservation | None = None,
        commit: bool = True,
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
        if not commit and observation is None:
            raise ValueError("Deferred source linking requires prior provider inspection")
        if observation is None:
            observation = await self.prepare_folder_link(
                space_id, user_id, folder_id, fallback_name=folder_name
            )
            # The existing Drive GUI owns its chosen display name.
            observation = replace(observation, name=folder_name)
        observation.require_scope("drive", space_id, user_id, folder_id, folder_name)
        if await self.space_repo.get_by_id_for_owner_update(space_id, user_id) is None:
            raise_space_not_found(space_id)
        await self._folder_link_constraints(space_id, user_id, folder_id)
        if (
            linked_drive_roots(await self.source_repo.get_all_for_space(space_id))
            != observation.roots
        ):
            raise ValueError("Linked Drive roots changed after provider inspection")
        source = await self.source_repo.create(
            {
                "space_id": space_id,
                "user_id": user_id,
                "folder_id": folder_id,
                "folder_name": folder_name,
                "sync_status": RAGDriveSyncStatus.IDLE,
            }
        )
        if not commit:
            await self.db.flush()
            return source
        await self.db.commit()
        rag_drive_sources_total_count.inc()
        logger.info(
            "rag_drive_source_linked",
            source_id=str(source.id),
            space_id=str(space_id),
            folder_id=folder_id,
        )
        return source

    async def _folder_link_constraints(self, space_id: UUID, user_id: UUID, folder_id: str) -> None:
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

    async def prepare_folder_link(
        self, space_id: UUID, user_id: UUID, folder_id: str, *, fallback_name: str | None = None
    ) -> SourceLinkObservation:
        """Inspect an owned candidate and the existing trees without writing a source."""
        await self._folder_link_constraints(space_id, user_id, folder_id)
        roots = linked_drive_roots(await self.source_repo.get_all_for_space(space_id))
        client = await self._get_drive_client(user_id)
        try:
            await self.db.commit()  # The whole provider traversal uses detached read snapshots.
            # ONE read of the Drive for the act — the verdicts come AFTER the
            # block, so a refusal of OUR rules never files as a Drive that
            # refused (« failed » is the source's word, not ours).
            async with space_read(user_id=user_id, section=SECTION_DRIVE):
                metadata = await client.get_file_metadata(folder_id)
                nested_in = (
                    await self._nested_folder_conflict(client, space_id, folder_id, roots=roots)
                    if "folder" in metadata.get("mimeType", "")
                    else None
                )
        finally:
            await client.close()
        if "folder" not in metadata.get("mimeType", ""):
            raise BaseAPIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The specified Drive ID is not a folder",
                log_event="rag_drive_not_a_folder",
                folder_id=folder_id,
            )
        # A source is a TREE: a folder inside a linked one, or above one, would
        # have its files indexed by two sources at once — each synchronisation
        # discarding the other's document.
        if nested_in is not None:
            _raise_drive_folder_nested(folder_id, nested_in)

        return SourceLinkObservation(
            "drive",
            space_id,
            user_id,
            folder_id,
            observed_source_name(metadata, folder_id, fallback_name),
            roots,
        )

    async def _nested_folder_conflict(
        self,
        client: GoogleDriveClient,
        space_id: UUID,
        folder_id: str,
        *,
        roots: tuple[DriveLinkRoot, ...] | None = None,
    ) -> str | None:
        """The linked root ``folder_id`` shares a tree with, or None.

        Two readings, both needed: the candidate's ancestors against every
        linked root (candidate INSIDE a tree), and each linked root's ancestors
        — plus its last walked folder set — against the candidate (candidate
        ABOVE a tree). Reads only; the caller raises, outside the recorded read.
        """
        others = (
            roots
            if roots is not None
            else linked_drive_roots(await self.source_repo.get_all_for_space(space_id))
        )
        if not others:
            return None
        candidate_ancestors = set(await ancestor_ids(client, folder_id))
        for other in others:
            if other.folder_id in candidate_ancestors or folder_id in (other.folder_ids or []):
                return str(other.folder_id)
            if folder_id in set(await ancestor_ids(client, other.folder_id)):
                return str(other.folder_id)
        return None

    async def unlink_folder(
        self,
        space_id: UUID,
        source_id: UUID,
        user_id: UUID,
        delete_documents: bool = False,
        *,
        commit: bool = True,
    ) -> None:
        """Unlink a Drive folder from a space.

        Args:
            space_id: Parent RAG space ID.
            source_id: Drive source ID to remove.
            user_id: Owning user ID.
            delete_documents: If True, delete all documents originating from this
                source. If False, documents are kept but unlinked (drive_source_id
                set to NULL).
            commit: False leaves a retain-only unlink in the caller's transaction.
        """
        if not commit and delete_documents:
            raise ValueError("Deferred source unlink must retain documents")
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
        if not commit:
            await self.db.flush()
            return
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

    async def try_acquire_sync_lock(
        self, source_id: UUID, *, commit: bool = True, worker_id: str | None = None
    ) -> bool:
        """Atomically acquire a sync lock on a Drive source.

        Sets sync_status to 'syncing' only if it is not already 'syncing'.

        Args:
            source_id: Drive source ID.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        if not commit and worker_id is None:
            raise ValueError("Deferred source claims require a unique caller worker identity")
        owner = worker_id if worker_id is not None else _DRIVE_WORKER_ID
        validate_source_worker_id(owner)
        clock = "clock_timestamp()" if worker_id is not None else "now()"
        result = await self.db.execute(
            text(
                "UPDATE rag_drive_sources "
                "SET sync_status = :syncing, error_message = NULL, "
                # Durable-job lease (audit F001): a live sync holds it via the
                # heartbeat; a crash frees it for the reaper within the TTL. This
                # is the USER-initiated path (the reaper re-leases via
                # reclaim_or_fail_source instead), so each acquisition is a FRESH
                # run — attempts is set to 1, not incremented, so manual re-syncs
                # never consume the crash-recovery retry budget.
                f"lease_expires_at = {clock} + (:ttl * interval '1 second'), "
                f"heartbeat_at = {clock}, attempts = 1, worker_id = :wid "
                "WHERE id = :id AND sync_status != :syncing"
            ),
            {
                "syncing": RAGDriveSyncStatus.SYNCING,
                "id": str(source_id),
                "ttl": settings.rag_job_lease_ttl_seconds,
                "wid": owner,
            },
        )
        if commit:
            await self.db.commit()
        return (getattr(result, "rowcount", 0) or 0) > 0

    # ========================================================================
    # Browse
    # ========================================================================

    async def preflight(self, space_id: UUID, source_id: UUID, user_id: UUID) -> DrivePreflight:
        """Count what a synchronisation of ``source_id`` would index, exactly.

        Walks the tree as the synchronisation does and classifies each file
        with the ingest's own predicates. Read-only: nothing is downloaded,
        nothing is written. The read of the person's Drive is recorded.

        Args:
            space_id: The space the source belongs to.
            source_id: The linked folder.
            user_id: The caller.

        Returns:
            The figures, the bounds and whether the threshold asks for a
            confirmation.

        Raises:
            BaseAPIException: Ownership, a missing source, or an unreadable root.
        """
        await self._verify_space_ownership(space_id, user_id)
        source = await self._get_source_or_404(source_id, space_id)
        folder_id = source.folder_id
        client = await self._get_drive_client(user_id)
        try:
            await self.db.commit()  # Ownership, source and credential reads end before walking.
            async with space_read(user_id=user_id, section=SECTION_DRIVE):
                try:
                    tree = await walk_drive_tree(
                        client,
                        folder_id,
                        max_files=RAG_DRIVE_MAX_FILES_PER_SYNC,
                        max_folders=RAG_DRIVE_MAX_FOLDERS_PER_WALK,
                    )
                except DriveWalkError as exc:
                    raise BaseAPIException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=str(exc),
                        log_event="rag_drive_preflight_root_unreadable",
                        source_id=str(source_id),
                    ) from exc
        finally:
            await client.close()

        capacity = max(
            0,
            settings.rag_spaces_max_docs_per_space - await self.doc_repo.count_for_space(space_id),
        )
        unsupported = unchanged = modified = new = 0
        existing_by_id = await self.doc_repo.get_by_drive_file_ids(
            space_id, [str(file["id"]) for file in tree.files if is_supported_drive_file(file)]
        )
        for drive_file in tree.files:
            if not is_supported_drive_file(drive_file):
                unsupported += 1
                continue
            existing = existing_by_id.get(str(drive_file["id"]))
            if existing is None:
                new += 1
            elif is_unchanged(existing, drive_file):
                unchanged += 1
            else:
                modified += 1
        new_within_capacity = min(new, capacity)
        to_index = modified + new_within_capacity
        threshold = settings.rag_drive_sync_confirm_threshold
        return DrivePreflight(
            total_files=len(tree.files),
            unsupported=unsupported,
            unchanged=unchanged,
            modified=modified,
            new=new,
            over_capacity=new - new_within_capacity,
            to_index=to_index,
            folders=len(tree.folder_ids),
            unreadable_folders=tree.unreadable_folders,
            truncated=tree.truncated,
            threshold=threshold,
            max_files=RAG_DRIVE_MAX_FILES_PER_SYNC,
            max_folders=RAG_DRIVE_MAX_FOLDERS_PER_WALK,
            requires_confirmation=to_index > threshold,
        )

    async def browse_drive_contents(
        self,
        user_id: UUID,
        folder_id: str = "root",
        page_token: str | None = None,
        *,
        max_results: int = 100,
    ) -> dict:
        """Browse contents of a Google Drive folder for the folder picker.

        Returns both folders (navigable) and files (preview only) so the user
        can see what will be synced before selecting a folder.

        Args:
            user_id: Owning user ID.
            folder_id: Parent folder ID (default: "root").
            page_token: Pagination token from a previous response.
            max_results: Provider page bound; the GUI retains its existing default.

        Returns:
            Dict with 'files' list and optional 'nextPageToken'.
        """
        client = await self._get_drive_client(user_id)
        try:
            await self.db.commit()  # Credential reads end before the provider wait.
            async with space_read(user_id=user_id, section=SECTION_DRIVE):
                return await client.list_files(
                    folder_id=folder_id,
                    content_type=None,
                    page_token=page_token,
                    max_results=max_results,
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
        credentials = await ConnectorService(self.db).get_connector_credentials(
            user_id, ConnectorType.GOOGLE_DRIVE
        )
        if not credentials:
            raise BaseAPIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google Drive connector is not active",
                log_event="rag_drive_connector_not_active",
                user_id=str(user_id),
            )
        # The client's own writes run on a session of their own (ADR-304).
        return GoogleDriveClient(user_id, credentials, DetachedConnectorService())


# ============================================================================
# Background Sync
# ============================================================================


async def sync_folder_background(
    space_id: UUID,
    source_id: UUID,
    user_id: UUID,
) -> None:
    """Background coroutine for Drive folder sync.

    Creates its own DB session and drive client. Walks the linked folder AND
    its sub-folders (``drive_walk``), downloads or exports the supported
    files, creates RAGDocument records, launches document processing, and
    persists the walked folder set the push path routes on.

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

            if current_source_worker() is not None:
                await require_source_worker(
                    db, source_id=source_id, kind="drive", actor_id=user_id, space_id=space_id
                )
                await db.commit()

            # Get source
            source = await source_repo.get_by_id(source_id)
            if not source:
                logger.warning(
                    "rag_drive_sync_source_not_found",
                    source_id=str(source_id),
                )
                return

            # Get drive client: its credentials read in a session of their
            # own, its token refreshes written through it (ADR-304).
            connectors = DetachedConnectorService()
            await db.commit()
            async with connectors.unit_of_work() as connector_service:
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

            client = GoogleDriveClient(user_id, credentials, connectors)
            # The reads end before the walk: a tree of hundreds of folders is
            # hundreds of Drive calls, and no transaction waits on them.
            await db.commit()
            try:
                # The whole tree under the linked folder, bounded (drive_walk).
                # ONE consultation for the act: the person asked for this
                # folder to be kept indexed, and honouring it opens their Drive.
                try:
                    folder_id = source.folder_id
                    async with space_read(user_id=user_id, section=SECTION_DRIVE):
                        tree = await source_worker_external(
                            lambda: walk_drive_tree(
                                client,
                                folder_id,
                                max_files=native_source_limit(
                                    RAG_DRIVE_MAX_FILES_PER_SYNC, "max_items"
                                ),
                                max_folders=RAG_DRIVE_MAX_FOLDERS_PER_WALK,
                            )
                        )
                except DriveWalkError as e:
                    await source_repo.update(
                        source,
                        {
                            "sync_status": RAGDriveSyncStatus.ERROR,
                            "error_message": str(e),
                        },
                    )
                    await db.commit()
                    rag_drive_sync_runs_total.labels(status="error").inc()
                    return

                if tree.truncated:
                    logger.warning(
                        "rag_drive_sync_walk_truncated",
                        source_id=str(source_id),
                        file_count=len(tree.files),
                        folder_count=len(tree.folder_ids),
                    )

                # Filter supported files
                supported_files = [f for f in tree.files if is_supported_drive_file(f)]

                # Process each file. `synced` is computed AFTER the embedding
                # oracle (F053); the loop only tracks skips and download failures.
                skipped = 0
                failed = 0
                docs_to_process: list[dict] = []
                seen_file_ids: set[str] = set()
                jobs = RAGJobsRepository(db)

                for drive_file in supported_files:
                    # Renew the source lease before each (slow) file download so a
                    # live sync is never reclaimed by the reaper mid-flight.
                    await jobs.heartbeat_source(source_id, settings.rag_job_lease_ttl_seconds)
                    seen_file_ids.add(drive_file["id"])

                    ingest = await ingest_drive_file(
                        db,
                        client,
                        space_id=space_id,
                        source_id=source_id,
                        user_id=user_id,
                        drive_file=drive_file,
                    )
                    if ingest.outcome == "queued" and ingest.process_kwargs:
                        # Queue for processing. NOT counted as synced yet: a
                        # downloaded file is not a synced file until its
                        # embedding succeeded (audit F053).
                        docs_to_process.append(ingest.process_kwargs)
                    elif ingest.outcome == "failed":
                        failed += 1
                    else:
                        skipped += 1

                # Detect and delete removed files
                existing_file_ids = await doc_repo.get_drive_file_ids_for_source(source_id)
                complete_listing = not tree.truncated and tree.unreadable_folders == 0
                removed_ids = existing_file_ids - seen_file_ids if complete_listing else set()
                for removed_file_id in removed_ids:
                    await remove_drive_document(
                        db,
                        space_id=space_id,
                        source_id=source_id,
                        user_id=user_id,
                        file_id=removed_file_id,
                    )

                # Every read and write of the loop ends before the documents
                # embed (ADR-304): the embeddings run for minutes, each on a
                # session of its own, and this one must not wait on them.
                await db.commit()

                # Await all document processing BEFORE declaring the sync
                # complete. This coroutine is already a detached background task,
                # so awaiting blocks nothing user-facing — but it stops the
                # source from claiming COMPLETED while its documents are still
                # embedding (audit F001, "premature COMPLETED"). Each
                # process_document opens its own DB session, so concurrent
                # execution under the semaphore is session-safe.
                synced, embed_failed = await process_queued(
                    docs_to_process, processor=process_document
                )
                # Count AFTER the processing oracle (audit F053): the
                # result="synced" series and the synced counter only move once
                # process_document returned True. process_document swallows its
                # own exceptions and returns False on failure (it never
                # re-raises), so a failed document surfaces as
                # `proc_result is not True`; a gather exception (defensive,
                # return_exceptions=True) lands on the same branch. Each
                # downloaded document increments exactly one of the two series
                # here — download failures were already counted result="failed"
                # in the per-file loop and never reach this point.
                # Update source status — now truthful: all documents processed.
                values = await sync_result_values(db, source, tree, len(supported_files), synced)
                await source_repo.update(source, values)
                await db.commit()

                duration = time.time() - start_time
                rag_drive_sync_runs_total.labels(
                    status=(
                        "completed"
                        if values["sync_status"] == RAGDriveSyncStatus.COMPLETED
                        else "error"
                    )
                ).inc()
                rag_drive_sync_duration_seconds.observe(duration)

                # Same counters as persisted on RAGDriveSource (audit F053):
                # synced == synced_file_count; failures are split by cause so
                # the log can never claim more successes than the base records.
                logger.info(
                    (
                        "rag_drive_sync_complete"
                        if values["sync_status"] == RAGDriveSyncStatus.COMPLETED
                        else "rag_drive_sync_partial"
                    ),
                    source_id=str(source_id),
                    downloaded=len(docs_to_process),
                    synced=synced,
                    failed_download=failed,
                    failed_embedding=embed_failed,
                    skipped=skipped,
                    removed=len(removed_ids),
                    duration=round(duration, 2),
                )
            finally:
                await client.close()

    except SourceLeaseLost:
        rag_drive_sync_runs_total.labels(status="error").inc()
        logger.warning("rag_drive_sync_lease_lost", source_id=str(source_id))
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
                    await record_source_failure(db, source, e)
        except Exception:
            logger.exception(
                "rag_drive_sync_error_update_failed",
                source_id=str(source_id),
            )
