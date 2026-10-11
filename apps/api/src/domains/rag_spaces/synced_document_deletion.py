"""Native sync retains old bytes until the row deletion has a known SQL acknowledgement."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.domains.rag_spaces.models import RAGDocument, RAGDocumentStatus
from src.domains.rag_spaces.repository import RAGChunkRepository, RAGDocumentRepository
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    current_source_worker,
    require_source_worker,
)
from src.domains.rag_spaces.storage_paths import stored_file_path
from src.infrastructure.file_transfer import LocalFileRead


async def capture_native_synced_file(
    document: RAGDocument, user_id: UUID, space_id: UUID
) -> tuple[str, str | None]:
    filename = document.filename
    expected_digest: str | None = None
    try:
        reader = LocalFileRead.open(stored_file_path(user_id, space_id, filename))
    except FileNotFoundError:
        return filename, None
    try:
        expected_digest = reader.identity_digest
    finally:
        await reader.close()
    return filename, expected_digest


async def lock_native_replacement(
    db: AsyncSession, document: RAGDocument, user_id: UUID, space_id: UUID
) -> None:
    expected = (document.filename, document.updated_at, document.status)
    current = await db.scalar(
        select(RAGDocument)
        .where(
            RAGDocument.id == document.id,
            RAGDocument.user_id == user_id,
            RAGDocument.space_id == space_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        current is None
        or (current.filename, current.updated_at, current.status) != expected
        or current.status not in {RAGDocumentStatus.READY, RAGDocumentStatus.ERROR}
    ):
        raise SourceLeaseLost("Replacement document changed or has an active processing job")
    scope = current_source_worker()
    if scope is not None:
        reference = current.drive_source_id if scope.kind == "drive" else current.mail_source_id
        if reference is not None and reference != scope.source_id:
            raise SourceLeaseLost("Replacement belongs to another source")


async def discard_native_synced_document(
    db: AsyncSession, document: RAGDocument, user_id: UUID, space_id: UUID
) -> None:
    await lock_native_replacement(db, document, user_id, space_id)
    filename, expected_digest = await capture_native_synced_file(document, user_id, space_id)
    await require_source_worker(db)
    await RAGChunkRepository(db).delete_by_document(document.id)
    await RAGDocumentRepository(db).delete(document)
    await require_source_worker(db)
    await db.commit()  # Unknown ACK preserves bytes; the caller does not replay or compensate.
    await cleanup_deleted_document_file(user_id, space_id, filename, expected_digest)
