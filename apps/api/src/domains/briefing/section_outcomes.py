"""What one live read of a briefing section leaves behind in the cache.

Extracted from ``BriefingService._section`` (its file is at its size cap), with
two additions measured on production (spec 2026-10-21 §0ter):

- **An attempt marker** (A8, E12). A failed source was never cached, so every
  completeness reader — ``/synthesis``, a waiter of the cross-worker build —
  saw the bundle as incomplete and rebuilt it, opening the failing source
  again: on the owner's account 92 % of ``/synthesis`` calls found an
  incomplete bundle. An ERROR read now leaves its section (stale copy
  included) under a short-lived marker that ONLY the completeness readers
  consult (``read_settled_section``): the failure is settled for them, while
  ``_section``'s own cache read ignores it, so the next page load retries the
  source live. A success clears the marker.
- **A generation fence** (E5; Facebook memcache leases, NSDI 2013). A push
  invalidation deletes a section's cache, but a read already in flight used to
  write its older payload right after — a stale card for a whole TTL. The push
  now bumps the section's generation (``bump_section_generation``); the read
  takes the generation BEFORE its fetch and its write commits only if it is
  unchanged, in one Redis script. A push during a read leaves the section
  missing — the next read is live — never stale.

Every Redis failure falls back to the write that existed before (the floor).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.briefing.cache_keys import (
    attempt_marker_key,
    last_good_key,
    section_cache_key,
    section_generation_key,
)
from src.domains.briefing.card_content import _has_content
from src.domains.briefing.classification import expire_cached_annotations
from src.domains.briefing.constants import ERROR_CODE_INTERNAL, SECTION_GENERATION_TTL_SECONDS
from src.domains.briefing.exceptions import ConnectorAccessError, ConnectorNotConfiguredError
from src.domains.briefing.schemas import CardSection, CardStatus
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.metrics_briefing import (
    briefing_section_attempt_markers_total,
    briefing_section_writes_fenced_total,
)

logger = structlog.get_logger(__name__)

#: Reads one cached section by key, or None.
SectionReader = Callable[[str], Awaitable[CardSection | None]]

ORIGIN_LIVE = "live"
ORIGIN_STALE = "stale"  # D-04: last known-good served alongside an ERROR

#: Outcomes a later read may serve from cache (ERROR retries on the next request).
_CACHEABLE = frozenset({CardStatus.OK, CardStatus.EMPTY, CardStatus.NOT_CONFIGURED})

#: Clear the attempt marker, then write the payload only if no push bumped the
#: section's generation since the read began. An absent generation reads as '0'.
#: Returns {written, markers cleared}.
FENCED_WRITE_SCRIPT = """
local cleared = redis.call('del', KEYS[3])
local current = redis.call('get', KEYS[2]) or '0'
if current == ARGV[2] then
    redis.call('set', KEYS[1], ARGV[1], 'EX', ARGV[3])
    return {1, cleared}
end
return {0, cleared}
"""

#: Bump a section's generation, bounded so an idle account leaves nothing behind.
BUMP_GENERATION_SCRIPT = """
local value = redis.call('incr', KEYS[1])
redis.call('expire', KEYS[1], ARGV[1])
return value
"""


@dataclass(frozen=True)
class SectionKeys:
    """Every key one section's live read touches.

    Attributes:
        cache: The payload served to the next reads.
        last_good: The long-lived last known-good copy (D-04).
        marker: The short-lived record of a failed attempt.
        generation: The section's push generation (language-independent).
    """

    cache: str
    last_good: str
    marker: str
    generation: str


def section_keys(*, user_id: UUID, language: str, section: str, cache_section: str) -> SectionKeys:
    """The keys of one section for one reader.

    Args:
        user_id: Whose dashboard.
        language: The language the payload is formatted in.
        section: The section's name, as the push invalidation knows it.
        cache_section: The name its payload is cached under (an editorial
            variant of the mails, for instance).

    Returns:
        The section's keys.
    """
    return SectionKeys(
        cache=section_cache_key(user_id=user_id, language=language, section=cache_section),
        last_good=last_good_key(user_id=user_id, language=language, section=cache_section),
        marker=attempt_marker_key(user_id=user_id, language=language, section=cache_section),
        generation=section_generation_key(user_id=user_id, section=section),
    )


async def read_generation(key: str) -> str | None:
    """The section's generation before a live read, or None when it cannot be read.

    Args:
        key: The generation key.

    Returns:
        The generation ('0' when absent), or None on a cache failure — the
        write then falls back to the unfenced one.
    """
    try:
        redis = await get_redis_cache()
        raw = await redis.get(key)
    except Exception as exc:  # noqa: BLE001 - a missing fence is the old write, not an outage
        logger.debug("briefing_generation_read_failed", error_type=type(exc).__name__)
        return None
    if raw is None:
        return "0"
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


async def persist_live_outcome(
    name: str,
    section: CardSection,
    *,
    keys: SectionKeys,
    ttl: int,
    generation: str | None,
) -> tuple[CardSection, str]:
    """Cache what a live read produced, remember a failure, and serve a stale copy.

    Args:
        name: The section's name (metric label).
        section: What the live read produced.
        keys: The section's keys.
        ttl: The section's cache TTL; 0 means the section is never cached.
        generation: The generation read before the fetch; None writes unfenced.

    Returns:
        The section (an ERROR carries its last known-good copy when there is
        one) and its origin label.
    """
    if ttl <= 0:
        return section, ORIGIN_LIVE
    if section.status in _CACHEABLE:
        await _write_fenced(name, section, keys=keys, ttl=ttl, generation=generation)
    if section.status is CardStatus.OK and section.data is not None:
        await _write_last_good(keys.last_good, section)
        return section, ORIGIN_LIVE
    if section.status is not CardStatus.ERROR:
        return section, ORIGIN_LIVE
    section = await _attach_stale(keys.last_good, section)
    await _write_marker(keys.marker, section)
    return section, ORIGIN_STALE if section.data is not None else ORIGIN_LIVE


async def fetch_and_map(
    name: str,
    fetcher: Callable[[], Awaitable[Any]],
    *,
    user_id: UUID,
) -> CardSection:
    """Run the live fetch and map the outcome to a CardSection.

    Extracted from ``BriefingService._section`` (CC discipline). **Never
    raises** — the exception taxonomy maps to statuses; ERROR sections carry
    ``last_attempt_at`` (D-04 honest freshness).

    Args:
        name: The section, for the logs.
        fetcher: The section's live read.
        user_id: The account, for the logs.

    Returns:
        The section the outcome maps to.
    """
    now = datetime.now(UTC)
    try:
        data = await fetcher()
        return CardSection(
            status=CardStatus.OK if _has_content(data) else CardStatus.EMPTY,
            data=data if _has_content(data) else None,
            generated_at=now,
        )
    except ConnectorNotConfiguredError as exc:
        return CardSection(
            status=CardStatus.NOT_CONFIGURED,
            generated_at=now,
            error_code=exc.error_code,
        )
    except ConnectorAccessError as exc:
        logger.info(
            "briefing_section_access_error",
            section=name,
            user_id=str(user_id),
            error_code=exc.error_code,
            source=exc.source,
        )
        return CardSection(
            status=CardStatus.ERROR,
            generated_at=now,
            error_code=exc.error_code,
            error_message=exc.message,
            last_attempt_at=now,
        )
    except Exception as exc:  # safety net
        # Its facts only: a connector's error text quotes what it read (ADR-317).
        logger.warning(
            "briefing_section_failed",
            section=name,
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return CardSection(
            status=CardStatus.ERROR,
            generated_at=now,
            error_code=ERROR_CODE_INTERNAL,
            last_attempt_at=now,
        )


async def read_settled_section(read: SectionReader, keys: SectionKeys) -> CardSection | None:
    """A completeness reader's view: the cached payload, else a recent failed attempt.

    Args:
        read: Reads one cached section by key (the service's own reader).
        keys: The section's keys.

    Returns:
        The cached section, the attempt marker's ERROR section, or None.
    """
    cached = await read(keys.cache)
    if cached is not None:
        return cached
    marker = await read(keys.marker)
    if marker is not None:
        briefing_section_attempt_markers_total.labels(outcome="settled").inc()
    return marker


async def bump_section_generation(*, user_id: UUID | str, section: str) -> None:
    """Fence off every read of the section already in flight (a push changed the source).

    Raises:
        Exception: Whatever the cache raised — the push path is best-effort by
            doctrine and swallows it.
    """
    redis = await get_redis_cache()
    await redis.eval(
        BUMP_GENERATION_SCRIPT,
        1,
        section_generation_key(user_id=user_id, section=section),
        SECTION_GENERATION_TTL_SECONDS,
    )


async def read_section(key: str) -> CardSection | None:
    """One cached section, or None when absent, unreadable or the cache is down.

    Args:
        key: The section's cache key.

    Returns:
        The section, its expired annotations removed.
    """
    try:
        redis = await get_redis_cache()
        raw = await redis.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return expire_cached_annotations(CardSection.model_validate_json(raw))
    except Exception as exc:  # noqa: BLE001 - the cache is best-effort
        logger.debug("briefing_cache_read_failed", key=key, error_type=type(exc).__name__)
        return None


async def write_section(key: str, section: CardSection, ttl: int) -> None:
    """Write one section, best-effort.

    Args:
        key: The cache key.
        section: The section.
        ttl: Its time to live.
    """
    try:
        redis = await get_redis_cache()
        await redis.set(key, section.model_dump_json(), ex=ttl)
    except Exception as exc:  # noqa: BLE001 - the cache is best-effort
        logger.debug("briefing_cache_write_failed", key=key, error_type=type(exc).__name__)


async def _write_fenced(
    name: str, section: CardSection, *, keys: SectionKeys, ttl: int, generation: str | None
) -> None:
    """Write the payload unless a push bumped the generation; clear any attempt marker."""
    if generation is None:
        await write_section(keys.cache, section, ttl)
        await _clear_marker(keys.marker)
        return
    try:
        redis = await get_redis_cache()
        written, cleared = await redis.eval(
            FENCED_WRITE_SCRIPT,
            3,
            keys.cache,
            keys.generation,
            keys.marker,
            section.model_dump_json(),
            generation,
            ttl,
        )
    except Exception as exc:  # noqa: BLE001 - the cache is best-effort
        logger.debug("briefing_fenced_write_failed", section=name, error_type=type(exc).__name__)
        return
    if cleared:
        briefing_section_attempt_markers_total.labels(outcome="cleared").inc()
    if not written:
        briefing_section_writes_fenced_total.labels(section=name).inc()
        logger.info("briefing_section_write_fenced", section=name)


async def _write_last_good(key: str, section: CardSection) -> None:
    """Remember an OK-with-data payload under the long-TTL side key (0 disables)."""
    ttl = settings.briefing_last_good_ttl_seconds
    if ttl > 0:
        await write_section(key, section, ttl)


async def _attach_stale(key: str, section: CardSection) -> CardSection:
    """Fill an ERROR section with the last known-good payload, if any.

    The error stays the STATUS (code, message, CTA all keep working); the
    stale payload rides along with its own original timestamp so the card can
    say "data from 09:12 — connector unreachable" instead of showing a hole.
    """
    stale = await read_section(key)
    if stale is None or stale.data is None:
        return section
    section.data = stale.data
    section.stale_generated_at = stale.generated_at
    return section


async def _write_marker(key: str, section: CardSection) -> None:
    """Settle the failure for the completeness readers, for a short while (0 disables)."""
    ttl = settings.briefing_section_attempt_marker_seconds
    if ttl <= 0:
        return
    await write_section(key, section, ttl)
    briefing_section_attempt_markers_total.labels(outcome="written").inc()


async def _clear_marker(key: str) -> None:
    """Drop a failed attempt's marker after a success read without a fence."""
    try:
        redis = await get_redis_cache()
        cleared: Any = await redis.delete(key)
    except Exception as exc:  # noqa: BLE001 - the marker expires on its own
        logger.debug("briefing_marker_clear_failed", error_type=type(exc).__name__)
        return
    if cleared:
        briefing_section_attempt_markers_total.labels(outcome="cleared").inc()


__all__ = [
    "ORIGIN_LIVE",
    "ORIGIN_STALE",
    "SectionKeys",
    "bump_section_generation",
    "fetch_and_map",
    "persist_live_outcome",
    "read_generation",
    "read_section",
    "read_settled_section",
    "section_keys",
    "write_section",
]
