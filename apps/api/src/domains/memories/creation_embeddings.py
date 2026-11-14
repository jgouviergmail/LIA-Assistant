"""Explicit memory writes share one bounded, owned embedding preparation."""

from collections.abc import Awaitable, Callable, Sequence
from itertools import batched
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import MEMORY_IMPORT_EMBEDDING_BATCH_SIZE
from src.domains.memories.prepared_embeddings import PreparedMemoryEmbeddings
from src.domains.memories.service import (
    _generate_document_embedding,
    generate_document_embeddings,
)
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.usage_guard import enforce_usage_limit


def released_after(
    db: AsyncSession, guard: Callable[[], Awaitable[None]]
) -> Callable[[], Awaitable[None]]:
    """A fence that ends its read: an embedding is a network call (ADR-304).

    Nothing is written before the embeddings, so ending the transaction loses nothing and the
    write that follows reads again under its lock.

    Args:
        db: The session the fence reads on.
        guard: The fence.

    Returns:
        The fence, leaving no transaction open.
    """

    async def fence() -> None:
        await guard()
        await db.rollback()

    return fence


async def prepare_memory_creation_embeddings(
    user_id: UUID,
    command_id: UUID,
    content: str,
    trigger_topic: str,
    guard: Callable[[], Awaitable[None]],
) -> PreparedMemoryEmbeddings:
    """Both ceilings and current permission are checked before each paid source call."""
    previous = get_embedding_context()
    set_embedding_context(str(user_id), f"application-memory:{command_id}", run_id=str(command_id))
    try:
        texts = [content, trigger_topic] if trigger_topic.strip() else [content]
        vectors: list[list[float] | None] = []
        for text in texts:
            await guard()
            await enforce_usage_limit(user_id, layer="application_memory")
            vectors.append(await _generate_document_embedding(text))
        return PreparedMemoryEmbeddings(
            {(content, trigger_topic): (vectors[0], vectors[1] if len(vectors) == 2 else None)}
        )
    finally:
        clear_embedding_context()
        if previous is not None:
            set_embedding_context(
                previous.user_id, previous.session_id, previous.conversation_id, previous.run_id
            )


async def prepare_memory_import_embeddings(
    user_id: UUID,
    command_id: UUID,
    pairs: Sequence[tuple[str, str]],
    guard: Callable[[], Awaitable[None]],
) -> PreparedMemoryEmbeddings:
    """The vectors of an import, asked by batches: the fence and both ceilings before each.

    Each distinct text is embedded once (a trigger topic several memories share is paid
    for once), ``MEMORY_IMPORT_EMBEDDING_BATCH_SIZE`` texts per provider call. The spend
    is attributed to the account for the whole import, and a failed call is raised: the
    caller then writes nothing.

    Args:
        user_id: The account the memories are imported into, and billed.
        command_id: The identity of this import, under which its spend is filed.
        pairs: The ``(content, trigger_topic)`` of each memory to create.
        guard: The fence asked before every paid call; it leaves no transaction open.

    Returns:
        The closed set of vectors the write resolves from.
    """
    texts = list(dict.fromkeys(text for pair in pairs for text in pair if text.strip()))
    vectors: dict[str, list[float]] = {}
    previous = get_embedding_context()
    set_embedding_context(str(user_id), f"application-memory:{command_id}", run_id=str(command_id))
    try:
        for batch in batched(texts, MEMORY_IMPORT_EMBEDDING_BATCH_SIZE, strict=False):
            await guard()
            await enforce_usage_limit(user_id, layer="application_memory")
            answered = await generate_document_embeddings(list(batch))
            vectors.update(zip(batch, answered, strict=True))
    finally:
        clear_embedding_context()
        if previous is not None:
            set_embedding_context(
                previous.user_id, previous.session_id, previous.conversation_id, previous.run_id
            )
    return PreparedMemoryEmbeddings(
        {
            (content, trigger_topic): (
                vectors[content],
                vectors[trigger_topic] if trigger_topic.strip() else None,
            )
            for content, trigger_topic in pairs
        }
    )
