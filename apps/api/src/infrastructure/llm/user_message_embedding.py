"""
Centralized user message embedding service.

Computes the embedding of the user's message ONCE per conversation turn
and caches by text hash. Shared across nodes (planner, response) and
background tasks within the same process, avoiding redundant OpenAI API calls.

Architecture:
    planner_node / response_node (early, before injection)
        |
    get_or_compute_embedding(message, ..., is_conversational=...)
        |--- is_conversational and is_trivial_message(message) -> None
        |--- Cache hit (text_hash in _cache) -> return cached vector
        |--- Cache miss -> aembed_query(message[:500]) -> cache + return

The triviality heuristic only applies to text the user actually typed. It is
pattern-based on short acknowledgements, and those patterns collide with real
surnames ("Fine", "Cool", "Bien"): applying them to a person name silently
erased that contact's memories. ``is_conversational`` is therefore required —
every caller must state what kind of text it is passing.

Cache key: md5(text[:500]) -- text-dependent, not run-dependent.
This allows cross-node sharing: planner and response_node cache the same
embedding when they use the same query text.

TTL: 5 min. Max: 100 entries. Lazy eviction on each access.
Same cache pattern as _extraction_debug_results in extraction_service.py.

Conversational callers (is_conversational=True — the user's own message):
    - Memory injection (build_psychological_profile)
    - Journal injection (build_journal_context)
    - Memory extraction (dedup search pre-filter)
    - Journal extraction (semantic pre-filter)

Non-conversational callers (is_conversational=False — never an utterance):
    - person_tools._fetch_person_memories (embeds a person NAME)
    - heartbeat context_aggregator (embeds an internal search query)

Not consumers of this cache at all (they embed their own text elsewhere):
    - Interest extraction (embeds extracted topics, not user message)
    - Journal dedup guard (embeds proposed entry content)
    - get_memory_facts_for_query (embeds clarification response)
    - reminder_notification (embeds reminder content)

Phase: v1.14.0 -- Embedding centralization & token optimization
Created: 2026-03-30
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import TYPE_CHECKING

from src.core.constants import (
    USER_MESSAGE_EMBEDDING_MAX_CACHE_SIZE,
    USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH,
    USER_MESSAGE_EMBEDDING_TTL_SECONDS,
    USER_MESSAGE_TRIVIAL_MAX_LENGTH,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


# =============================================================================
# Triviality Detection
# =============================================================================

# Patterns for common trivial messages (case-insensitive).
# One pattern per supported language (fr, en, de, es, it, zh) + emoji-only.
# The list is applied WITHOUT knowing the message language, so every token is
# live for every user \u2014 a French speaker typing "no" is matched by the English
# pattern. That is intentional and harmless for acknowledgements.
#
# DELIBERATELY EXCLUDED \u2014 these are real surnames, and a pattern that swallows a
# name is not a saved token, it is lost data (D7: a contact named Fine, Cool or
# Bien lost every associated memory because this heuristic also ran on person
# names). Do not add them back:
#   - "gut"   (de, "good")  \u2014 Gut is an attested surname
#   - "vale"  (es, "okay")  \u2014 Vale is a common surname
#   - "bene"  (it, "good")  \u2014 Bene is an attested surname (Carmelo Bene)
#   - "claro" (es, "sure")  \u2014 Claro exists as a surname
# The fr/en patterns below already carry that risk historically ("fine", "cool",
# "top", "bien"); it is now bounded to conversational input only, because
# get_or_compute_embedding requires an explicit `is_conversational` flag.
_TRIVIAL_PATTERNS: list[re.Pattern[str]] = [
    # French
    re.compile(
        r"^(ok|oui|non|merci|d'accord|super|cool|top|parfait|bien|bof|mouais)[\.\!\?]*$",
        re.IGNORECASE,
    ),
    # English
    re.compile(
        r"^(ok|yes|no|thanks|thank you|sure|yep|nope|great|fine|cool)[\.\!\?]*$",
        re.IGNORECASE,
    ),
    # German
    re.compile(
        r"^(ja|nein|danke|okay|alles klar|perfekt|stimmt)[\.\!\?]*$",
        re.IGNORECASE,
    ),
    # Spanish
    re.compile(
        r"^(s\u00ed|gracias|perfecto|genial|de acuerdo)[\.\!\?]*$",
        re.IGNORECASE,
    ),
    # Italian
    re.compile(
        r"^(s\u00ec|grazie|va bene|perfetto|certo|ottimo)[\.\!\?]*$",
        re.IGNORECASE,
    ),
    # Chinese (no case folding applies; CJK acknowledgements are not surnames)
    re.compile(
        r"^(\u597d\u7684|\u597d|\u8c22\u8c22|\u662f\u7684|\u6536\u5230|\u660e\u767d|\u55ef)[\.\!\?\u3002\uff01\uff1f]*$",
    ),
    # Emoji-only
    re.compile(
        r"^[\U0001f44d\U0001f44c\u2705\U0001f44f\u2764\ufe0f\U0001f60a\U0001f64f]+$",
    ),
]


def is_trivial_message(message: str) -> bool:
    """Check if a user message is trivial using heuristics.

    Trivial messages are short acknowledgements, greetings, or emoji-only
    messages that carry no extractable information for memory or journal.
    All six supported languages are covered (fr, en, de, es, it, zh): before
    that, a German "ja" or a Chinese "好的" paid for one embedding plus up to
    four extraction LLM calls.

    No LLM call, no embedding computation -- pure regex + length check.

    Only ever call this on text the user actually typed — see
    ``get_or_compute_embedding``'s ``is_conversational`` flag. The patterns
    collide with real surnames, so applying them to a lookup key silently
    discards it.

    Args:
        message: Raw user message text.

    Returns:
        True if the message is trivial and should skip extraction.
    """
    stripped = message.strip()
    if not stripped:
        return True

    if len(stripped) > USER_MESSAGE_TRIVIAL_MAX_LENGTH:
        return False

    return any(pattern.match(stripped) for pattern in _TRIVIAL_PATTERNS)


# =============================================================================
# Embedding Cache (in-process, text-hash keyed)
# =============================================================================

# dict[text_hash] -> (monotonic_timestamp, embedding_vector)
_cache: dict[str, tuple[float, list[float]]] = {}


def _text_hash(text: str) -> str:
    """Compute cache key from truncated message text.

    Uses MD5 for speed (not security). Truncates to embedding length
    to match what the embedding model actually sees.

    Args:
        text: Raw message text.

    Returns:
        MD5 hex digest of the truncated text.
    """
    truncated = text[:USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH]
    return hashlib.md5(truncated.encode("utf-8")).hexdigest()


def _cleanup_stale() -> None:
    """Evict expired entries and enforce max cache size.

    Called lazily before each cache read/write. Non-blocking.
    """
    now = time.monotonic()

    # TTL eviction
    stale_keys = [
        k for k, (ts, _) in _cache.items() if now - ts > USER_MESSAGE_EMBEDDING_TTL_SECONDS
    ]
    for k in stale_keys:
        del _cache[k]

    # LRU eviction (oldest first) if over max size
    while len(_cache) > USER_MESSAGE_EMBEDDING_MAX_CACHE_SIZE:
        oldest_key = next(iter(_cache))
        del _cache[oldest_key]


# =============================================================================
# Main API
# =============================================================================


async def get_or_compute_embedding(
    message: str,
    user_id: str | None = None,
    session_id: str | None = None,
    *,
    is_conversational: bool,
) -> list[float] | None:
    """Compute or return cached embedding for a text.

    This is the main entry point for all consumers needing an embedding of a
    short text. It handles the triviality check, caching, and graceful
    degradation.

    Callers should set EmbeddingTrackingContext before calling for
    accurate cost attribution (user_id, session_id, run_id).

    Args:
        message: Text to embed.
        user_id: Optional user ID for logging.
        session_id: Optional session ID for logging.
        is_conversational: True when ``message`` is something the user actually
            typed in the conversation — only then may it be discarded as a
            trivial acknowledgement. Required (keyword-only) on purpose: a
            silent default is what let a *person name* be judged "trivial",
            since the patterns collide with real surnames (Fine, Cool, Bien).
            Pass False for lookup keys, search queries and any other
            non-conversational input.

    Returns:
        1536-dim embedding vector, or None if:
        - Message is empty
        - Message is a trivial conversational acknowledgement
        - Embedding computation fails (graceful degradation)
    """
    if not message or not message.strip():
        return None

    if is_conversational and is_trivial_message(message):
        logger.debug(
            "user_message_embedding_trivial_skip",
            user_id=user_id,
            message_length=len(message),
        )
        return None

    key = _text_hash(message)
    _cleanup_stale()

    # Cache hit
    if key in _cache:
        logger.debug(
            "user_message_embedding_cache_hit",
            user_id=user_id,
            cache_size=len(_cache),
        )
        return _cache[key][1]

    # Cache miss -- compute embedding
    try:
        from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

        embeddings = get_memory_embeddings()
        truncated = message[:USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH]
        vector = await embeddings.aembed_query(truncated)

        _cache[key] = (time.monotonic(), vector)

        logger.info(
            "user_message_embedding_computed",
            user_id=user_id,
            message_length=len(message),
            truncated_length=len(truncated),
            cache_size=len(_cache),
        )

        return vector

    except Exception as e:
        # Graceful degradation: consumers fallback to recent-only mode
        logger.warning(
            "user_message_embedding_failed",
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def clear_cache() -> None:
    """Clear the entire embedding cache.

    Used in tests and at application shutdown.
    """
    _cache.clear()
    logger.debug("user_message_embedding_cache_cleared")
