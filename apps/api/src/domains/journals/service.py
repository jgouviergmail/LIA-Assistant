"""
Business logic service for the Journals domain.

Provides:
- Entry CRUD with automatic char_count and embedding generation
- Size tracking (total_chars, usage percentage)
- Last cost retrieval for UI display
- Ownership validation

Embedding generation uses Gemini gemini-embedding-001 (1536d) via
GeminiRetrievalEmbeddings, with automatic token tracking via Prometheus.
Background extraction/consolidation services also use this service
for consistent char_count + embedding handling (DRY).
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.consolidation_controls import check_consolidation_embedding
from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_MAX_LENGTH
from src.domains.journals.evidence import apply_update, clamp_confidence, stale_rule
from src.domains.journals.lifecycle import lock_journal_owner, mark_journal_changed
from src.domains.journals.models import (
    JournalEntry,
    JournalEntryConfidence,
    JournalEntryLevel,
    JournalEntryMood,
    JournalEntrySource,
    JournalEntryStatus,
)
from src.domains.journals.repository import JournalEntryRepository
from src.domains.journals.schemas import JournalCostInfo, JournalSizeInfo
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

JournalEmbeddings = tuple[list[float] | None, list[float] | None]


_clamp_confidence = clamp_confidence


async def _generate_document_embedding(text: str) -> list[float] | None:
    """Generate embedding for document storage (task_type=RETRIEVAL_DOCUMENT).

    Uses GeminiRetrievalEmbeddings which automatically applies
    task_type=RETRIEVAL_DOCUMENT via aembed_documents.

    Returns None on failure (graceful degradation — entry works without embedding).

    Args:
        text: Text to embed for storage.

    Returns:
        1536-dim float vector, or None on error.
    """
    await check_consolidation_embedding()
    try:
        from src.domains.journals.embedding import get_journal_embeddings

        embeddings = get_journal_embeddings()
        results = await embeddings.aembed_documents([text])
        return results[0] if results else None
    except Exception as e:
        logger.warning(
            "journal_embedding_generation_failed",
            error=str(e),
            error_type=type(e).__name__,
            text_length=len(text),
        )
        return None


async def _generate_dual_embeddings(
    title: str,
    content: str,
    search_hints: list[str] | None = None,
) -> tuple[list[float] | None, list[float] | None]:
    """Generate separate embeddings for content and search_hints.

    Stores title+content in the main embedding and search_hints keywords
    in a separate keyword_embedding. This prevents signal dilution when
    searching for keyword-level matches.

    Both calls go through GeminiRetrievalEmbeddings which tracks tokens
    and costs automatically (Prometheus + DB persistence).

    Args:
        title: Entry title.
        content: Entry content.
        search_hints: Optional LLM-generated keywords in user vocabulary.

    Returns:
        Tuple of (content_embedding, keyword_embedding).
        keyword_embedding is None if search_hints is empty.
    """
    content_text = f"{title}. {content}."
    content_embedding = await _generate_document_embedding(content_text)

    keyword_embedding: list[float] | None = None
    if search_hints:
        hints_text = " ".join(search_hints)
        if hints_text.strip():
            keyword_embedding = await _generate_document_embedding(hints_text)

    return content_embedding, keyword_embedding


async def prepare_embeddings(
    title: str, content: str, search_hints: list[str] | None = None
) -> JournalEmbeddings:
    """Prepare a write outside the caller's atomic settlement lock."""
    return await _generate_dual_embeddings(title, content, search_hints)


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
        confidence: str = JournalEntryConfidence.MEDIUM.value,
        level: str = JournalEntryLevel.L1.value,
        precomputed_embeddings: JournalEmbeddings | None = None,
        entry_id: UUID | None = None,
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
            confidence: Epistemic status — defaults to "medium" for fresh entries.
                The extractor LLM may set "low" for new hypotheses.
            level: Abstraction level — defaults to "L1" (operational directive).
                The LLM may set "L0" for raw observations, "L2" for patterns, or
                "L3" for portrait facets.

        Returns:
            Created JournalEntry with ID, char_count, and embedding
        """
        if len(content) > max_entry_chars:
            raise ValueError("Journal content exceeds the configured entry limit")
        if source == JournalEntrySource.CONVERSATION.value and level not in ("L0", "L1"):
            raise ValueError("Conversation extraction cannot create consolidated journal levels")

        char_count = len(content)

        # Epistemic clamp: a fresh L0/L1 has zero evidence by definition (B-06).
        confidence = _clamp_confidence(confidence, level, evidence_count=0, source="create")
        if source == JournalEntrySource.CONSOLIDATION.value and confidence == "high":
            # Converging supports authorize a synthesis, not its validation.
            confidence = "medium"

        # Generate dual embeddings: title+content + search_hints separately
        embedding, keyword_embedding = (
            precomputed_embeddings
            if precomputed_embeddings is not None
            else await _generate_dual_embeddings(title, content, search_hints)
        )

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
            keyword_embedding=keyword_embedding,
            search_hints=search_hints,
            confidence=confidence,
            level=level,
        )
        if entry_id is not None:
            entry.id = entry_id

        await lock_journal_owner(self.db, user_id)
        created = await self.repo.create(entry)
        await mark_journal_changed(self.db, user_id)
        return created

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
        confidence: str | None = None,
        evidence_outcome: str | None = None,
        level: str | None = None,
        theme: str | None = None,
        event_key: str | None = None,
        evidence_source: str | None = None,
        expected_revision: int | None = None,
        precomputed_embeddings: JournalEmbeddings | None = None,
    ) -> JournalEntry:
        """Apply a revision-checked update and one distinct reaction event.

        Different content is a new proposition: its revision advances and its
        validation resets. Title/hint edits retain validation. Embeddings are
        prepared before the owner/entry locks; no provider call holds them.
        An outcome about replaced words cannot validate the new proposition.
        """
        if content is not None and len(content) > max_entry_chars:
            raise ValueError("Journal content exceeds the configured entry limit")
        changes: dict[str, Any] = {
            key: value
            for key, value in {
                "title": title,
                "content": content,
                "mood": mood,
                "search_hints": search_hints,
                "level": level,
                "theme": theme,
            }.items()
            if value is not None
        }
        if content is not None:
            changes["char_count"] = len(content)
        if any(
            value is not None and value != getattr(entry, key)
            for key, value in (
                ("title", title),
                ("content", content),
                ("search_hints", search_hints),
            )
        ):
            embedding, keyword_embedding = (
                precomputed_embeddings
                if precomputed_embeddings is not None
                else await _generate_dual_embeddings(
                    title if title is not None else entry.title,
                    content if content is not None else entry.content,
                    search_hints if search_hints is not None else entry.search_hints,
                )
            )
            changes["embedding"], changes["keyword_embedding"] = embedding, keyword_embedding
        updated = await apply_update(
            self.db,
            entry,
            changes,
            confidence=confidence,
            evidence_outcome=evidence_outcome,
            event_key=event_key,
            evidence_source=evidence_source,
            expected_revision=expected_revision,
        )
        return await self.repo.update(updated)

    async def merge_entries(
        self,
        winner: JournalEntry,
        source_ids: list[UUID],
        expected_revisions: dict[str, int],
        precomputed_embeddings: JournalEmbeddings | None = None,
    ) -> JournalEntry:
        """Merge equivalent propositions with deterministic source-event union."""
        from src.domains.journals.merging import merge_entries, union_hints

        sources = [
            await self.repo.get_by_id_for_user(identifier, winner.user_id)
            for identifier in sorted(set(source_ids) - {winner.id})
        ]
        if any(source is None for source in sources):
            raise stale_rule()
        prepared_hints = union_hints(
            [winner, *[source for source in sources if source is not None]]
        )
        keyword_embedding = winner.keyword_embedding
        if precomputed_embeddings is not None:
            keyword_embedding = precomputed_embeddings[1]
        elif prepared_hints != (winner.search_hints or []):
            keyword_embedding = (
                await _generate_document_embedding(" ".join(prepared_hints))
                if prepared_hints
                else None
            )

        return await merge_entries(
            self.db,
            winner,
            source_ids,
            expected_revisions,
            prepared_hints=prepared_hints,
            keyword_embedding=keyword_embedding,
        )

    async def prepare_merge_embeddings(
        self, winner: JournalEntry, sources: list[JournalEntry]
    ) -> JournalEmbeddings:
        """Prepare merged vocabulary before taking any journal write lock."""
        from src.domains.journals.merging import union_hints

        hints = union_hints([winner, *sources])
        keyword = winner.keyword_embedding
        if hints != (winner.search_hints or []):
            keyword = await _generate_document_embedding(" ".join(hints)) if hints else None
        return winner.embedding, keyword

    # =========================================================================
    # Delete
    # =========================================================================

    async def delete_entry(self, entry: JournalEntry, expected_revision: int | None = None) -> None:
        """Delete a single journal entry."""
        await lock_journal_owner(self.db, entry.user_id)
        if expected_revision is not None:
            from sqlalchemy import select

            revision = (
                await self.db.execute(
                    select(JournalEntry.revision)
                    .where(JournalEntry.id == entry.id, JournalEntry.user_id == entry.user_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if revision != expected_revision:
                raise stale_rule()
        await self.repo.delete_entry(entry)
        await mark_journal_changed(self.db, entry.user_id)

    async def delete_all_for_user(self, user_id: UUID) -> int:
        """Delete all journal entries for a user (GDPR)."""
        await lock_journal_owner(self.db, user_id)
        deleted = await self.repo.delete_all_for_user(user_id)
        await mark_journal_changed(self.db, user_id)
        return deleted

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
