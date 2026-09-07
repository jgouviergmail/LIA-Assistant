"""Semantic memory recall for the 360° — deliberately not the page's read.

The relationship card answers "which memories MENTION this name" with a literal
match, and says it is best-effort. The 360° benefits from memories that are
ABOUT the person without naming them, so it embeds the name and searches by
relevance. Two different questions, two different reads, both stated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger(__name__)

_MEMORIES_LIMIT = 5
_MEMORY_MIN_SCORE = 0.3


async def fetch_person_memories(user_id: UUID, person_name: str) -> list[str] | None:
    """Long-term memories relevant to the person (embedding + topic match).

    Args:
        user_id: Owner of the memories.
        person_name: The person to recall about.

    Returns:
        The memory contents, or None when no embedding could be computed —
        which is "I could not look", not "there is nothing".
    """
    from src.domains.memories.repository import MemoryRepository
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.llm.user_message_embedding import get_or_compute_embedding

    # A person name is a lookup key, never an utterance: the triviality patterns
    # collide with real surnames (Fine, Cool, Bien), and treating one as trivial
    # returned None here — silently erasing that contact's memories.
    query_embedding = await get_or_compute_embedding(message=person_name, is_conversational=False)
    if not query_embedding:
        return None
    async with get_db_context() as db:
        results = await MemoryRepository(db).search_by_relevance(
            user_id=user_id,
            query_embedding=query_embedding,
            limit=_MEMORIES_LIMIT,
            min_score=_MEMORY_MIN_SCORE,
        )
    return [memory.content for memory, _score in results if memory.content]


def recalled_memories(recall: object) -> list[str] | None:
    """What the recall actually answered — or None for "I could not".

    ``None`` is not ``[]``: the recall returns None when no embedding could be
    computed (provider down, key missing), and an exception means the same.
    Flattening either into an empty list would have the assistant state this
    person is unmemorable — the negative ADR-184 forbids.

    Args:
        recall: The recall's result, an exception, or None.

    Returns:
        The memories, or None when the question was never answered.
    """
    if isinstance(recall, BaseException) or recall is None:
        logger.info(
            "person_overview_memories_unreadable",
            error_type=type(recall).__name__ if recall is not None else "no_embedding",
        )
        return None
    return list(recall) if isinstance(recall, list) else []
