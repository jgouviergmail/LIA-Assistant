"""A native document job owns its claim independently of the source claim."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.rag_spaces.jobs_repository import RAGJobsRepository
from src.domains.rag_spaces.models import RAGDocument, RAGDocumentStatus
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    current_source_worker,
    require_source_worker,
)
from src.infrastructure.database.session import get_db_context


async def require_source_document(db: AsyncSession, document_id: UUID, worker_id: str) -> None:
    scope = current_source_worker()
    if scope is None:
        return
    await require_source_worker(db)
    reference = RAGDocument.drive_source_id if scope.kind == "drive" else RAGDocument.mail_source_id
    owned = await db.scalar(
        select(RAGDocument.id)
        .where(
            RAGDocument.id == document_id,
            RAGDocument.user_id == scope.actor_id,
            RAGDocument.space_id == scope.space_id,
            reference == scope.source_id,
            RAGDocument.status == RAGDocumentStatus.PROCESSING,
            RAGDocument.worker_id == worker_id,
            RAGDocument.lease_expires_at > func.clock_timestamp(),
        )
        .with_for_update()
    )
    if owned is None:
        raise SourceLeaseLost("Native document claim expired or changed owner")


async def renew_source_document(document_id: UUID, worker_id: str) -> None:
    if current_source_worker() is None:
        return
    async with get_db_context() as db:
        await require_source_document(db, document_id, worker_id)
        if not await RAGJobsRepository(db).heartbeat_document(
            document_id, worker_id, settings.rag_job_lease_ttl_seconds
        ):
            raise SourceLeaseLost("Native document renewal refused")
