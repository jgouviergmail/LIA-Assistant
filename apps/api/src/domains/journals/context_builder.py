"""
Journal context builder for prompt injection.

Builds a formatted journal context block for injection into response
and planner prompts. Uses semantic search (cosine similarity on E5-small
embeddings) to find the most relevant entries for the current context.

Two distinct calls in the pipeline:
- Response: query = last user message (tone, formulation)
- Planner: query = user goal + intent (reasoning, learnings)

Design decisions:
- No minimum score: all results returned WITH scores (assistant decides relevance)
- User's max_chars setting loaded from DB (not available in node scope)
- Truncation respects max_chars budget
- Returns debug data alongside context for the debug panel
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.journals.constants import JOURNAL_MOOD_EMOJI
from src.domains.journals.repository import JournalEntryRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def build_journal_context(
    user_id: UUID | str,
    query: str,
    db: AsyncSession,
    include_debug: bool = False,
) -> tuple[str | None, dict[str, Any] | None]:
    """
    Build journal context block for prompt injection.

    Performs semantic search on journal entries and formats results
    with relevance scores for the LLM to decide what to use.

    Args:
        user_id: User UUID (str or UUID)
        query: Search query (last user message for response, goal+intent for planner)
        db: Database session
        include_debug: If True, returns debug details for the debug panel

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
        if not getattr(user, "journals_enabled", False):
            return None, None

        max_chars = getattr(
            user, "journal_context_max_chars", settings.journal_default_context_max_chars
        )
        max_results = getattr(
            user, "journal_context_max_results", settings.journal_context_max_results
        )

        # Generate query embedding
        from src.infrastructure.llm.local_embeddings import get_local_embeddings

        embeddings_model = get_local_embeddings()
        query_embedding = embeddings_model.embed_query(query[:500])  # Truncate query

        if not query_embedding:
            logger.warning(
                "journal_context_embedding_failed",
                user_id=str(user_id),
            )
            return None, None

        # Semantic search with min_score prefiltering
        min_score = settings.journal_context_min_score
        repo = JournalEntryRepository(db)
        scored_entries = await repo.search_by_relevance(
            user_id=user_id,
            query_embedding=query_embedding,
            limit=max_results,
            min_score=min_score,
        )

        if not scored_entries:
            return None, None

        # Format entries with scores, respecting max_chars budget
        lines = [
            "## CARNET DE BORD PERSONNEL",
            "These are YOUR own reflections and observations. "
            "Scores indicate relevance to the current context.",
            "Use freely whichever notes seem pertinent to you.",
            "",
        ]
        current_chars = sum(len(line) for line in lines)

        # Debug data collection
        debug_entries: list[dict[str, Any]] = []
        injected_count = 0

        for entry, score in scored_entries:
            # Format entry line
            date_str = entry.created_at.strftime("%Y-%m-%d")
            theme_label = entry.theme.replace("_", " ")
            mood_emoji = JOURNAL_MOOD_EMOJI.get(entry.mood, "")

            # Truncate content if needed
            content_preview = entry.content
            line = (
                f"- [score={score:.2f} | {date_str} | {theme_label} | {mood_emoji}] "
                f"**{entry.title}** — {content_preview}"
            )

            # Collect debug data for each scored entry (before budget check)
            if include_debug:
                debug_entries.append(
                    {
                        "theme": entry.theme,
                        "title": entry.title[:25],
                        "score": round(score, 4),
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
                        f"- [score={score:.2f} | {date_str} | {theme_label} | {mood_emoji}] "
                        f"**{entry.title}** — {content_preview}"
                    )
                    lines.append(line)
                    injected_count += 1
                else:
                    # Mark as not injected in debug
                    if include_debug and debug_entries:
                        debug_entries[-1]["injected"] = False
                break  # Budget exhausted

            lines.append(line)
            current_chars += len(line) + 1  # +1 for newline
            injected_count += 1

        result = "\n".join(lines)

        # Build debug data
        debug_data: dict[str, Any] | None = None
        if include_debug:
            debug_data = {
                "entries_found": len(scored_entries),
                "entries_injected": injected_count,
                "total_chars_injected": len(result),
                "max_chars_budget": max_chars,
                "max_results_setting": max_results,
                "entries": debug_entries,
            }

        logger.debug(
            "journal_context_built",
            user_id=str(user_id),
            entries_count=len(scored_entries),
            entries_injected=injected_count,
            result_chars=len(result),
            max_chars=max_chars,
        )

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
