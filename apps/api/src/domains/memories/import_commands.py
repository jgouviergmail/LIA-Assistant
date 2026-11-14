"""Import the memories of an export into an account: all of what is new, or nothing.

One sequence, and no transaction around the provider (ADR-304):

1. read what the account already holds — a memory it has is neither created again nor
   paid for;
2. compute the vectors of what is new, by batches, under the fence and both spending
   ceilings (``prepare_memory_import_embeddings``); the fence asked before every paid
   call ends the transaction, and a refused ceiling or a failed call stops here,
   nothing written;
3. take the account's lock, read what it holds AGAIN (an extraction or another import
   may have written meanwhile), create what is still new, and commit once.

The counts answered are exact (ADR-185): every entry of the file is imported, already
present, a duplicate inside the file, or invalid.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.creation_embeddings import prepare_memory_import_embeddings
from src.domains.memories.import_file import ParsedMemoryImport
from src.domains.memories.management_commands import lock_memory_actor, set_locked_memory_pin
from src.domains.memories.models import Memory
from src.domains.memories.service import MemoryService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MemoryImportOutcome:
    """What became of every entry of the file.

    Attributes:
        total: Every entry the file held.
        imported: Memories created.
        already_present: Entries whose content the account already held.
        duplicates: Entries whose content the file itself already held.
        invalid: Entries the write schema refuses.
    """

    total: int
    imported: int
    already_present: int
    duplicates: int
    invalid: int


async def _held_contents(db: AsyncSession, user_id: UUID) -> set[str]:
    """The content of every active memory of the account."""
    rows = await db.scalars(
        select(Memory.content).where(Memory.user_id == user_id, Memory.invalidated_at.is_(None))
    )
    return set(rows)


async def import_memories(
    db: AsyncSession, user_id: UUID, parsed: ParsedMemoryImport
) -> MemoryImportOutcome:
    """Create the memories of a parsed export that the account does not hold yet.

    The caller holds no transaction when it calls, and none is left open on return: the
    import commits what it wrote. On any failure nothing is written.

    Args:
        db: The request's session.
        user_id: The account the memories are imported into, and billed.
        parsed: The file, as :func:`~src.domains.memories.import_file.parse_memory_import`
            read it.

    Returns:
        The exact count of what became of every entry.
    """
    held = await _held_contents(db, user_id)
    new = [memory for memory in parsed.memories if memory.data.content not in held]

    async def fence() -> None:
        await lock_memory_actor(db, user_id)
        # Nothing was written: this ends the read above and the fence, so no
        # transaction is open when the provider is called.
        await db.commit()

    prepared = await prepare_memory_import_embeddings(
        user_id,
        uuid4(),
        [(memory.data.content, memory.data.trigger_topic) for memory in new],
        fence,
    )

    await lock_memory_actor(db, user_id)
    held = await _held_contents(db, user_id)
    service = MemoryService(db, embedder=prepared.resolve)
    imported = 0
    for memory in new:
        if memory.data.content in held:
            continue
        row = await service.create_from_management(user_id, memory.data)
        if memory.pinned is not None and row.pinned != memory.pinned:
            await set_locked_memory_pin(db, row, memory.pinned)
        imported += 1
    await db.commit()

    outcome = MemoryImportOutcome(
        total=parsed.total,
        imported=imported,
        already_present=len(parsed.memories) - imported,
        duplicates=parsed.duplicates,
        invalid=parsed.invalid,
    )
    logger.info(
        "memories_imported",
        user_id=str(user_id),
        total=outcome.total,
        imported=outcome.imported,
        already_present=outcome.already_present,
        duplicates=outcome.duplicates,
        invalid=outcome.invalid,
    )
    return outcome
