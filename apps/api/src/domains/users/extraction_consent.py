"""Fresh consent and a durable fence shared by automatic personal-data writers."""

from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import Select

from src.domains.users.models import User


class ExtractionKind(str, Enum):
    MEMORY = "memory"
    JOURNAL = "journal"
    PSYCHE = "psyche"


_CONSENT_COLUMNS: dict[ExtractionKind, InstrumentedAttribute[bool]] = {
    ExtractionKind.MEMORY: User.memory_enabled,
    ExtractionKind.JOURNAL: User.journals_enabled,
    ExtractionKind.PSYCHE: User.psyche_enabled,
}


def invalidate_extractions(actor: User) -> None:
    """The caller holds the user's write lock until its personal-data change commits."""
    actor.extraction_revision = (actor.extraction_revision or 0) + 1


def _revision_query(
    actor_id: UUID, expected_revision: int | None, lock: bool
) -> Select[tuple[int]]:
    query = select(User.extraction_revision).where(
        User.id == actor_id, User.is_active, User.deleted_at.is_(None)
    )
    if expected_revision is not None:
        query = query.where(User.extraction_revision == expected_revision)
    return query.with_for_update() if lock else query


async def snapshot_extraction_revision(
    db: AsyncSession,
    actor_id: UUID,
    *,
    expected_revision: int | None = None,
    lock: bool = False,
) -> int | None:
    """Fence writers whose source has no per-account learning consent."""
    revision: int | None = await db.scalar(_revision_query(actor_id, expected_revision, lock))
    return revision


async def snapshot_extraction_consent(
    db: AsyncSession,
    actor_id: UUID,
    kind: ExtractionKind,
    *,
    expected_revision: int | None = None,
    lock: bool = False,
) -> int | None:
    query = _revision_query(actor_id, expected_revision, lock).where(_CONSENT_COLUMNS[kind])
    revision: int | None = await db.scalar(query)
    return revision
