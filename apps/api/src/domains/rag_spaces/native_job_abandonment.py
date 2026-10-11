"""Interrupted native jobs close as errors; a new action requires fresh human consent."""

from sqlalchemy import and_, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentErrorCode,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGMailSource,
    RAGSourceSyncStatus,
    RAGSpace,
)
from src.domains.rag_spaces.repository import RAGDriveSourceRepository, RAGMailSourceRepository
from src.domains.rag_spaces.source_worker_lease import (
    NATIVE_DOCUMENT_WORKER_PREFIX,
    NATIVE_SOURCE_WORKER_PREFIX,
    SourceLeaseLost,
    current_source_worker,
    require_source_worker,
)

_INTERRUPTED = "Synchronization interrupted; confirm a new synchronization to retry."


def is_native_source_job(worker_id: object) -> bool:
    return isinstance(worker_id, str) and worker_id.startswith(NATIVE_SOURCE_WORKER_PREFIX)


async def record_source_failure(
    db: AsyncSession, source: RAGDriveSource | RAGMailSource, error: Exception
) -> None:
    if current_source_worker() is not None:
        await stop_abandoned_native_source(db, source, allow_live=True)
        return
    values: dict[str, object] = {
        "sync_status": RAGSourceSyncStatus.ERROR,
        "error_message": f"Sync failed: {error}",
    }
    if isinstance(source, RAGDriveSource):
        await RAGDriveSourceRepository(db).update(source, values)
    else:
        values.update(lease_expires_at=None, worker_id=None)
        await RAGMailSourceRepository(db).update(source, values)
    await db.commit()


async def stop_abandoned_native_source(
    db: AsyncSession, source: RAGDriveSource | RAGMailSource, *, allow_live: bool = False
) -> str | None:
    """Atomic source/document closure retains bytes and never launches external work."""
    token = source.worker_id
    if not is_native_source_job(token):
        return None
    if allow_live:
        if current_source_worker() is None:
            raise SourceLeaseLost("A live native closure needs its owned worker scope")
        await require_source_worker(db, source_id=source.id)
    parent = await db.scalar(
        select(RAGSpace.id)
        .where(RAGSpace.id == source.space_id, RAGSpace.user_id == source.user_id)
        .with_for_update()
    )
    if parent is None:
        return "skipped"
    model = RAGDriveSource if isinstance(source, RAGDriveSource) else RAGMailSource
    stale = await db.scalar(
        select(model.id)
        .where(
            model.id == source.id,
            model.space_id == source.space_id,
            model.user_id == source.user_id,
            model.worker_id == token,
            model.sync_status == RAGSourceSyncStatus.SYNCING,
            or_(
                literal(allow_live),
                model.lease_expires_at.is_(None),
                model.lease_expires_at <= func.clock_timestamp(),
            ),
        )
        .with_for_update()
    )
    if stale is None:
        return "skipped"
    reference = (
        RAGDocument.drive_source_id if model is RAGDriveSource else RAGDocument.mail_source_id
    )
    await db.execute(
        update(RAGDocument)
        .where(
            reference == source.id,
            RAGDocument.user_id == source.user_id,
            RAGDocument.space_id == source.space_id,
            or_(
                RAGDocument.status == RAGDocumentStatus.PENDING,
                and_(
                    RAGDocument.status == RAGDocumentStatus.PROCESSING,
                    RAGDocument.worker_id.startswith(NATIVE_DOCUMENT_WORKER_PREFIX),
                ),
            ),
        )
        .values(
            status=RAGDocumentStatus.ERROR,
            error_code=RAGDocumentErrorCode.RETRIES_EXHAUSTED.value,
            error_message=_INTERRUPTED,
            worker_id=None,
            heartbeat_at=None,
            lease_expires_at=None,
        )
    )
    await db.execute(
        update(model)
        .where(model.id == source.id, model.worker_id == token)
        .values(
            sync_status=RAGSourceSyncStatus.ERROR,
            error_message=_INTERRUPTED,
            worker_id=None,
            heartbeat_at=None,
            lease_expires_at=None,
        )
    )
    await db.commit()
    return "failed"


async def stop_abandoned_native_document(db: AsyncSession, document: RAGDocument) -> str | None:
    token = document.worker_id
    if isinstance(token, str) and token.startswith(NATIVE_DOCUMENT_WORKER_PREFIX):
        result = await db.execute(
            update(RAGDocument)
            .where(
                RAGDocument.id == document.id,
                RAGDocument.worker_id == token,
                RAGDocument.status == RAGDocumentStatus.PROCESSING,
                RAGDocument.lease_expires_at.is_(None)
                | (RAGDocument.lease_expires_at <= func.clock_timestamp()),
            )
            .values(
                status=RAGDocumentStatus.ERROR,
                error_code=RAGDocumentErrorCode.RETRIES_EXHAUSTED.value,
                error_message=_INTERRUPTED,
                worker_id=None,
                heartbeat_at=None,
                lease_expires_at=None,
            )
            .returning(RAGDocument.id)
        )
        changed = result.scalar_one_or_none() is not None
        await db.commit()
        return "failed" if changed else "skipped"
    for model, reference in (
        (RAGDriveSource, document.drive_source_id),
        (RAGMailSource, document.mail_source_id),
    ):
        if reference is not None:
            owner = await db.scalar(select(model.worker_id).where(model.id == reference))
            if is_native_source_job(owner):
                return "skipped"
    return None
