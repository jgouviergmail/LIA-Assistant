"""Per-provider cache invalidation on push notification (lot H, 2026-08).

A notification means the source changed. Dropping the matching caches makes
the next read fresh; failing to drop them only means the TTL bounds staleness
— so everything here is best-effort and never raises into the webhook path.
"""

from __future__ import annotations

import contextlib
from uuid import UUID

import structlog

from src.core.constants import REDIS_KEY_GMAIL_SEARCH_PREFIX
from src.domains.briefing.constants import (
    BRIEFING_CACHE_PREFIX,
    SECTION_AGENDA,
    SECTION_DOCUMENTS,
    SECTION_MAILS,
)
from src.domains.push_channels.models import PushChannelProvider
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

_DELETE_BATCH_SIZE = 100

# Boot-time completeness (ADR-085): every provider maps to a briefing section.
_PROVIDER_SECTIONS: dict[str, str] = {
    PushChannelProvider.GOOGLE_CALENDAR.value: SECTION_AGENDA,
    PushChannelProvider.GOOGLE_DRIVE.value: SECTION_DOCUMENTS,
    PushChannelProvider.GOOGLE_GMAIL.value: SECTION_MAILS,
}
# Completeness raised (not asserted) so the guard survives -O and a missing
# entry can never fall through silently (ADR-085 pattern).
if set(_PROVIDER_SECTIONS) != {p.value for p in PushChannelProvider}:
    raise RuntimeError("Every PushChannelProvider must map to a briefing section")


async def invalidate_for_provider(provider: str, user_id: UUID) -> None:
    """Drop the caches a change on ``provider`` makes stale for ``user_id``.

    - Every provider: the matching briefing section cache.
    - Gmail additionally: the per-user Gmail search caches (their pages may
      miss the new/changed messages).

    Best-effort: a Redis failure is logged at debug and swallowed — the
    webhook path must never fail on a missed cache optimization.
    """
    # Best-effort by doctrine: TTLs bound staleness when Redis is down.
    with contextlib.suppress(Exception):
        redis = await get_redis_cache()
        section = _PROVIDER_SECTIONS[provider]
        await redis.delete(f"{BRIEFING_CACHE_PREFIX}:{user_id}:{section}")

        if provider == PushChannelProvider.GOOGLE_GMAIL.value:
            keys: list[str] = []
            async for key in redis.scan_iter(match=f"{REDIS_KEY_GMAIL_SEARCH_PREFIX}{user_id}:*"):
                keys.append(key)
            for start in range(0, len(keys), _DELETE_BATCH_SIZE):
                await redis.delete(*keys[start : start + _DELETE_BATCH_SIZE])

        if provider == PushChannelProvider.GOOGLE_CALENDAR.value:
            # ADR-261 (P3): a changed agenda makes the cached departure advice
            # stale — the next heartbeat pass recomputes it from fresh events.
            departure_keys: list[str] = []
            async for key in redis.scan_iter(match=f"heartbeat:departure:{user_id}:*"):
                departure_keys.append(key)
            for start in range(0, len(departure_keys), _DELETE_BATCH_SIZE):
                await redis.delete(*departure_keys[start : start + _DELETE_BATCH_SIZE])

        logger.debug(
            "push_caches_invalidated",
            provider=provider,
            user_id=str(user_id),
        )
