"""
Service layer for the Memories domain.

Handles CRUD operations with automatic embedding generation and
char_count computation. Used by:
- Memory extraction pipeline (background create/update/delete)
- Memory API router (manual CRUD)
- Memory cleanup scheduler (delete)

Follows the same pattern as JournalService:
- Constructor receives AsyncSession and creates repository
- Embedding auto-generated on create and re-generated on content change
- Structured logging on all operations

Phase: v1.14.0 — Memory migration to PostgreSQL custom
Created: 2026-03-30
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Embedding Helpers
# =============================================================================


def _build_memory_embedding_text(content: str, trigger_topic: str) -> str:
    """Build text for embedding generation from memory fields.

    Combines content and trigger_topic into a single string optimized
    for semantic search. The trigger_topic acts as a keyword anchor
    similar to journal's search_hints.

    Args:
        content: Memory content text (first-person formulation).
        trigger_topic: Trigger keyword for this memory.

    Returns:
        Combined text for embedding.
    """
    parts = [content]
    if trigger_topic and trigger_topic.strip():
        parts.append(trigger_topic)
    return " | ".join(parts)


async def _generate_embedding(text: str) -> list[float] | None:
    """Generate OpenAI embedding for memory content.

    Uses the shared TrackedOpenAIEmbeddings singleton (same model as
    journal and interest embeddings: text-embedding-3-small, 1536 dims).

    Returns None on failure (graceful degradation — memory works
    without embedding but won't appear in semantic search).

    Args:
        text: Text to embed (content + trigger_topic).

    Returns:
        1536-dim float vector, or None on error.
    """
    try:
        from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

        embeddings = get_memory_embeddings()
        return await embeddings.aembed_query(text)
    except Exception as e:
        logger.warning(
            "memory_embedding_generation_failed",
            error=str(e),
            error_type=type(e).__name__,
            text_length=len(text),
        )
        return None


# =============================================================================
# Memory Service
# =============================================================================


class MemoryService:
    """Business logic for memory management.

    Handles CRUD operations with automatic char_count computation
    and embedding generation. Same pattern as JournalService.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            db: AsyncSession for database operations.
        """
        self.db = db
        self.repo = MemoryRepository(db)

    # =========================================================================
    # Create
    # =========================================================================

    async def create_memory(
        self,
        user_id: UUID,
        content: str,
        category: str,
        emotional_weight: int = 0,
        trigger_topic: str = "",
        usage_nuance: str = "",
        importance: float = 0.7,
    ) -> Memory:
        """Create a new memory with auto-generated embedding.

        Args:
            user_id: Owner user UUID.
            content: Memory text (first-person, max 500 chars).
            category: Memory category (preference, personal, etc.).
            emotional_weight: Emotional intensity (-10 to +10).
            trigger_topic: Keyword trigger for search.
            usage_nuance: How the assistant should use this info.
            importance: Importance score (0.0 to 1.0).

        Returns:
            Created Memory with embedding.
        """
        char_count = len(content)

        # Generate embedding from content + trigger_topic
        embed_text = _build_memory_embedding_text(content, trigger_topic)
        embedding = await _generate_embedding(embed_text)

        memory = Memory(
            user_id=user_id,
            content=content,
            category=category,
            emotional_weight=emotional_weight,
            trigger_topic=trigger_topic,
            usage_nuance=usage_nuance,
            importance=importance,
            embedding=embedding,
            char_count=char_count,
        )

        created = await self.repo.create(memory)

        logger.info(
            "memory_created",
            user_id=str(user_id),
            memory_id=str(created.id),
            category=category,
            content_preview=content[:50],
            char_count=char_count,
            has_embedding=embedding is not None,
        )

        return created

    # =========================================================================
    # Update
    # =========================================================================

    async def update_memory(
        self,
        memory: Memory,
        content: str | None = None,
        category: str | None = None,
        emotional_weight: int | None = None,
        trigger_topic: str | None = None,
        usage_nuance: str | None = None,
        importance: float | None = None,
    ) -> Memory:
        """Update a memory. Re-embeds if content or trigger_topic changed.

        Only updates fields that are provided (not None). Mirrors the
        PATCH semantics of the API.

        Args:
            memory: Existing Memory instance to update.
            content: New content (triggers re-embedding).
            category: New category.
            emotional_weight: New emotional weight.
            trigger_topic: New trigger topic (triggers re-embedding).
            usage_nuance: New usage nuance.
            importance: New importance score.

        Returns:
            Updated Memory.
        """
        content_changed = False

        if content is not None and content != memory.content:
            memory.content = content
            memory.char_count = len(content)
            content_changed = True

        if category is not None:
            memory.category = category

        if emotional_weight is not None:
            memory.emotional_weight = emotional_weight

        if trigger_topic is not None and trigger_topic != memory.trigger_topic:
            memory.trigger_topic = trigger_topic
            content_changed = True

        if usage_nuance is not None:
            memory.usage_nuance = usage_nuance

        if importance is not None:
            memory.importance = importance

        # Re-embed if content or trigger_topic changed
        if content_changed:
            embed_text = _build_memory_embedding_text(memory.content, memory.trigger_topic)
            memory.embedding = await _generate_embedding(embed_text)

        updated = await self.repo.update(memory)

        logger.info(
            "memory_updated",
            memory_id=str(memory.id),
            content_changed=content_changed,
            re_embedded=content_changed,
        )

        return updated

    # =========================================================================
    # Delete
    # =========================================================================

    async def delete_memory(self, memory: Memory) -> None:
        """Delete a memory.

        Args:
            memory: Memory instance to delete.
        """
        memory_id = str(memory.id)
        category = memory.category
        await self.repo.delete(memory)

        logger.info(
            "memory_deleted",
            memory_id=memory_id,
            category=category,
        )
