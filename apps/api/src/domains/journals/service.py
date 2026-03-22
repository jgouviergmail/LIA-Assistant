"""
Business logic service for the Journals domain.

Provides:
- Entry CRUD with automatic char_count and embedding generation
- Size tracking (total_chars, usage percentage)
- Last cost retrieval for UI display
- Ownership validation

Embedding generation uses OpenAI text-embedding-3-small (1536d) via
TrackedOpenAIEmbeddings, with automatic token tracking via Prometheus.
Background extraction/consolidation services also use this service
for consistent char_count + embedding handling (DRY).
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_MAX_LENGTH
from src.domains.journals.models import (
    JournalEntry,
    JournalEntryMood,
    JournalEntrySource,
    JournalEntryStatus,
)
from src.domains.journals.repository import JournalEntryRepository
from src.domains.journals.schemas import JournalCostInfo, JournalSizeInfo
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def _generate_embedding(text: str) -> list[float] | None:
    """
    Generate OpenAI embedding for journal entry content.

    Uses the singleton TrackedOpenAIEmbeddings instance (lazy-loaded, thread-safe).
    Returns None on failure (graceful degradation — entry works without embedding).

    Args:
        text: Text to embed (title + content + optional search hints)

    Returns:
        1536-dim float vector, or None on error
    """
    try:
        from src.domains.journals.embedding import get_journal_embeddings

        embeddings = get_journal_embeddings()
        return await embeddings.aembed_query(text)
    except Exception as e:
        logger.warning(
            "journal_embedding_generation_failed",
            error=str(e),
            error_type=type(e).__name__,
            text_length=len(text),
        )
        return None


def _build_embedding_text(
    title: str,
    content: str,
    search_hints: list[str] | None = None,
) -> str:
    """
    Build text for embedding generation from entry fields.

    Combines title, content, and optional search hints into a single
    string optimized for semantic search. Search hints bridge the gap
    between the assistant's introspective vocabulary and the user's
    direct vocabulary.

    Args:
        title: Entry title
        content: Entry content
        search_hints: Optional LLM-generated keywords in user vocabulary

    Returns:
        Combined text for embedding
    """
    hints_text = f" Context: {' '.join(search_hints)}" if search_hints else ""
    return f"{title}. {content}.{hints_text}"


class JournalService:
    """
    Business logic for journal entry management.

    Handles CRUD operations with automatic char_count computation
    and embedding generation. Used by both API endpoints (manual CRUD)
    and background services (extraction/consolidation) for consistency.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session."""
        self.db = db
        self.repo = JournalEntryRepository(db)

    # =========================================================================
    # Create
    # =========================================================================

    async def create_entry(
        self,
        user_id: UUID,
        theme: str,
        title: str,
        content: str,
        mood: str = JournalEntryMood.REFLECTIVE.value,
        source: str = JournalEntrySource.MANUAL.value,
        session_id: str | None = None,
        personality_code: str | None = None,
        max_entry_chars: int = JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
        search_hints: list[str] | None = None,
    ) -> JournalEntry:
        """
        Create a new journal entry with char_count and embedding.

        Args:
            user_id: Owner user UUID
            theme: Thematic category (JournalTheme value)
            title: Short descriptive title
            content: Full entry content
            mood: Emotional tone (JournalEntryMood value)
            source: Origin (conversation/consolidation/manual)
            session_id: Conversation session ID (for extraction traceability)
            personality_code: Active personality code when entry was written
            max_entry_chars: Max content length (safety net for LLM output)
            search_hints: LLM-generated keywords bridging user vocabulary to content

        Returns:
            Created JournalEntry with ID, char_count, and embedding
        """
        # Truncate content if exceeding max (safety net for LLM output)
        if len(content) > max_entry_chars:
            original_length = len(content)
            content = content[:max_entry_chars]
            logger.warning(
                "journal_entry_content_truncated",
                user_id=str(user_id),
                original_length=original_length,
                max_length=max_entry_chars,
            )

        char_count = len(content)

        # Generate embedding from title + content + search hints for semantic search
        embedding = await _generate_embedding(_build_embedding_text(title, content, search_hints))

        entry = JournalEntry(
            user_id=user_id,
            theme=theme,
            title=title,
            content=content,
            mood=mood,
            status=JournalEntryStatus.ACTIVE.value,
            source=source,
            session_id=session_id,
            personality_code=personality_code,
            char_count=char_count,
            embedding=embedding,
            search_hints=search_hints,
        )

        return await self.repo.create(entry)

    # =========================================================================
    # Update
    # =========================================================================

    async def update_entry(
        self,
        entry: JournalEntry,
        title: str | None = None,
        content: str | None = None,
        mood: str | None = None,
        max_entry_chars: int = JOURNAL_ENTRY_CONTENT_MAX_LENGTH,
        search_hints: list[str] | None = None,
    ) -> JournalEntry:
        """
        Update an existing journal entry.

        Recalculates char_count and regenerates embedding if content changes.

        Args:
            entry: Existing JournalEntry instance
            title: New title (None = keep current)
            content: New content (None = keep current)
            mood: New mood (None = keep current)
            max_entry_chars: Max content length (safety net for LLM output)
            search_hints: New search hints (None = keep current)

        Returns:
            Updated JournalEntry
        """
        content_changed = False

        if title is not None:
            entry.title = title
            content_changed = True

        if content is not None:
            if len(content) > max_entry_chars:
                content = content[:max_entry_chars]
            entry.content = content
            entry.char_count = len(content)
            content_changed = True

        if mood is not None:
            entry.mood = mood

        if search_hints is not None:
            entry.search_hints = search_hints
            content_changed = True  # Hints affect embedding text

        # Regenerate embedding if title, content, or search_hints changed
        if content_changed:
            entry.embedding = await _generate_embedding(
                _build_embedding_text(entry.title, entry.content, entry.search_hints)
            )

        return await self.repo.update(entry)

    # =========================================================================
    # Delete
    # =========================================================================

    async def delete_entry(self, entry: JournalEntry) -> None:
        """Delete a single journal entry."""
        await self.repo.delete_entry(entry)

    async def delete_all_for_user(self, user_id: UUID) -> int:
        """Delete all journal entries for a user (GDPR)."""
        return await self.repo.delete_all_for_user(user_id)

    # =========================================================================
    # Read / Query
    # =========================================================================

    async def get_entry_for_user(self, entry_id: UUID, user_id: UUID) -> JournalEntry | None:
        """Get entry by ID with ownership check."""
        return await self.repo.get_by_id_for_user(entry_id, user_id)

    async def list_entries(
        self,
        user_id: UUID,
        theme: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[JournalEntry], int]:
        """List entries with optional filters and pagination."""
        return await self.repo.get_for_user(user_id, theme, status, limit, offset)

    async def get_all_active(self, user_id: UUID) -> list[JournalEntry]:
        """Get all active entries for a user (for consolidation)."""
        return await self.repo.get_all_active_for_user(user_id)

    # =========================================================================
    # Size Tracking
    # =========================================================================

    async def get_size_info(self, user_id: UUID, max_total_chars: int) -> JournalSizeInfo:
        """
        Get size usage information.

        Args:
            user_id: User UUID
            max_total_chars: User's configured maximum (from user model)

        Returns:
            JournalSizeInfo with total_chars, max, and usage percentage
        """
        total_chars = await self.repo.get_total_chars(user_id)
        usage_pct = (total_chars / max_total_chars * 100) if max_total_chars > 0 else 0.0

        return JournalSizeInfo(
            total_chars=total_chars,
            max_total_chars=max_total_chars,
            usage_pct=round(usage_pct, 1),
        )

    async def get_theme_counts(self, user_id: UUID) -> dict[str, int]:
        """Get active entry counts grouped by theme."""
        return await self.repo.count_by_theme(user_id)

    # =========================================================================
    # Cost Info
    # =========================================================================

    @staticmethod
    def build_cost_info_from_user(user: object) -> JournalCostInfo:
        """
        Build JournalCostInfo from User model fields.

        Args:
            user: User model instance with journal_last_cost_* fields

        Returns:
            JournalCostInfo with last intervention cost details
        """
        return JournalCostInfo(
            tokens_in=getattr(user, "journal_last_cost_tokens_in", None),
            tokens_out=getattr(user, "journal_last_cost_tokens_out", None),
            cost_eur=getattr(user, "journal_last_cost_eur", None),
            timestamp=getattr(user, "journal_last_cost_at", None),
            source=getattr(user, "journal_last_cost_source", None),
        )

    # =========================================================================
    # Archive (used by extraction/consolidation via prompt-driven lifecycle)
    # =========================================================================

    async def archive_entry(self, entry: JournalEntry) -> JournalEntry:
        """Archive an entry (soft status change, data preserved)."""
        entry.status = JournalEntryStatus.ARCHIVED.value
        return await self.repo.update(entry)
