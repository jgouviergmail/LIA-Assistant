"""Durable bookmark projections fence live account/capability/parent/claim before paid work."""

from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentSourceType,
    RAGDocumentStatus,
    RAGSpace,
)
from src.domains.usage_limits.enforcement import spend_blocked
from src.domains.users.models import User


class BookmarkProcessingStopped(RuntimeError):
    """A stopped projection must not spend again or publish computed data."""


async def require_bookmark_processing(
    db: AsyncSession,
    document_id: UUID,
    actor_id: UUID,
    space_id: UUID,
    *,
    worker_id: str | None = None,
    before_spend: bool = False,
) -> None:
    if before_spend and await spend_blocked(actor_id):
        raise BookmarkProcessingStopped("Bookmark indexing budget unavailable")
    try:
        await require_capability_fresh(db, PlatformCapability.BOOKMARKS)
        await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    except AuthorizationError as error:
        raise BookmarkProcessingStopped("Bookmark indexing capability unavailable") from error
    owner = await db.scalar(
        select(User.id)
        .where(User.id == actor_id, User.is_active.is_(True), User.deleted_at.is_(None))
        .with_for_update()
    )
    parent = await db.scalar(
        select(RAGSpace.id)
        .where(RAGSpace.id == space_id, RAGSpace.user_id == actor_id, RAGSpace.is_system.is_(False))
        .with_for_update()
    )
    if owner is None or parent is None:
        raise BookmarkProcessingStopped("Bookmark indexing account or parent unavailable")
    statement = select(RAGDocument.id).where(
        RAGDocument.id == document_id,
        RAGDocument.user_id == actor_id,
        RAGDocument.space_id == space_id,
        RAGDocument.source_type == RAGDocumentSourceType.BOOKMARK,
    )
    if worker_id is not None:
        statement = statement.where(
            RAGDocument.worker_id == worker_id,
            RAGDocument.status == RAGDocumentStatus.PROCESSING,
            RAGDocument.lease_expires_at > func.clock_timestamp(),
        )
    if await db.scalar(statement.with_for_update()) is None:
        raise BookmarkProcessingStopped("Bookmark projection or claim unavailable")


async def settle_stopped_bookmark(
    db: AsyncSession, document_id: UUID, actor_id: UUID, space_id: UUID, worker_id: str
) -> None:
    """A revoked worker can close only its own projection; recovery cannot re-spend it."""
    await db.execute(
        update(RAGDocument)
        .where(
            RAGDocument.id == document_id,
            RAGDocument.user_id == actor_id,
            RAGDocument.space_id == space_id,
            RAGDocument.source_type == RAGDocumentSourceType.BOOKMARK,
            or_(
                RAGDocument.status == RAGDocumentStatus.PENDING, RAGDocument.worker_id == worker_id
            ),
        )
        .values(
            status=RAGDocumentStatus.ERROR,
            error_message="Saved-answer indexing authority unavailable",
            error_code=None,
            worker_id=None,
            lease_expires_at=None,
            heartbeat_at=None,
        )
    )
    await db.commit()
