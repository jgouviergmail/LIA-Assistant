"""A partial Drive census retains routing coverage and cannot claim a completed sync."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces.drive_walk import DriveTree
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGDriveSyncStatus,
)
from src.domains.rag_spaces.source_worker_lease import current_source_worker, require_source_worker


def drive_sync_values(
    source: RAGDriveSource, tree: DriveTree, supported_count: int, synced: int
) -> dict[str, object]:
    complete = not tree.truncated and tree.unreadable_folders == 0
    folders = (
        list(tree.folder_ids)
        if complete
        else list(dict.fromkeys([source.folder_id, *(source.folder_ids or ()), *tree.folder_ids]))
    )
    return {
        "sync_status": RAGDriveSyncStatus.COMPLETED if complete else RAGDriveSyncStatus.ERROR,
        "last_sync_at": datetime.now(UTC) if complete else source.last_sync_at,
        "file_count": supported_count,
        "synced_file_count": synced,
        "folder_ids": folders,
        "error_message": (
            None
            if complete
            else "Source listing incomplete; unseen documents and previously known folders were retained. Counts cover the observed subset."
        ),
        "lease_expires_at": None,
        "worker_id": None,
        "attempts": 0,
        "heartbeat_at": None,
    }


async def sync_result_values(
    db: AsyncSession, source: RAGDriveSource, tree: DriveTree, supported_count: int, synced: int
) -> dict[str, object]:
    values = drive_sync_values(source, tree, supported_count, synced)
    scope = current_source_worker()
    if scope is None:
        return values
    await require_source_worker(db)
    total, ready = (
        await db.execute(
            select(
                func.count(RAGDocument.id),
                func.count(RAGDocument.id).filter(RAGDocument.status == RAGDocumentStatus.READY),
            ).where(
                RAGDocument.drive_source_id == source.id,
                RAGDocument.user_id == scope.actor_id,
                RAGDocument.space_id == scope.space_id,
            )
        )
    ).one()
    values["synced_file_count"] = ready
    complete_listing = not tree.truncated and tree.unreadable_folders == 0
    if not complete_listing:
        values["file_count"] = total
    if ready != supported_count or not complete_listing:
        values.update(
            sync_status=RAGDriveSyncStatus.ERROR,
            last_sync_at=source.last_sync_at,
            error_message="Synchronization incomplete; retained-document counts are current. Consult document states and confirm a new synchronization to retry.",
        )
    return values
