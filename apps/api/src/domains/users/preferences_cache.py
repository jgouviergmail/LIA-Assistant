"""In-process TTL cache for user display preferences (timezone, language).

``get_user_preferences`` (agents tool helper) previously opened a DB session
and issued a User query on every call; with 25+ tools calling it several
times per plan, that meant dozens of identical queries per conversation
turn. Timezone and language change rarely, so a short per-user TTL cache
eliminates almost all of them (audit wave 3, N-129).

Cross-worker note: the cache is per-process (same pattern as
``LLMConfigOverrideCache``). ``UserService.update_user`` invalidates the
entry in its own worker immediately; other uvicorn workers converge within
``settings.user_preferences_cache_ttl_seconds``.
"""

from __future__ import annotations

import time

from src.core.config import settings
from src.core.constants import USER_PREFERENCES_CACHE_MAX_ENTRIES
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class UserPreferencesCache:
    """Per-user TTL cache for (timezone, language) pairs.

    Only successful DB lookups are cached — defaults for missing users are
    never pinned, so a user created after a miss is picked up immediately.
    """

    # user_id → (monotonic expiry, timezone, language)
    _entries: dict[str, tuple[float, str, str]] = {}

    @classmethod
    def get(cls, user_id: str) -> tuple[str, str] | None:
        """Return cached (timezone, language) or None if absent/expired.

        Args:
            user_id: User UUID as string.

        Returns:
            Tuple of (timezone, language), or None on cache miss.
        """
        entry = cls._entries.get(user_id)
        if entry is None:
            return None
        expires_at, timezone, language = entry
        if time.monotonic() >= expires_at:
            cls._entries.pop(user_id, None)
            return None
        return timezone, language

    @classmethod
    def set(cls, user_id: str, timezone: str, language: str) -> None:
        """Cache (timezone, language) for a user until the TTL elapses.

        A TTL of 0 (settings) disables caching entirely.

        Args:
            user_id: User UUID as string.
            timezone: IANA timezone name.
            language: Canonical language code (e.g., "fr", "zh-CN").
        """
        ttl = settings.user_preferences_cache_ttl_seconds
        if ttl <= 0:
            return
        if len(cls._entries) >= USER_PREFERENCES_CACHE_MAX_ENTRIES:
            # Safety valve — should never trigger with realistic user counts.
            logger.warning(
                "user_preferences_cache_reset",
                entries=len(cls._entries),
                max_entries=USER_PREFERENCES_CACHE_MAX_ENTRIES,
            )
            cls._entries.clear()
        cls._entries[user_id] = (time.monotonic() + ttl, timezone, language)

    @classmethod
    def invalidate(cls, user_id: str) -> None:
        """Drop the cached entry for a user (call on profile update).

        Args:
            user_id: User UUID as string.
        """
        cls._entries.pop(user_id, None)

    @classmethod
    def clear(cls) -> None:
        """Drop all entries (test isolation helper)."""
        cls._entries.clear()
