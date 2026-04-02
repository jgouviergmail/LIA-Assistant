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


async def _generate_document_embedding(text: str) -> list[float] | None:
    """Generate embedding for document storage (task_type=RETRIEVAL_DOCUMENT).

    Uses GeminiRetrievalEmbeddings which automatically applies
    task_type=RETRIEVAL_DOCUMENT via aembed_documents.

    Returns None on failure (graceful degradation — memory works
    without embedding but won't appear in semantic search).

    Args:
        text: Text to embed for storage.

    Returns:
        1536-dim float vector, or None on error.
    """
    try:
        from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

        embeddings = get_memory_embeddings()
        results = await embeddings.aembed_documents([text])
        return results[0] if results else None
    except Exception as e:
        logger.warning(
            "memory_embedding_generation_failed",
            error=str(e),
            error_type=type(e).__name__,
            text_length=len(text),
        )
        return None


async def _generate_dual_embeddings(
    content: str,
    trigger_topic: str,
) -> tuple[list[float] | None, list[float] | None]:
    """Generate separate embeddings for content and trigger_topic.

    Restores the multi-vector strategy from the old LangGraph store
    where content and trigger_topic were indexed as separate vectors.
    This prevents signal dilution when searching for keyword-level
    matches (e.g., "ma femme" matching trigger_topic "femme épouse famille").

    Both calls go through GeminiRetrievalEmbeddings which tracks tokens
    and costs automatically (Prometheus + DB persistence).

    Args:
        content: Memory content text (first-person formulation).
        trigger_topic: Keyword trigger for this memory.

    Returns:
        Tuple of (content_embedding, keyword_embedding).
        keyword_embedding is None if trigger_topic is empty.
    """
    content_embedding = await _generate_document_embedding(content)

    keyword_embedding: list[float] | None = None
    if trigger_topic and trigger_topic.strip():
        keyword_embedding = await _generate_document_embedding(trigger_topic)

    return content_embedding, keyword_embedding


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

        # Generate dual embeddings: content + trigger_topic separately
        embedding, keyword_embedding = await _generate_dual_embeddings(content, trigger_topic)

        memory = Memory(
            user_id=user_id,
            content=content,
            category=category,
            emotional_weight=emotional_weight,
            trigger_topic=trigger_topic,
            usage_nuance=usage_nuance,
            importance=importance,
            embedding=embedding,
            keyword_embedding=keyword_embedding,
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
            memory.embedding, memory.keyword_embedding = await _generate_dual_embeddings(
                memory.content, memory.trigger_topic
            )

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
