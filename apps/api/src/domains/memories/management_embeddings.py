"""Prepare manually requested vectors with ownership and both spending ceilings."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.creation_embeddings import prepare_memory_creation_embeddings
from src.domains.memories.management_commands import lock_memory_actor
from src.domains.memories.prepared_embeddings import PreparedMemoryEmbeddings


async def prepare_managed_embeddings(
    db: AsyncSession, user_id: UUID, texts: tuple[str, str] | None
) -> PreparedMemoryEmbeddings:
    """Release every authority read before the network; caller re-locks before writing."""
    if texts is None:
        return PreparedMemoryEmbeddings({})

    async def guard() -> None:
        await lock_memory_actor(db, user_id)
        # The caller committed its read; this transaction contains only the fence.
        await db.commit()

    return await prepare_memory_creation_embeddings(user_id, uuid4(), *texts, guard)
