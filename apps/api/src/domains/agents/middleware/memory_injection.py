"""
Memory Injection Middleware for Psychological Profile Building.

Constructs and injects a PSYCHOLOGICAL PROFILE ACTIF into the system prompt
based on semantically relevant memories from the user's long-term memory store.

Key features:
- Semantic search for contextually relevant memories
- Emotional state computation (comfort/danger/neutral)
- Formatted profile with visual indicators and usage nuances
- Priority ordering (sensitivities first, then relationships, etc.)
- Smart usage tracking for purge algorithm (Phase 6)

Architecture:
    This middleware runs before the planner/response nodes to enrich
    the context with user-specific knowledge. It transforms raw memory
    items into actionable briefings for the assistant.

The output includes a DIRECTIVE PRIORITAIRE that prevents the assistant
from becoming a "Drama Queen" - emotional context is subtext, not the focus.

Example:
    >>> profile = await build_psychological_profile(store, user_id, query)
    >>> if profile:
    ...     system_prompt += profile

"""

from datetime import UTC, datetime
from typing import Any

from langgraph.store.base import BaseStore, Item

from src.core.config import settings
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    set_embedding_context,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.store.semantic_store import (
    EmotionalState,
    MemoryNamespace,
    StoreNamespace,
    compute_emotional_state,
    search_hybrid,
)

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
    """
    Get semantic label for emotional weight (LLM-friendly, not emoji).

    Args:
        emotional_weight: Value from -10 to +10

    Returns:
        Text label representing the emotional intensity for LLM interpretation
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


def _format_memory_item(memory_value: dict, score: float) -> str:
    """
    Format a single memory item for the profile briefing.

    For sensitivity-category or negative-weight memories, the usage_nuance is
    formatted as an imperative obligation rather than an informational hint,
    ensuring the LLM treats it as a binding instruction.

    Args:
        memory_value: Memory dict with content, emotional_weight, usage_nuance, category
        score: Semantic similarity score

    Returns:
        Formatted line for the profile
    """
    content = memory_value.get("content", "")
    emotional = memory_value.get("emotional_weight", 0)
    nuance = memory_value.get("usage_nuance", "")
    category = memory_value.get("category", "personal")

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
    store: BaseStore,
    user_id: str,
    query: str,
    limit: int | None = None,
    min_score: float | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    include_debug: bool = False,
) -> tuple[str | None, EmotionalState, list[dict] | None]:
    """
    Build the psychological profile for injection into system prompt.

    Searches for semantically relevant memories and formats them into
    an actionable briefing with visual indicators and usage nuances.

    Token Tracking:
        Embedding tokens are tracked to database for user billing when
        session_id is provided. This enables memory costs to appear
        in user statistics.

    Args:
        store: LangGraph BaseStore with semantic search
        user_id: Target user ID for memory retrieval
        query: Current user query for semantic matching
        limit: Maximum number of memories to include
        min_score: Minimum similarity score threshold
        session_id: Optional session ID for token tracking
        conversation_id: Optional conversation UUID for token cost linking

    Returns:
        Tuple of (profile_text, emotional_state, debug_details):
        - profile_text: Formatted profile for system prompt, or None if no memories
        - emotional_state: Computed aggregate emotional state for UI indicator
        - debug_details: List of memory dicts with score/category (only if include_debug=True)

    Example:
        >>> profile, state, debug = await build_psychological_profile(
        ...     store, "user-123", "réunion demain",
        ...     session_id="thread-456"
        ... )
        >>> if profile:
        ...     system_prompt += profile
        >>> # state can be used for UI emotional indicator

    NOTE: Memory injection is always enabled.
    """
    # Use settings defaults if not provided
    if limit is None:
        limit = settings.memory_max_results
    if min_score is None:
        min_score = settings.memory_min_search_score

    # Set embedding context for DB persistence of embedding tokens
    # This enables embedding costs to be tracked in user statistics
    if session_id:
        set_embedding_context(
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

    try:
        namespace = MemoryNamespace(user_id)
        results = await search_hybrid(store, namespace, query, limit=limit, min_score=min_score)

        if not results:
            return None, EmotionalState.NEUTRAL, None

        # Phase 6: Track usage for highly relevant memories (background)
        await track_memory_usage(store, user_id, results)

        # Compute emotional state for UI indicator
        emotional_state = compute_emotional_state(results)

        # Group memories by category
        by_category: dict[str, list[str]] = {}

        for item in results:
            if not isinstance(item.value, dict):
                continue

            category = item.value.get("category", "personal")
            if category not in by_category:
                by_category[category] = []

            formatted_line = _format_memory_item(item.value, getattr(item, "score", 0.0))
            by_category[category].append(formatted_line)

        # Build sections in priority order
        sections = []

        for category in CATEGORY_PRIORITY:
            if category in by_category and by_category[category]:
                header, _icon = SECTION_TEMPLATES.get(category, (f"### {category.upper()}", "info"))
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
            for item in results:
                if not isinstance(item.value, dict):
                    continue
                debug_details.append(
                    {
                        "content": item.value.get("content", "")[:200],
                        "category": item.value.get("category", "unknown"),
                        "score": round(getattr(item, "score", 0.0) or 0.0, 4),
                        "emotional_weight": item.value.get("emotional_weight", 0),
                    }
                )

        logger.info(
            "psychological_profile_built",
            user_id=user_id,
            memory_count=len(results),
            categories=list(by_category.keys()),
            emotional_state=emotional_state.value,
        )

        return profile_text, emotional_state, debug_details

    except Exception as e:
        logger.error(
            "psychological_profile_build_failed",
            user_id=user_id,
            error=str(e),
        )
        return None, EmotionalState.NEUTRAL, None

    finally:
        # Always clear embedding context to prevent cross-request contamination
        if session_id:
            clear_embedding_context()


async def get_memory_context_for_response(
    store: BaseStore,
    user_id: str,
    query: str,
) -> dict:
    """
    Get memory context for inclusion in response generation.

    Returns a dict that can be added to the state for use by response_node.

    Args:
        store: LangGraph BaseStore
        user_id: Target user ID
        query: Current query for semantic matching

    Returns:
        Dict with:
        - memory_context: Formatted profile text or None
        - emotional_state: Emotional state value string
        - memory_count: Number of memories used
    """
    profile, state, _debug = await build_psychological_profile(store, user_id, query)

    return {
        "memory_context": profile,
        "emotional_state": state.value,
        "memory_count": 0 if profile is None else profile.count("- "),
    }


# =============================================================================
# Phase 6: Smart Usage Tracking for Memory Purge
# =============================================================================


async def _update_usage_stats(
    store: BaseStore,
    namespace: StoreNamespace,
    memories: list[Item],
) -> int:
    """
    Increment usage_count and update last_accessed_at for highly relevant memories.

    This runs in the background to avoid adding latency to the response.
    Only memories with score >= MEMORY_RELEVANCE_THRESHOLD trigger this update.

    Args:
        store: LangGraph BaseStore
        namespace: Memory namespace (user_id, "memories")
        memories: List of memory Items to update

    Returns:
        Number of memories updated
    """
    updated_count = 0
    now = datetime.now(UTC)

    for item in memories:
        try:
            # Get current values
            current_usage = item.value.get("usage_count", 0)

            # Update the memory with incremented usage
            updated_value = {
                **item.value,
                "usage_count": current_usage + 1,
                "last_accessed_at": now.isoformat(),
            }

            await store.aput(
                namespace.to_tuple(),
                key=item.key,
                value=updated_value,
            )
            updated_count += 1

        except Exception as e:
            logger.warning(
                "memory_usage_update_failed",
                memory_id=item.key,
                error=str(e),
            )

    if updated_count > 0:
        logger.debug(
            "memory_usage_stats_updated",
            count=updated_count,
            namespace=namespace.to_tuple(),
        )

    return updated_count


async def track_memory_usage(
    store: BaseStore,
    user_id: str,
    memories: list[Item],
) -> None:
    """
    Track usage for highly relevant memories (score >= threshold).

    Filters memories by relevance threshold and updates usage stats in background.
    This is the public entry point called from build_psychological_profile.

    Args:
        store: LangGraph BaseStore
        user_id: Target user ID
        memories: List of memory Items from semantic search
    """
    # Filter for highly relevant memories only
    relevance_threshold = settings.memory_relevance_threshold
    highly_relevant = [
        m for m in memories if hasattr(m, "score") and m.score >= relevance_threshold
    ]

    if not highly_relevant:
        return

    # Fire and forget - don't block the response
    namespace = MemoryNamespace(user_id)
    safe_fire_and_forget(
        _update_usage_stats(store, namespace, highly_relevant),
        name=f"memory_usage_update_{user_id}",
    )

    logger.debug(
        "memory_usage_tracking_scheduled",
        user_id=user_id,
        total_memories=len(memories),
        highly_relevant=len(highly_relevant),
        threshold=relevance_threshold,
    )


# =============================================================================
# Pre-Planner Memory Facts Extraction
# =============================================================================


async def get_memory_facts_for_query(
    store: BaseStore,
    user_id: str,
    query: str,
    limit: int = 5,
    min_score: float = 0.5,
) -> list[str] | None:
    """
    Get memory facts for pre-planner reference resolution.

    This function extracts memory content as a list for use by
    QueryAnalyzerService and MemoryReferenceResolutionService to resolve
    personal references like "ma femme", "mon frère" before planning.

    Args:
        store: LangGraph BaseStore with semantic search
        user_id: Target user ID for memory retrieval
        query: Current user query for semantic matching
        limit: Maximum memories to retrieve (default: 5)
        min_score: Minimum similarity threshold (default: 0.5)

    Returns:
        List of memory content strings, or None if no memories found.
        Example: ["Ma femme s'appelle jean dupond.", "J'ai un frère jean."]

    Usage:
        memory_facts = await get_memory_facts_for_query(store, user_id, query)
        if memory_facts:
            # Pass list directly to QueryAnalyzerService
            # Or join for string-based consumers: "\\n".join(memory_facts)
    """
    if not store or not user_id:
        return None

    try:
        namespace = MemoryNamespace(user_id)
        # Fetch more results than needed, then sort by importance/usage
        fetch_limit = max(limit * 3, 30)  # Fetch 3x or at least 30 to ensure good coverage
        results = await search_hybrid(
            store, namespace, query, limit=fetch_limit, min_score=min_score
        )

        if not results:
            logger.debug(
                "memory_facts_no_results",
                user_id=user_id,
                query_preview=query[:50],
            )
            return None

        # Sort by usage_count + importance (descending) to prioritize frequently used
        # and important memories over transient ones
        def sort_key(item: Any) -> tuple[float, float, float]:
            """Sort by: usage_count (desc), importance (desc), score (desc)."""
            if not isinstance(item.value, dict):
                return (0.0, 0.0, 0.0)
            usage = item.value.get("usage_count", 0) or 0
            importance = item.value.get("importance", 0.5) or 0.5
            score = getattr(item, "score", 0.0) or 0.0
            return (usage, importance, score)

        sorted_results = sorted(results, key=sort_key, reverse=True)

        # Extract content from top memories
        facts = []
        for item in sorted_results[:limit]:
            if not isinstance(item.value, dict):
                continue

            content = item.value.get("content", "")
            if content:
                facts.append(content)

        if not facts:
            return None

        logger.info(
            "memory_facts_extracted",
            user_id=user_id,
            query_preview=query[:50],
            facts_count=len(facts),
            total_length=sum(len(f) for f in facts),
            fetched_count=len(results),
            sorted_by="usage_count+importance",
        )

        return facts  # Return list[str] - consumers format as needed

    except Exception as e:
        logger.warning(
            "memory_facts_extraction_failed",
            user_id=user_id,
            error=str(e),
        )
        return None
