"""Turning a LOOKUP into memories — the one door (ADR-313).

A lookup is a subject somebody asks about (« my dentist », « what do I drink »,
a person's name), never a line of chat. Several callers turned such a query into
memories, three different ways, and one of them did not search at all:

- the pre-planner reference resolution embedded the query itself;
- the 360° person recall went through the shared embedding cache;
- the phone's ``recall_memories`` lookup and the owner call's context handed
  their query to the chat's profile builder WITHOUT a vector — which then
  served the ten most RECENT memories whatever was asked (found 2026-09-24).

They now all come here. Two rules are load-bearing:

- the query is embedded as a KEY (``is_conversational=False``): the triviality
  patterns of chat lines collide with real names and short questions;
- the vector is computed BEFORE a session opens, and the session serves one
  query (ADR-304: no transaction held across a network call).

The embedding's cost is recorded by the embeddings wrapper into whatever
``TrackingContext`` is active — the chat turn, the routine run, the phone call
— so no caller hands tracking of its own.
"""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.user_message_embedding import get_or_compute_embedding


async def embed_lookup(query: str, *, user_id: str | None = None) -> list[float] | None:
    """The vector of a lookup query.

    Args:
        query: What is looked up — a subject, a name, a question.
        user_id: Owner, for logs.

    Returns:
        The vector, or None when none could be computed (empty query, provider
        failure) — which means « could not look », never « nothing matched ».
    """
    return await get_or_compute_embedding(message=query, user_id=user_id, is_conversational=False)


async def search_memories(
    user_id: UUID,
    query: str,
    *,
    limit: int,
    min_score: float,
    categories: Collection[str] | None = None,
) -> list[tuple[Memory, float]] | None:
    """The owner's live memories most relevant to a lookup.

    Args:
        user_id: Whose memories.
        query: What is looked up.
        limit: Most rows returned.
        min_score: Similarity floor (0.0-1.0).
        categories: Families to keep; None or empty keeps every family.

    Returns:
        ``(memory, similarity)`` pairs, best first — an empty list when the
        search ran and nothing matched, None when it could not run.
    """
    embedding = await embed_lookup(query, user_id=str(user_id))
    if not embedding:
        return None
    async with get_db_context() as db:
        return await MemoryRepository(db).search_by_relevance(
            user_id=user_id,
            query_embedding=embedding,
            limit=limit,
            min_score=min_score,
            categories=categories,
        )


__all__ = ["embed_lookup", "search_memories"]
