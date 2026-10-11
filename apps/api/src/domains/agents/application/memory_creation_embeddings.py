"""Approved embedding work runs outside write locks and keeps existing cost attribution."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from src.domains.memories.prepared_embeddings import PreparedMemoryEmbeddings
from src.domains.memories.service import _generate_document_embedding
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.usage_guard import enforce_usage_limit


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
