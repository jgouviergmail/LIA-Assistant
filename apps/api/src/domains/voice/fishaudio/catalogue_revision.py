"""A library revision shared by PostgreSQL choices and cached voice lists."""

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.voice.fishaudio.models import FishAudioCatalogueRevision
from src.infrastructure.database.owner_lock import INSTANCE_OWNER, hold_owner_lock
from src.infrastructure.database.session import get_db_context


async def pending_removals(db: AsyncSession) -> dict[str, str]:
    """Pending deletions stay unavailable even after a timeout or worker restart."""
    pending: dict[str, str] | None = await db.scalar(
        select(FishAudioCatalogueRevision.pending_removals).where(
            FishAudioCatalogueRevision.id == INSTANCE_OWNER
        )
    )
    return dict(pending or {})


async def reserve_removal(db: AsyncSession, voice_id: str) -> tuple[str, bool]:
    """Reserve under the catalogue lock; a retry cannot undo prior uncertainty."""
    pending = await pending_removals(db)
    fresh = voice_id not in pending
    token = uuid4().hex
    pending[voice_id] = token
    await _store_pending(db, pending)
    return token, fresh


async def clear_removal(db: AsyncSession, voice_id: str, token: str) -> bool:
    """Only this deletion can release its reservation; a newer retry owns its own."""
    pending = await pending_removals(db)
    if pending.get(voice_id) != token:
        return False
    del pending[voice_id]
    await _store_pending(db, pending)
    return True


async def _store_pending(db: AsyncSession, pending: dict[str, str]) -> None:
    generation = uuid4()
    statement = insert(FishAudioCatalogueRevision).values(
        id=INSTANCE_OWNER, generation=generation, pending_removals=pending
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[FishAudioCatalogueRevision.id],
            set_={"generation": generation, "pending_removals": pending, "updated_at": func.now()},
        )
    )


async def lock_catalogue(db: AsyncSession) -> None:
    """Serialize the final choice write and local deletion, including no state row."""
    await hold_owner_lock(db, "fishaudio_voice_catalogue", INSTANCE_OWNER)


async def current_revision(db: AsyncSession) -> UUID | None:
    """Read the revision fresh; absence is the initial catalogue's revision."""
    generation: UUID | None = await db.scalar(
        select(FishAudioCatalogueRevision.generation).where(
            FishAudioCatalogueRevision.id == INSTANCE_OWNER
        )
    )
    return generation


async def catalogue_revision() -> UUID | None:
    """Read on a short session closed before any vendor wait."""
    async with get_db_context() as db:
        return await current_revision(db)


async def advance_revision(db: AsyncSession) -> None:
    """Replace the revision within the caller's locked deletion transaction."""
    generation = uuid4()
    statement = insert(FishAudioCatalogueRevision).values(id=INSTANCE_OWNER, generation=generation)
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[FishAudioCatalogueRevision.id],
            set_={"generation": generation, "updated_at": func.now()},
        )
    )
