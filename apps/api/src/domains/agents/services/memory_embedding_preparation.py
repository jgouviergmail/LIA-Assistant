"""Resolve all embedding work outside the extraction's consent-locked transaction."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from src.domains.memories.models import Memory
from src.domains.memories.prepared_embeddings import (
    MemoryEmbedder,
    MemoryVectors,
    PreparedMemoryEmbeddings,
)
from src.domains.memories.schemas import ExtractedMemory
from src.domains.users.extraction_consent import ExtractionKind, snapshot_extraction_consent
from src.infrastructure.database.session import get_db_context


async def prepare_memory_embeddings(
    actor_id: UUID,
    actions: Sequence[ExtractedMemory],
    embedder: MemoryEmbedder,
    *,
    extraction_revision: int,
) -> PreparedMemoryEmbeddings:
    ids: set[UUID] = set()
    for action in actions:
        if action.action == "update" and action.memory_id:
            try:
                ids.add(UUID(action.memory_id))
            except ValueError:
                continue
    existing: dict[str, tuple[str, str]] = {}
    if ids:
        async with get_db_context() as db:
            memories = await db.scalars(
                select(Memory).where(Memory.user_id == actor_id, Memory.id.in_(ids))
            )
            existing = {
                str(memory.id): (memory.content, memory.trigger_topic)
                for memory in memories
                if not memory.pinned and memory.invalidated_at is None
            }
    keys: set[tuple[str, str]] = set()
    for action in actions:
        if action.action == "create" and action.content and action.category:
            keys.add((action.content, action.trigger_topic or ""))
        elif (
            action.action == "update"
            and action.memory_id is not None
            and action.memory_id in existing
        ):
            old_content, old_topic = existing[action.memory_id]
            keys.add(
                (
                    action.content if action.content is not None else old_content,
                    action.trigger_topic if action.trigger_topic is not None else old_topic,
                )
            )
    vectors: dict[tuple[str, str], MemoryVectors] = {}
    for content, topic in sorted(keys):
        async with get_db_context() as db:
            revision = await snapshot_extraction_consent(
                db, actor_id, ExtractionKind.MEMORY, expected_revision=extraction_revision
            )
        if revision is None:
            # The late write fence also refuses this lease; no further paid work starts.
            return PreparedMemoryEmbeddings({})
        vectors[(content, topic)] = await embedder(content, topic)
    return PreparedMemoryEmbeddings(vectors)
