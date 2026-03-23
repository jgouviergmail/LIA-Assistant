"""
Journal context builder for prompt injection.

Builds a formatted journal context block for injection into response
and planner prompts. Combines two retrieval strategies:
1. Semantic search (pgvector cosine distance on OpenAI embeddings) for topically relevant entries
2. Temporal recency for continuity of the assistant's latest reflections

Two distinct calls in the pipeline:
- Response: query = last user message (tone, formulation)
- Planner: query = user goal (reasoning, learnings)

Design decisions:
- min_score prefiltering: entries below threshold are discarded
- Recent entries always injected (up to N), deduplicated with semantic results
- User's max_chars setting loaded from DB (not available in node scope)
- Truncation respects max_chars budget
- Returns debug data alongside context for the debug panel
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.journals.constants import JOURNAL_MOOD_EMOJI
from src.domains.journals.models import JournalEntry
from src.domains.journals.repository import JournalEntryRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _fire_and_forget_injection_tracking(entry_ids: list[UUID]) -> None:
    """
    Launch non-blocking injection count update for tracked entries.

    Uses a new DB session (the caller's session may be closed by the time
    this executes) via safe_fire_and_forget.

    Args:
        entry_ids: UUIDs of entries that were injected into a prompt
    """
    from src.infrastructure.async_utils import safe_fire_and_forget

    async def _track() -> None:
        from src.infrastructure.database import get_db_context

        try:
            async with get_db_context() as db:
                repo = JournalEntryRepository(db)
                await repo.increment_injection_counts(entry_ids)
        except Exception as e:
            logger.warning(
                "journal_injection_tracking_failed",
                entry_count=len(entry_ids),
                error=str(e),
            )

    safe_fire_and_forget(_track(), name="journal_injection_tracking")


async def build_journal_context(
    user_id: UUID | str,
    query: str,
    db: AsyncSession,
    include_debug: bool = False,
    run_id: str | None = None,
    session_id: str | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    """
    Build journal context block for prompt injection.

    Combines semantic search results with the N most recent entries
    to provide both topical relevance and temporal continuity.

    Args:
        user_id: User UUID (str or UUID)
        query: Search query (last user message for response, goal for planner)
        db: Database session
        include_debug: If True, returns debug details for the debug panel
        run_id: Pipeline run ID for embedding cost attribution to message
        session_id: Session ID for embedding cost logging

    Returns:
        Tuple of (formatted context string, debug data dict).
        Either or both may be None.
    """
    if isinstance(user_id, str):
        user_id = UUID(user_id)

    try:
        # Check system-level feature flag FIRST (before any DB query)
        if not settings.journals_enabled:
            return None, None

        # Load user settings from DB (not available in node scope)
        from sqlalchemy import select

        from src.domains.auth.models import User

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            return None, None

        # Check user-level feature flag
        if not getattr(user, "journals_enabled", settings.journals_enabled):
            return None, None

        max_chars = getattr(
            user, "journal_context_max_chars", settings.journal_default_context_max_chars
        )
        max_results = getattr(
            user, "journal_context_max_results", settings.journal_context_max_results
        )
        recent_count = settings.journal_context_recent_entries

        repo = JournalEntryRepository(db)

        # Semantic search (best-effort — embedding failure degrades gracefully)
        scored_entries: list[tuple[JournalEntry, float]] = []
        try:
            from src.domains.journals.embedding import get_journal_embeddings
            from src.infrastructure.llm.embedding_context import (
                clear_embedding_context,
                set_embedding_context,
            )

            # Set embedding tracking context for cost attribution
            set_embedding_context(
                user_id=str(user_id),
                session_id=session_id or "journal_search",
                run_id=run_id,
            )
            try:
                embeddings_model = get_journal_embeddings()
                query_embedding = await embeddings_model.aembed_query(query[:500])
            finally:
                clear_embedding_context()

            if query_embedding:
                min_score = settings.journal_context_min_score
                scored_entries = await repo.search_by_relevance(
                    user_id=user_id,
                    query_embedding=query_embedding,
                    limit=max_results,
                    min_score=min_score,
                )
            else:
                logger.warning(
                    "journal_context_embedding_empty",
                    user_id=str(user_id),
                )
        except Exception as embed_err:
            logger.warning(
                "journal_context_semantic_search_failed",
                user_id=str(user_id),
                error=str(embed_err),
                error_type=type(embed_err).__name__,
            )

        # Fetch recent entries for temporal continuity (always, regardless of embedding)
        recent_entries: list[tuple[JournalEntry, float | None]] = []
        if recent_count > 0:
            raw_recent = await repo.get_recent_for_user(user_id, limit=recent_count)
            # Deduplicate: exclude entries already in semantic results
            semantic_ids = {entry.id for entry, _ in scored_entries}
            for entry in raw_recent:
                if entry.id not in semantic_ids:
                    recent_entries.append((entry, None))  # None score = recent

        # Merge: recent entries first (continuity), then semantic (relevance)
        all_entries: list[tuple[JournalEntry, float | None]] = recent_entries + [
            (entry, score) for entry, score in scored_entries
        ]

        # Respect max_results budget
        all_entries = all_entries[:max_results]

        if not all_entries:
            return None, None

        # Format entries with scores, respecting max_chars budget
        lines = [
            "## CARNET DE BORD PERSONNEL",
            "These are YOUR own reflections and observations. "
            "Entries marked [recent] are your latest thoughts; scored entries match "
            "the current context semantically.",
            "Use freely whichever notes seem pertinent to you.",
            "",
        ]
        current_chars = sum(len(line) for line in lines)

        # Debug data collection and injection tracking
        debug_entries: list[dict[str, Any]] = []
        injected_ids: list[UUID] = []  # UUIDs of entries actually injected
        injected_count = 0

        for entry, score in all_entries:
            # Format entry line
            date_str = entry.created_at.strftime("%Y-%m-%d")
            theme_label = entry.theme.replace("_", " ")
            mood_emoji = JOURNAL_MOOD_EMOJI.get(entry.mood, "")

            # Score label: numeric for semantic, [recent] for temporal
            score_label = f"score={score:.2f}" if score is not None else "recent"

            content_preview = entry.content
            line = (
                f"- [{score_label} | {date_str} | {theme_label} | {mood_emoji}] "
                f"**{entry.title}** — {content_preview}"
            )

            # Collect debug data for each entry (before budget check)
            if include_debug:
                debug_entries.append(
                    {
                        "theme": entry.theme,
                        "title": entry.title[:25],
                        "full_title": entry.title,
                        "content": entry.content,
                        "score": round(score, 4) if score is not None else None,
                        "mood": entry.mood,
                        "char_count": entry.char_count,
                        "source": entry.source,
                        "date": date_str,
                        "injected": True,  # Will be set to False if budget exceeded
                    }
                )

            # Check budget
            if current_chars + len(line) > max_chars:
                # Try with truncated content
                available = max_chars - current_chars - 100  # Reserve for header
                if available > 50:
                    content_preview = entry.content[: available - 50] + "..."
                    line = (
                        f"- [{score_label} | {date_str} | {theme_label} | {mood_emoji}] "
                        f"**{entry.title}** — {content_preview}"
                    )
                    lines.append(line)
                    injected_ids.append(entry.id)
                    injected_count += 1
                else:
                    # Mark as not injected in debug
                    if include_debug and debug_entries:
                        debug_entries[-1]["injected"] = False
                break  # Budget exhausted

            lines.append(line)
            current_chars += len(line) + 1  # +1 for newline
            injected_ids.append(entry.id)
            injected_count += 1

        result = "\n".join(lines)

        # Build debug data
        debug_data: dict[str, Any] | None = None
        if include_debug:
            debug_data = {
                "entries_found": len(scored_entries),
                "entries_recent": len(recent_entries),
                "entries_injected": injected_count,
                "total_chars_injected": len(result),
                "max_chars_budget": max_chars,
                "max_results_setting": max_results,
                "entries": debug_entries,
            }

        logger.info(
            "journal_context_built",
            user_id=str(user_id),
            semantic_count=len(scored_entries),
            recent_count=len(recent_entries),
            entries_injected=injected_count,
            result_chars=len(result),
            max_chars=max_chars,
            semantic_scores=[round(s, 4) for _, s in scored_entries] if scored_entries else [],
            has_debug_data=debug_data is not None,
            debug_entries_count=len(debug_data.get("entries", [])) if debug_data else 0,
        )

        # Fire-and-forget injection tracking (non-blocking)
        if injected_ids:
            _fire_and_forget_injection_tracking(injected_ids)

        return result, debug_data

    except Exception as e:
        # Graceful degradation — context injection failure must not break the prompt
        logger.warning(
            "journal_context_build_failed",
            user_id=str(user_id),
            error=str(e),
            error_type=type(e).__name__,
        )
        return None, None
