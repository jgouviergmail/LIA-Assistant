"""
Memory Injection Middleware for Psychological Profile Building.

Constructs and injects a PSYCHOLOGICAL PROFILE ACTIF into the system prompt
based on semantically relevant memories from the user's long-term memory store.

Key features:
- Semantic search for contextually relevant memories (pgvector cosine distance)
- Emotional state computation (comfort/danger/neutral)
- Formatted profile with visual indicators and usage nuances
- Priority ordering (sensitivities first, then relationships, etc.)
- Smart usage tracking for purge algorithm (Phase 6)
- Accepts pre-computed embedding from centralized UserMessageEmbeddingService

Architecture:
    This middleware runs before the planner/response nodes to enrich
    the context with user-specific knowledge. It transforms raw memory
    items into actionable briefings for the assistant.

The output includes a DIRECTIVE PRIORITAIRE that prevents the assistant
from becoming a "Drama Queen" - emotional context is subtext, not the focus.

Example:
    >>> profile = await build_psychological_profile(
    ...     user_id="user-123", query="réunion demain",
    ...     query_embedding=precomputed_vector,
    ... )
    >>> if profile:
    ...     system_prompt += profile

Phase: v1.14.0 — Migrated from LangGraph store to PostgreSQL custom
"""

from __future__ import annotations

from uuid import UUID

from src.core.config import settings
from src.domains.memories.emotional_state import EmotionalState, compute_emotional_state
from src.domains.memories.models import Memory
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# Template for the psychological profile injection (base, always present)
PSYCHOLOGICAL_PROFILE_TEMPLATE = """
## PROFIL PSYCHOLOGIQUE DE L'UTILISATEUR

⚠️ **IMPORTANT**: Les informations ci-dessous sont des souvenirs de L'UTILISATEUR, pas les tiens.
Quand tu lis "Je me suis marié en 2008", cela signifie que L'UTILISATEUR s'est marié en 2008.
Tu dois répondre en disant "Tu t'es marié en 2008" ou "Vous vous êtes marié en 2008".

{profile_sections}

---
{behavioral_directive}
"""

# Behavioral directive when emotional state is DANGER (sensitivity memories present)
DANGER_DIRECTIVE = """## ⛔ DIRECTIVE DE SÉCURITÉ ÉMOTIONNELLE (PRIORITÉ ABSOLUE)

Des souvenirs marqués **[TRAUMA/DOULEUR]** ou **[NÉGATIF]** sont actifs dans ce contexte.
Les instructions marquées **⚠ OBLIGATION :** dans les zones sensibles ci-dessus sont des ORDRES, pas des suggestions.

**INTERDICTIONS ABSOLUES** — violation = faute grave :
1. **JAMAIS** de blague, ironie, sarcasme ou humour noir touchant de près ou de loin un sujet TRAUMA/NÉGATIF
2. **JAMAIS** de référence désinvolte, légère ou banalisante à un sujet de zone sensible
3. **JAMAIS** de minimisation ("ce n'est pas si grave", "ça va aller") d'un souvenir négatif
4. **JAMAIS** de projection ou de comparaison avec d'autres situations ("d'autres ont vécu pire")

**COMPORTEMENT REQUIS** quand un sujet sensible est activé ou proche du contexte :
- Adopte un ton **respectueux, sobre et empathique**
- Si le sujet sensible n'est pas directement abordé par l'utilisateur, **ne le mentionne pas**
- Si l'utilisateur l'aborde : **accueille avec bienveillance**, sans relancer ni approfondir sauf si demandé
- En cas de doute sur le ton approprié : **choisis toujours la prudence**

Ces informations constituent le "sous-texte" de ton interaction, pas le sujet principal.

1. **Tâche technique** (code, recherche, calcul) → Ignore les émotions, garde le style de communication
2. **Tâche conversationnelle** → Personnalise avec respect, **en évitant tout sujet sensible**
3. **Ne force jamais** l'utilisation d'une mémoire si elle n'est pas pertinente au contexte immédiat

Les instructions de chaque souvenir (marquées ⚠ OBLIGATION) t'indiquent précisément ce que tu DOIS et NE DOIS PAS faire."""

# Behavioral directive for normal states (NEUTRAL / COMFORT)
NORMAL_DIRECTIVE = """## DIRECTIVE PRIORITAIRE

Ces informations constituent le "sous-texte" de ton interaction, pas le sujet principal.

1. **Tâche technique** (code, recherche, calcul) → Ignore les émotions, garde le style de communication
2. **Tâche conversationnelle** → Utilise ces leviers pour créer du lien et personnaliser
3. **Ne force jamais** l'utilisation d'une mémoire si elle n'est pas pertinente au contexte immédiat

Les nuances d'usage t'indiquent COMMENT exploiter chaque information quand c'est approprié."""

# Section templates by category with priority ordering
SECTION_TEMPLATES = {
    "sensitivity": ("### ZONES SENSIBLES (Attention requise)", "alert-triangle"),
    "relationship": ("### RELATIONS CONNUES", "users"),
    "preference": ("### PRÉFÉRENCES & GOÛTS", "heart"),
    "personal": ("### INFORMATIONS PERSONNELLES", "user"),
    "pattern": ("### PATTERNS COMPORTEMENTAUX", "repeat"),
    "event": ("### ÉVÉNEMENTS SIGNIFICATIFS", "calendar"),
}

# Priority order for sections (sensitivities first for safety)
CATEGORY_PRIORITY = [
    "sensitivity",
    "relationship",
    "preference",
    "personal",
    "pattern",
    "event",
]


def _get_emotional_label(emotional_weight: int) -> str:
    """Get semantic label for emotional weight (LLM-friendly, not emoji).

    Args:
        emotional_weight: Value from -10 to +10.

    Returns:
        Text label representing the emotional intensity for LLM interpretation.
    """
    if emotional_weight <= -7:
        return "[TRAUMA/DOULEUR]"
    elif emotional_weight <= -3:
        return "[NÉGATIF]"
    elif emotional_weight >= 7:
        return "[TRÈS POSITIF]"
    elif emotional_weight >= 3:
        return "[POSITIF]"
    else:
        return "[NEUTRE]"


def _format_memory_item(memory: Memory, score: float) -> str:
    """Format a single memory for the profile briefing.

    For sensitivity-category or negative-weight memories, the usage_nuance is
    formatted as an imperative obligation rather than an informational hint,
    ensuring the LLM treats it as a binding instruction.

    Args:
        memory: Memory ORM object.
        score: Semantic similarity score.

    Returns:
        Formatted line for the profile.
    """
    content = memory.content or ""
    emotional = memory.emotional_weight
    nuance = memory.usage_nuance or ""
    category = memory.category or "personal"

    label = _get_emotional_label(emotional)
    line = f"- {label} {content}"

    if nuance:
        # Sensitive or negative memories: format nuance as imperative obligation
        if category == "sensitivity" or emotional <= -3:
            line += f"\n  **⚠ OBLIGATION :** {nuance}"
        else:
            line += f" → *{nuance}*"

    return line


async def build_psychological_profile(
    user_id: str,
    query: str,
    query_embedding: list[float] | None = None,
    limit: int | None = None,
    min_score: float | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    include_debug: bool = False,
) -> tuple[str | None, EmotionalState, list[dict] | None]:
    """Build the psychological profile for injection into system prompt.

    Searches for semantically relevant memories and formats them into
    an actionable briefing with visual indicators and usage nuances.

    Accepts a pre-computed embedding from the centralized
    UserMessageEmbeddingService to avoid redundant API calls.
    Falls back to recent memories if embedding is None.

    Args:
        user_id: Target user ID for memory retrieval.
        query: Current user query (used for logging, not embedding).
        query_embedding: Pre-computed embedding vector (1536 dims), or None for fallback.
        limit: Maximum number of memories to include.
        min_score: Minimum similarity score threshold.
        session_id: Optional session ID for embedding cost tracking.
        conversation_id: Optional conversation UUID for cost linking.
        include_debug: If True, return debug details for debug panel.

    Returns:
        Tuple of (profile_text, emotional_state, debug_details).
    """
    from src.infrastructure.database.session import get_db_context

    # Use settings defaults if not provided
    if limit is None:
        limit = settings.memory_max_results
    if min_score is None:
        min_score = settings.memory_min_search_score

    try:
        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)

            # Semantic search or fallback to recent memories
            if query_embedding is not None:
                # Set embedding context for any additional embedding calls
                # (e.g., if the repo needs to embed for some reason)
                if session_id:
                    from src.infrastructure.llm.embedding_context import (
                        clear_embedding_context,
                        set_embedding_context,
                    )

                    set_embedding_context(
                        user_id=user_id,
                        session_id=session_id,
                        conversation_id=conversation_id,
                    )

                try:
                    results: list[tuple[Memory, float]] = await repo.search_by_relevance(
                        user_id=UUID(user_id),
                        query_embedding=query_embedding,
                        limit=limit,
                        min_score=min_score,
                    )
                finally:
                    if session_id:
                        clear_embedding_context()
            else:
                # Fallback: no embedding → load recent memories for continuity
                recent = await repo.get_recent_for_user(UUID(user_id), limit=min(limit, 10))
                results = [(m, 0.0) for m in recent]

            if not results:
                return None, EmotionalState.NEUTRAL, None

            # Phase 6: Track usage for highly relevant memories (background)
            await _track_memory_usage(user_id, results)

            # Compute emotional state for UI indicator
            emotional_state = compute_emotional_state(results)

            # Group memories by category
            by_category: dict[str, list[str]] = {}

            for memory, score in results:
                category = memory.category or "personal"
                if category not in by_category:
                    by_category[category] = []

                formatted_line = _format_memory_item(memory, score)
                by_category[category].append(formatted_line)

            # Build sections in priority order
            sections = []

            for category in CATEGORY_PRIORITY:
                if category in by_category and by_category[category]:
                    header, _icon = SECTION_TEMPLATES.get(
                        category, (f"### {category.upper()}", "info")
                    )
                    items_text = "\n".join(by_category[category])
                    sections.append(f"{header}\n{items_text}")

            if not sections:
                return None, EmotionalState.NEUTRAL, None

            # Select behavioral directive based on emotional state
            behavioral_directive = (
                DANGER_DIRECTIVE if emotional_state == EmotionalState.DANGER else NORMAL_DIRECTIVE
            )

            profile_text = PSYCHOLOGICAL_PROFILE_TEMPLATE.format(
                profile_sections="\n\n".join(sections),
                behavioral_directive=behavioral_directive,
            )

            # Build debug details if requested (for debug panel tuning)
            debug_details: list[dict] | None = None
            if include_debug:
                debug_details = []
                for memory, score in results:
                    debug_details.append(
                        {
                            "content": (memory.content or "")[:200],
                            "category": memory.category or "unknown",
                            "score": round(score, 4),
                            "emotional_weight": memory.emotional_weight,
                        }
                    )

            logger.info(
                "psychological_profile_built",
                user_id=user_id,
                memory_count=len(results),
                categories=list(by_category.keys()),
                emotional_state=emotional_state.value,
                used_embedding=query_embedding is not None,
            )

            return profile_text, emotional_state, debug_details

    except Exception as e:
        logger.error(
            "psychological_profile_build_failed",
            user_id=user_id,
            error=str(e),
        )
        return None, EmotionalState.NEUTRAL, None


async def get_memory_context_for_response(
    user_id: str,
    query: str,
    query_embedding: list[float] | None = None,
) -> dict:
    """Get memory context for inclusion in response generation.

    Returns a dict that can be added to the state for use by response_node.

    Args:
        user_id: Target user ID.
        query: Current query for semantic matching.
        query_embedding: Pre-computed embedding vector.

    Returns:
        Dict with memory_context, emotional_state, memory_count.
    """
    profile, state, _debug = await build_psychological_profile(
        user_id=user_id,
        query=query,
        query_embedding=query_embedding,
    )

    return {
        "memory_context": profile,
        "emotional_state": state.value,
        "memory_count": 0 if profile is None else profile.count("- "),
    }


# =============================================================================
# Phase 6: Smart Usage Tracking for Memory Purge
# =============================================================================


async def _update_usage_stats_db(
    memory_ids: list[UUID],
) -> int:
    """Increment usage_count and update last_accessed_at for memories.

    Uses the repository's bulk UPDATE instead of the store's aput pattern.

    Args:
        memory_ids: UUIDs of memories to update.

    Returns:
        Number of memories updated (always equals len(memory_ids) on success).
    """
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)
            await repo.increment_usage(memory_ids)
            await db.commit()

        logger.debug(
            "memory_usage_stats_updated",
            count=len(memory_ids),
        )
        return len(memory_ids)

    except Exception as e:
        logger.warning(
            "memory_usage_update_failed",
            count=len(memory_ids),
            error=str(e),
        )
        return 0


async def _track_memory_usage(
    user_id: str,
    results: list[tuple[Memory, float]],
) -> None:
    """Track usage for highly relevant memories (score >= threshold).

    Filters memories by relevance threshold and updates usage stats in background.
    Called from build_psychological_profile.

    Args:
        user_id: Target user ID.
        results: List of (Memory, score) tuples from semantic search.
    """
    relevance_threshold = settings.memory_relevance_threshold
    highly_relevant_ids = [memory.id for memory, score in results if score >= relevance_threshold]

    if not highly_relevant_ids:
        return

    # Fire and forget - don't block the response
    safe_fire_and_forget(
        _update_usage_stats_db(highly_relevant_ids),
        name=f"memory_usage_update_{user_id}",
    )

    logger.debug(
        "memory_usage_tracking_scheduled",
        user_id=user_id,
        total_memories=len(results),
        highly_relevant=len(highly_relevant_ids),
        threshold=relevance_threshold,
    )


# =============================================================================
# Pre-Planner Memory Facts Extraction
# =============================================================================


async def get_memory_facts_for_query(
    user_id: str,
    query: str,
    limit: int = 5,
    min_score: float | None = None,
) -> list[str] | None:
    """Get memory facts for pre-planner reference resolution.

    Extracts memory content as a list for use by QueryAnalyzerService
    and MemoryReferenceResolutionService to resolve personal references
    like "ma femme", "mon frère" before planning.

    This function computes its OWN embedding (not centralized) because
    the query is different from the user message (it's the clarification
    response, initiative context, or resolver query).

    Results are sorted by (usage_count, importance, score) descending
    to prioritize frequently used and important memories.

    Args:
        user_id: Target user ID.
        query: Current query for semantic matching.
        limit: Maximum memories to retrieve (default: 5).
        min_score: Minimum similarity threshold.

    Returns:
        List of memory content strings, or None if empty/error.
    """
    from src.infrastructure.database.session import get_db_context

    if not user_id:
        return None

    try:
        if min_score is None:
            min_score = settings.memory_min_search_score

        # Compute embedding locally (query ≠ user message)
        from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

        embeddings = get_memory_embeddings()
        query_embedding = await embeddings.aembed_query(query[:500])

        if not query_embedding:
            return None

        # Fetch more results than needed, then sort by importance/usage
        fetch_limit = max(limit * 3, 30)

        async with get_db_context() as db:
            from src.domains.memories.repository import MemoryRepository

            repo = MemoryRepository(db)
            results = await repo.search_by_relevance(
                user_id=UUID(user_id),
                query_embedding=query_embedding,
                limit=fetch_limit,
                min_score=min_score,
            )

            if not results:
                logger.debug(
                    "memory_facts_no_results",
                    user_id=user_id,
                    query_preview=query[:50],
                )
                return None

            # Sort by relevance score (primary), then importance, then usage_count.
            # Semantic similarity is the most critical signal when retrieving facts
            # for a specific query — usage_count as primary key caused targeted
            # reference resolution to miss specific facts (e.g., "mon fils") in
            # favor of more frequently used but less relevant memories.
            sorted_results = sorted(
                results,
                key=lambda x: (
                    x[1] or 0.0,
                    x[0].importance or 0.5,
                    x[0].usage_count or 0,
                ),
                reverse=True,
            )

            # Extract content from top memories (still inside session)
            facts: list[str] = []
            for memory, _score in sorted_results[:limit]:
                content = memory.content or ""
                if content:
                    facts.append(content)

            fetched_count = len(results)

        if not facts:
            return None

        logger.info(
            "memory_facts_extracted",
            user_id=user_id,
            query_preview=query[:50],
            facts_count=len(facts),
            total_length=sum(len(f) for f in facts),
            fetched_count=fetched_count,
            sorted_by="usage_count+importance",
        )

        return facts

    except Exception as e:
        logger.warning(
            "memory_facts_extraction_failed",
            user_id=user_id,
            error=str(e),
        )
        return None
