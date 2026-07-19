"""In-memory detection cache for pending HITL interrupts.

Single chokepoint for the per-process cache that fronts the Redis
``hitl_pending:{conversation_id}`` lookup on every chat request
(PHASE 8.1.3 performance optimization, extracted from the agents router).

Why invalidation matters (Lot 1 Phase 0): without it, a user replying
faster than the TTL — exactly what one-click approval buttons enable —
hits a stale cached answer and gets misrouted (a fresh interrupt is
missed → the reply starts a NEW turn; a cleared interrupt lingers →
the next message resumes a phantom HITL). ``HITLStore.save_interrupt``
and ``delete_interrupt`` call :func:`invalidate` so the same-process
window is closed at the source.

Scope: the cache is per-process. With multiple workers, a save on one
worker cannot invalidate another worker's entry — that residual
staleness is bounded by ``hitl_detection_cache_ttl_seconds`` (default
5 s), the same bound the cache always had.
"""

from datetime import UTC, datetime, timedelta

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# conversation_id -> (cached detection result, cached-at timestamp)
_cache: dict[str, tuple[dict | None, datetime]] = {}


def _ttl() -> timedelta:
    return timedelta(seconds=settings.hitl_detection_cache_ttl_seconds)


def get_cached(conversation_id: str) -> tuple[bool, dict | None]:
    """Return (hit, data) for a conversation's cached detection result.

    Args:
        conversation_id: Conversation UUID string.

    Returns:
        ``(True, data)`` on a fresh cache hit (``data`` may be None —
        a cached "nothing pending" answer); ``(False, None)`` on miss
        or stale entry.
    """
    entry = _cache.get(conversation_id)
    if entry is None:
        return False, None
    data, cached_at = entry
    if datetime.now(UTC) - cached_at >= _ttl():
        return False, None
    return True, data


def set_cached(conversation_id: str, data: dict | None) -> None:
    """Store a detection result and purge entries older than 2x TTL."""
    now = datetime.now(UTC)
    _cache[conversation_id] = (data, now)

    cleanup_threshold = now - (_ttl() * 2)
    stale_keys = [conv_id for conv_id, (_, ts) in _cache.items() if ts <= cleanup_threshold]
    for conv_id in stale_keys:
        del _cache[conv_id]


def invalidate(conversation_id: str) -> None:
    """Drop a conversation's cached detection result (save/clear chokepoint)."""
    if _cache.pop(conversation_id, None) is not None:
        logger.debug("hitl_detection_cache_invalidated", conversation_id=conversation_id)
