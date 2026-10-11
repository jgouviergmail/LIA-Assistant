"""
Journal context builder for prompt injection.

Builds a formatted journal context block for injection into response
and planner prompts. Combines two retrieval strategies:
1. Semantic search (pgvector cosine distance on Gemini embeddings) for
   topically relevant entries — per-user adaptive threshold (lot 7)
2. Temporal recency for continuity — DISABLED BY DEFAULT
   (``JOURNAL_CONTEXT_RECENT_ENTRIES_DEFAULT = 0``): the semantic path is
   the only active one unless the setting is raised (B-07, 2026-08-19)

Two distinct calls in the pipeline:
- Response: query = last user message (tone, formulation)
- Planner: query = user goal (reasoning, learnings)

Design decisions:
- min_score prefiltering: entries below threshold are discarded (per-user
  adaptive value inside hard bounds — see infrastructure/adaptive)
- Recent entries injected only when ``journal_context_recent_entries`` > 0
  (default 0), deduplicated with semantic results
- User's max_chars setting loaded from DB (not available in node scope)
- Whole entries respect the rendered max_chars budget, including its header
- Returns debug data alongside context for the debug panel
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.journals.constants import (
    JOURNAL_MOOD_EMOJI,
    JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS,
)
from src.domains.journals.models import JournalEntry
from src.domains.journals.repository import JournalEntryRepository
from src.infrastructure.adaptive.threshold_controller import (
    JOURNAL_INJECTION_PERIMETER,
    effective_threshold,
    observe_score,
)
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.domains.users.models import User


def _shared_embedding_matches_journal() -> bool:
    """The shared message vector uses the memory model's query task.

    Equal widths alone do not make two models' vector spaces compatible.
    Both retrieval wrappers use RETRIEVAL_QUERY for this text.
    """
    return bool(
        settings.memory_embedding_model.removeprefix("models/")
        == settings.journal_embedding_model.removeprefix("models/")
        and settings.memory_embedding_dimensions == settings.journal_embedding_dimensions
    )


def track_injected_entries(entry_ids: list[UUID]) -> None:
    """
    Launch non-blocking injection count update for tracked entries.

    Uses a new DB session (the caller's session may be closed by the time
    this executes) via safe_fire_and_forget. Public since ADR-318: an entry
    the journal lookup tool returns reached a prompt exactly as an injected
    one did, and the consolidation reads the count as that entry's usefulness.

    Args:
        entry_ids: UUIDs of entries that were injected into a prompt
    """

    async def _track() -> None:
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


async def _authorized_user(db: AsyncSession, user_id: UUID) -> User | None:
    """Check the system gate before SQL, then the account's current consent."""
    if not settings.journals_enabled or not await is_capability_enabled(
        PlatformCapability.JOURNALS
    ):
        return None
    from sqlalchemy import select

    from src.domains.users.models import User

    result = await db.execute(
        select(User).where(User.id == user_id).execution_options(populate_existing=True)
    )
    user: User | None = result.scalar_one_or_none()
    if (
        user is None
        or not user.journals_enabled
        or not user.is_active
        or user.deleted_at is not None
    ):
        return None
    return user


def _context_limits(
    user: User,
    max_results_override: int | None,
    exclude_levels: list[str] | None,
) -> tuple[int, int, int, list[str]]:
    """Count-only callers remain semantic-only; explicit level overrides survive."""
    max_chars = getattr(
        user, "journal_context_max_chars", settings.journal_default_context_max_chars
    )
    max_results = getattr(user, "journal_context_max_results", settings.journal_context_max_results)
    recent_count = settings.journal_context_recent_entries
    if max_results_override is not None:
        max_results = max_results_override
        recent_count = 0
    excluded = (
        JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS if exclude_levels is None else exclude_levels
    )
    return max_chars, max_results, recent_count, excluded


async def _query_embedding(
    user_id: UUID,
    query: str,
    embedding: list[float] | None,
    run_id: str | None,
    session_id: str | None,
) -> list[float] | None:
    """Attribute fallback embedding work and clear its context even on failure."""
    if embedding is not None:
        return embedding
    from src.domains.journals.embedding import get_journal_embeddings
    from src.infrastructure.llm.embedding_context import (
        clear_embedding_context,
        set_embedding_context,
    )

    set_embedding_context(
        user_id=str(user_id), session_id=session_id or "journal_search", run_id=run_id
    )
    try:
        result: list[float] | None = await get_journal_embeddings().aembed_query(
            query[:USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH]
        )
        return result
    finally:
        clear_embedding_context()


async def _semantic_entries(
    repo: JournalEntryRepository,
    user_id: UUID,
    query: str,
    embedding: list[float] | None,
    max_results: int,
    excluded: list[str],
    run_id: str | None,
    session_id: str | None,
) -> list[tuple[JournalEntry, float]]:
    """Embedding/search failures leave temporal retrieval available."""
    entries: list[tuple[JournalEntry, float]] = []
    try:
        embedding = await _query_embedding(user_id, query, embedding, run_id, session_id)
        if not embedding:
            logger.warning("journal_context_embedding_empty", user_id=str(user_id))
            return []
        min_score = await effective_threshold(user_id, JOURNAL_INJECTION_PERIMETER)
        observed: list[float] = []
        entries = await repo.search_by_relevance(
            user_id=user_id,
            query_embedding=embedding,
            limit=max_results,
            min_score=min_score,
            exclude_levels=excluded,
            operational_only=True,
            observed_scores=observed,
        )
        if observed:
            await observe_score(user_id, JOURNAL_INJECTION_PERIMETER, max(observed))
        return entries
    except Exception as error:
        logger.warning(
            "journal_context_semantic_search_failed",
            user_id=str(user_id),
            error=str(error),
            error_type=type(error).__name__,
        )
        return entries


async def _recent_entries(
    repo: JournalEntryRepository,
    user_id: UUID,
    count: int,
    excluded: list[str],
    scored: list[tuple[JournalEntry, float]],
) -> list[tuple[JournalEntry, float | None]]:
    """Continuity entries precede relevance entries, without duplicate rules."""
    if count <= 0:
        return []
    raw = await repo.get_recent_for_user(
        user_id,
        limit=count,
        exclude_levels=excluded,
        operational_only=True,
    )
    semantic_ids = {entry.id for entry, _ in scored}
    return [(entry, None) for entry in raw if entry.id not in semantic_ids]


def _render_entry(entry: JournalEntry, score: float | None) -> tuple[str, int]:
    """Render the complete directive with the exact version sent to the model."""
    date = entry.created_at.strftime("%Y-%m-%d")
    theme = entry.theme.replace("_", " ")
    mood = JOURNAL_MOOD_EMOJI.get(entry.mood, "")
    score_label = f"score={score:.2f}" if score is not None else "recent"
    revision = int(getattr(entry, "revision", 1) or 1)
    confidence = getattr(entry, "confidence", "medium")
    return (
        f"- [{score_label} | {date} | {theme} | {mood} | "
        f"confidence={confidence} | revision={revision}] **{entry.title}** — {entry.content}",
        revision,
    )


def _debug_entry(entry: JournalEntry, score: float | None, revision: int) -> dict[str, Any]:
    return {
        "theme": entry.theme,
        "title": entry.title[:25],
        "full_title": entry.title,
        "content": entry.content,
        "score": round(score, 4) if score is not None else None,
        "mood": entry.mood,
        "char_count": entry.char_count,
        "source": entry.source,
        "confidence": getattr(entry, "confidence", "medium"),
        "revision": revision,
        "date": entry.created_at.strftime("%Y-%m-%d"),
        "injected": True,
    }


def _pack_entries(
    entries: list[tuple[JournalEntry, float | None]],
    max_chars: int,
    truncate_to_budget: bool,
    include_debug: bool,
) -> tuple[str, list[UUID], dict[str, int], list[dict[str, Any]]]:
    """Account for the whole header and newlines; omitted entries retain no IDs."""
    lines = [
        "## PERSONAL JOURNAL — BEHAVIORAL DIRECTIVES",
        (
            "These are YOUR behavioral directives from past interactions. "
            "Most follow the format: WHEN [context] → DO [action] "
            "(BECAUSE [observation]). "
            "Entries marked [recent] are your latest directives; scored entries "
            "match the current context semantically."
        ),
        "Apply matching directives silently — do not reference them explicitly.",
        "",
    ]
    used = len("\n".join(lines))
    injected_ids: list[UUID] = []
    revisions: dict[str, int] = {}
    debug: list[dict[str, Any]] = []
    for entry, score in entries:
        line, revision = _render_entry(entry, score)
        if include_debug:
            debug.append(_debug_entry(entry, score, revision))
        if truncate_to_budget and used + len(line) + 1 > max_chars:
            if include_debug:
                debug[-1]["injected"] = False
            continue
        lines.append(line)
        used += len(line) + 1
        injected_ids.append(entry.id)
        revisions[str(entry.id)] = revision
    result = "\n".join(lines) if injected_ids else ""
    return result, injected_ids, revisions, debug


def _context_debug(
    result: str,
    scored_count: int,
    recent_count: int,
    injected_count: int,
    max_chars: int,
    max_results: int,
    revisions: dict[str, int],
    entries: list[dict[str, Any]],
    include_debug: bool,
) -> dict[str, Any]:
    if not include_debug:
        return {"injected_revisions": revisions}
    return {
        "entries_found": scored_count,
        "entries_recent": recent_count,
        "entries_injected": injected_count,
        "total_chars_injected": len(result),
        "max_chars_budget": max_chars,
        "max_results_setting": max_results,
        "entries": entries,
        "injected_revisions": revisions,
    }


async def build_journal_context(
    user_id: UUID | str,
    query: str,
    db: AsyncSession,
    query_embedding: list[float] | None = None,
    include_debug: bool = False,
    run_id: str | None = None,
    session_id: str | None = None,
    exclude_levels: list[str] | None = None,
    max_results_override: int | None = None,
    truncate_to_budget: bool = True,
) -> tuple[str | None, dict[str, Any] | None, list[str]]:
    """
    Build journal context block for prompt injection.

    Combines semantic search results with the N most recent entries
    to provide both topical relevance and temporal continuity.

    Accepts a pre-computed embedding from the centralized
    UserMessageEmbeddingService. Falls back to computing its own
    embedding if not provided, or to recent-only if embedding fails.

    This is the operational injection chokepoint (response / planner /
    heartbeat / reminder / react). By default it injects ONLY behavioural
    directives (L1/L2): L0 raw feedstock and L3 portrait facets are excluded
    (the latter is carried by the compiled portrait). Extraction/consolidation
    bypass this function and read the repository directly, so they still see
    every level.

    Args:
        user_id: User UUID (str or UUID)
        query: Search query (last user message for response, goal for planner)
        db: Database session
        query_embedding: Pre-computed embedding vector (1536 dims), or None
        include_debug: If True, returns debug details for the debug panel
        run_id: Pipeline run ID for embedding cost attribution to message
        session_id: Session ID for embedding cost logging
        exclude_levels: Levels to filter OUT. ``None`` (default) falls back to
            ``JOURNAL_OPERATIONAL_INJECTION_EXCLUDE_LEVELS`` (``["L0", "L3"]``).
            Pass ``[]`` explicitly to inject all levels.
        max_results_override: Hard cap on the number of entries injected,
            overriding the user's ``journal_context_max_results`` setting.
            Used by the ReAct loop to inject a small, bounded set of directives.
        truncate_to_budget: When True (default), whole entries that do not fit
            ``max_chars`` are omitted. When False, entries are injected in full and
            only the count cap applies (no mid-directive truncation) — used by
            the ReAct loop where each entry is already bounded by max_entry_chars.

    Returns:
        Tuple of (formatted context string, debug data dict, injected entry IDs).
        - The formatted context and debug data may be None.
        - The injected entry IDs (strings) are always returned (empty list if
          nothing was injected). They are used by the deferred self-evaluation
          mechanism (T → T+1) to let the next turn's extractor observe whether
          the directives were confirmed or contradicted by the user's reaction.
    """
    if isinstance(user_id, str):
        user_id = UUID(user_id)

    try:
        user = await _authorized_user(db, user_id)
        if user is None:
            return None, None, []
        max_chars, max_results, recent_count, excluded = _context_limits(
            user, max_results_override, exclude_levels
        )
        repo = JournalEntryRepository(db)
        embedding = query_embedding if _shared_embedding_matches_journal() else None
        scored_entries = await _semantic_entries(
            repo, user_id, query, embedding, max_results, excluded, run_id, session_id
        )
        recent_entries = await _recent_entries(
            repo, user_id, recent_count, excluded, scored_entries
        )
        all_entries = (recent_entries + [(entry, score) for entry, score in scored_entries])[
            :max_results
        ]
        if not all_entries:
            return None, None, []
        result, injected_ids, revisions, debug_entries = _pack_entries(
            all_entries, max_chars, truncate_to_budget, include_debug
        )
        debug_data = _context_debug(
            result,
            len(scored_entries),
            len(recent_entries),
            len(injected_ids),
            max_chars,
            max_results,
            revisions,
            debug_entries,
            include_debug,
        )
        logger.info(
            "journal_context_built",
            user_id=str(user_id),
            semantic_count=len(scored_entries),
            recent_count=len(recent_entries),
            entries_injected=len(injected_ids),
            result_chars=len(result),
            max_chars=max_chars,
            semantic_scores=[round(s, 4) for _, s in scored_entries],
            has_debug_data=debug_data is not None,
            debug_entries_count=len(debug_data.get("entries", [])),
        )

        # Fire-and-forget injection tracking (non-blocking)
        if injected_ids:
            track_injected_entries(injected_ids)

        return result or None, debug_data, [str(_id) for _id in injected_ids]

    except Exception as e:
        # Graceful degradation — context injection failure must not break the prompt
        logger.warning(
            "journal_context_build_failed",
            user_id=str(user_id),
            error=str(e),
            error_type=type(e).__name__,
        )
        return None, None, []
