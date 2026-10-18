"""Typed registry of administrator-controlled system settings.

The store is a string column, so every setting needs the same three things:
a way to decode the string, a cache with an invalidation, and a default for
when nothing is stored. Writing that by hand per key produced ~250 lines of
duplication for two keys; this module declares each key ONCE and derives the
rest.

Doctrine:
- **Completeness is asserted at boot** (ADR-085): every ``SystemSettingKey``
  member must appear in ``SETTING_SPECS`` or the application refuses to
  start. A silent fallback on an unknown key is how a setting dies invisibly.
- **Reading never raises.** An admin toggle sits on the request path; Redis
  down, database down, absent row or a hand-edited garbage value all resolve
  to the declared default. The default is therefore always the SAFE value.
- **A key may opt out of caching** (``redis_key=None``): a once-per-install
  marker has no business occupying a cache slot or paying an invalidation.
- **An absence is cached too**, as a marker that reads the CURRENT default: a
  key never written — every capability no administrator toggled — otherwise
  reached the database on every read, and the capability filter reads all of
  them on every turn. A reader older than the marker decodes it as a stored
  value, so the capability keys moved to a namespace it never reads
  (``REDIS_KEY_CAPABILITY_PREFIX``); the other cached keys decode the marker
  to their own safe default.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Generic, TypeVar

import structlog
from redis.exceptions import RedisError
from sqlalchemy import select

from src.core.constants import (
    REDIS_KEY_DEBUG_PANEL_ENABLED,
    REDIS_KEY_DEBUG_PANEL_USER_ACCESS_ENABLED,
    REDIS_KEY_INSTANCE_DAILY_BUDGET_EUR,
    REDIS_KEY_PUBLIC_DEMO_LINK_ENABLED,
    SYSTEM_SETTING_CACHE_TTL_SECONDS,
)
from src.domains.system_settings.models import SystemSetting, SystemSettingKey

logger = structlog.get_logger(__name__)

T = TypeVar("T")


# ============================================================================
# CODECS
# ============================================================================


def decode_bool(raw: str) -> bool:
    """Any casing of ``true`` is true; everything else is false."""
    return raw.strip().lower() == "true"


def encode_bool(value: bool) -> str:
    return "true" if value else "false"


def _decode_positive_decimal(raw: str) -> Decimal | None:
    """A strictly positive amount, or ``None`` when the value is unusable.

    A zero or negative ceiling is not a stricter limit, it is a broken row:
    "allow nothing" is expressed by disabling the feature, not by a bound
    nobody can satisfy. Returning ``None`` lets the caller fall back to its
    own configured value instead of trusting corruption.
    """
    try:
        value = Decimal(raw.strip())
    except InvalidOperation, ValueError:
        return None
    return value if value > 0 else None


def _encode_decimal(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def _decode_str(raw: str) -> str:
    return raw


def _encode_str(value: str) -> str:
    return value


# ============================================================================
# SPECS
# ============================================================================


@dataclass(frozen=True)
class SettingSpec(Generic[T]):
    """Everything the runtime needs to know about one setting.

    Attributes:
        key: The enum member this spec describes.
        default: Value used when nothing is stored or anything fails. It is
            the SAFE value by construction.
        decode: Turns the stored string into the typed value.
        serialize: Turns the typed value back into a storable string.
        redis_key: Cache key, or ``None`` to bypass the cache entirely.
        cache_ttl_seconds: Bounded staleness when the cache is used.
    """

    key: SystemSettingKey
    default: T
    decode: Callable[[str], T]
    serialize: Callable[[T], str]
    redis_key: str | None = None
    cache_ttl_seconds: int = SYSTEM_SETTING_CACHE_TTL_SECONDS


SETTING_SPECS: dict[SystemSettingKey, SettingSpec[Any]] = {
    **{
        key: SettingSpec(key=key, default=False, decode=decode_bool, serialize=encode_bool)
        for key in (
            SystemSettingKey.JEV_FILTER_EMAIL_ENABLED,
            SystemSettingKey.JEV_FILTER_EVENT_ENABLED,
            SystemSettingKey.JEV_FILTER_TASK_ENABLED,
            SystemSettingKey.JEV_FILTER_FILE_ENABLED,
            SystemSettingKey.JEV_RADIO_VERIFICATION_ENABLED,
            SystemSettingKey.JEV_CONSULTATION_PATH_ENABLED,
            SystemSettingKey.JEV_CONSULTATION_BOUNDED_ENABLED,
            SystemSettingKey.JEV_OBSERVE_MEMORY_ENABLED,
            SystemSettingKey.JEV_OBSERVE_INTERESTS_ENABLED,
            SystemSettingKey.JEV_OBSERVE_JOURNAL_ENABLED,
            SystemSettingKey.JEV_OBSERVE_OPEN_LOOPS_ENABLED,
            SystemSettingKey.JEV_HITL_EXCLUSION_ENABLED,
            SystemSettingKey.JEV_FILTER_REMINDER_ENABLED,
            SystemSettingKey.JEV_FILTER_TICKET_ENABLED,
            SystemSettingKey.JEV_FILTER_MCP_ENABLED,
            SystemSettingKey.JEV_FILTER_DOCUMENT_ENABLED,
            SystemSettingKey.JEV_INITIATIVE_UTILITY_ENABLED,
            SystemSettingKey.JEV_MEMORY_REFERENCE_PRESENCE_ENABLED,
            SystemSettingKey.JEV_HITL_REJECTION_ENABLED,
            SystemSettingKey.JEV_PARAMETER_KIND_ENABLED,
        )
    },
    SystemSettingKey.JEV_ENABLED: SettingSpec(
        key=SystemSettingKey.JEV_ENABLED,
        default=False,
        decode=decode_bool,
        serialize=encode_bool,
    ),
    SystemSettingKey.JEV_MEETING_TEMPLATE_ENABLED: SettingSpec(
        key=SystemSettingKey.JEV_MEETING_TEMPLATE_ENABLED,
        default=False,
        decode=decode_bool,
        serialize=encode_bool,
    ),
    SystemSettingKey.SELF_HOST_SEED_BUNDLE: SettingSpec(
        key=SystemSettingKey.SELF_HOST_SEED_BUNDLE,
        default="",
        decode=_decode_str,
        serialize=_encode_str,
        # Written once at install and read by an audit script: caching it
        # would add an invalidation path for a value nobody polls.
        redis_key=None,
    ),
    SystemSettingKey.DEBUG_PANEL_ENABLED: SettingSpec(
        key=SystemSettingKey.DEBUG_PANEL_ENABLED,
        default=False,
        decode=decode_bool,
        serialize=encode_bool,
        redis_key=REDIS_KEY_DEBUG_PANEL_ENABLED,
    ),
    SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED: SettingSpec(
        key=SystemSettingKey.DEBUG_PANEL_USER_ACCESS_ENABLED,
        default=False,
        decode=decode_bool,
        serialize=encode_bool,
        redis_key=REDIS_KEY_DEBUG_PANEL_USER_ACCESS_ENABLED,
    ),
    SystemSettingKey.DEMO_INSTANCE_MARKER: SettingSpec(
        key=SystemSettingKey.DEMO_INSTANCE_MARKER,
        default=False,
        decode=decode_bool,
        serialize=encode_bool,
        # No cache on purpose: this authorizes destroying every visitor
        # account, so it is read from the database every single time.
        redis_key=None,
    ),
    SystemSettingKey.PUBLIC_DEMO_LINK_ENABLED: SettingSpec(
        key=SystemSettingKey.PUBLIC_DEMO_LINK_ENABLED,
        # Off by default: never advertise a demonstrator nobody set up.
        default=False,
        decode=decode_bool,
        serialize=encode_bool,
        redis_key=REDIS_KEY_PUBLIC_DEMO_LINK_ENABLED,
    ),
    SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR: SettingSpec(
        key=SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR,
        # None = no operator ceiling; the deployment ceiling (environment)
        # still applies. An operator may only LOWER, never raise.
        default=None,
        decode=_decode_positive_decimal,
        serialize=_encode_decimal,
        redis_key=REDIS_KEY_INSTANCE_DAILY_BUDGET_EUR,
    ),
}


def get_setting_spec(key: SystemSettingKey) -> SettingSpec[Any]:
    """Return the declaration for ``key``.

    Args:
        key: The setting to look up.

    Returns:
        Its spec.

    Raises:
        KeyError: If the key was never declared (boot-time assert prevents it).
    """
    return SETTING_SPECS[key]


def assert_registry_completeness() -> None:
    """Refuse to boot when a setting key has no declaration (ADR-085).

    Raises:
        RuntimeError: Listing every undeclared key.
    """
    missing = [key.value for key in SystemSettingKey if key not in SETTING_SPECS]
    if missing:
        raise RuntimeError(
            "SETTING_SPECS is incomplete: no declaration for "
            f"{', '.join(sorted(missing))}. Every SystemSettingKey needs a "
            "spec (default, codec, cache) — see registry.py."
        )


# ============================================================================
# READ / INVALIDATE
# ============================================================================


#: Cached in place of a value when no row exists. It reads as the CURRENT
#: default, so a deployment that changes a default is never masked by a cached
#: copy of the old one; no serializer can produce it.
_ABSENT_MARKER = "\x00absent"


@dataclass(frozen=True)
class _Cached(Generic[T]):
    """A cache hit — ``None`` meaning a miss, a ``None`` value can be a hit."""

    value: T


async def _read_from_database(spec: SettingSpec[T]) -> T | None:
    """Return the decoded stored value, or ``None`` when there is no row."""
    from src.infrastructure.database import get_db_context

    async with get_db_context() as db:
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == spec.key))
        setting = result.scalar_one_or_none()
    if setting is None:
        return None
    return spec.decode(setting.value)


async def read_setting(key: SystemSettingKey) -> Any:
    """Read one setting through cache, then database, then its default.

    Never raises: a failure anywhere resolves to the declared default, which
    is the safe value by construction.

    Args:
        key: The setting to read.

    Returns:
        The typed value.
    """
    spec = get_setting_spec(key)
    redis_key = spec.redis_key
    try:
        if redis_key is not None:
            cached = await _read_from_cache(spec, redis_key)
            if cached is not None:
                return cached.value
        value = await _read_from_database(spec)
        if redis_key is not None:
            await _write_to_cache(spec, redis_key, value)
        return spec.default if value is None else value
    except Exception as exc:  # noqa: BLE001 — bounded: a toggle never 500s
        logger.error("system_setting_read_failed", setting=key.value, error=str(exc))
        return spec.default


async def read_settings(keys: Collection[SystemSettingKey]) -> dict[SystemSettingKey, Any]:
    """Read several settings in two round trips at most.

    One cache ``MGET``, then one ``SELECT … IN`` for whatever the cache did
    not hold, absences cached as such. Same contract as :func:`read_setting`:
    never raises, every key resolves — to its default when anything fails.

    Args:
        keys: The settings to read.

    Returns:
        Each key's typed value.
    """
    specs = [get_setting_spec(key) for key in dict.fromkeys(keys)]
    values: dict[SystemSettingKey, Any] = {spec.key: spec.default for spec in specs}
    try:
        pending = await _read_many_from_cache(specs, values)
        if pending:
            stored = await _read_many_from_database(pending)
            for spec in pending:
                value = stored.get(spec.key)
                values[spec.key] = spec.default if value is None else value
            await _write_many_to_cache(_cache_entries(pending), stored)
    except Exception as exc:  # noqa: BLE001 — bounded: a toggle never 500s
        logger.error(
            "system_settings_read_failed", setting_count=len(specs), error=type(exc).__name__
        )
    return values


async def _read_many_from_cache(
    specs: list[SettingSpec[Any]], values: dict[SystemSettingKey, Any]
) -> list[SettingSpec[Any]]:
    """Fill ``values`` with the cache hits; return the specs left to read.

    A Redis outage leaves every cached key to the database; an undecodable
    cached value is read again from the database rather than trusted.
    """
    from src.infrastructure.cache.redis import get_redis_cache

    entries = _cache_entries(specs)
    cached_specs = [spec for spec, _redis_key in entries]
    pending = [spec for spec in specs if spec.redis_key is None]
    if not entries:
        return pending
    try:
        redis = await get_redis_cache()
        raws = await redis.mget([redis_key for _spec, redis_key in entries])
    except (RedisError, OSError) as exc:
        logger.warning("system_settings_cache_read_failed", error=str(exc))
        return pending + cached_specs
    for spec, cached in zip(cached_specs, raws, strict=True):
        hit = _decode_cached(spec, cached)
        if hit is None:
            pending.append(spec)
        else:
            values[spec.key] = hit.value
    return pending


async def _read_many_from_database(specs: list[SettingSpec[Any]]) -> dict[SystemSettingKey, Any]:
    """The decoded stored values of ``specs`` — one query, a key per existing row.

    A row that does not decode is left out: it reads as its default, like a
    single read of it would.
    """
    from src.infrastructure.database import get_db_context

    by_key = {spec.key: spec for spec in specs}
    async with get_db_context() as db:
        result = await db.execute(
            select(SystemSetting.key, SystemSetting.value).where(
                SystemSetting.key.in_(list(by_key))
            )
        )
        rows = result.all()
    stored: dict[SystemSettingKey, Any] = {}
    for key, raw in rows:
        try:
            stored[key] = by_key[key].decode(raw)
        except Exception as exc:  # noqa: BLE001 — garbage reads as the default
            logger.warning("system_setting_decode_failed", setting=key.value, error=str(exc))
    return stored


async def _write_many_to_cache(
    entries: list[tuple[SettingSpec[Any], str]], stored: dict[SystemSettingKey, Any]
) -> None:
    """Cache each value read — an absence as its marker; a failure only costs the next read."""
    from src.infrastructure.cache.redis import get_redis_cache

    if not entries:
        return
    try:
        redis = await get_redis_cache()
        async with redis.pipeline(transaction=False) as pipe:
            for spec, redis_key in entries:
                payload = _cache_payload(spec, stored.get(spec.key))
                pipe.set(redis_key, payload, ex=spec.cache_ttl_seconds)
            await pipe.execute()
    except (RedisError, OSError) as exc:
        logger.warning("system_settings_cache_write_failed", error=str(exc))


def _cache_entries(specs: list[SettingSpec[Any]]) -> list[tuple[SettingSpec[Any], str]]:
    """The cached specs of ``specs``, each with its Redis key."""
    return [(spec, spec.redis_key) for spec in specs if spec.redis_key is not None]


def _decode_cached(spec: SettingSpec[T], cached: object) -> _Cached[T] | None:
    """A cache hit, or ``None`` for a miss (or a cached value that no longer decodes)."""
    if cached is None:
        return None
    raw = cached.decode() if isinstance(cached, bytes) else str(cached)
    if raw == _ABSENT_MARKER:
        return _Cached(spec.default)
    try:
        return _Cached(spec.decode(raw))
    except Exception:  # noqa: BLE001 — the database answers instead
        return None


def _cache_payload(spec: SettingSpec[T], value: T | None) -> str:
    """What the cache holds for ``value``: its serialization, or the absence marker."""
    return _ABSENT_MARKER if value is None else spec.serialize(value)


async def _read_from_cache(spec: SettingSpec[T], redis_key: str) -> _Cached[T] | None:
    """Return the cache hit, or ``None`` on a miss or a Redis outage.

    ``redis_key`` is passed rather than read off the spec so the "this key is
    cached" precondition lives in the signature instead of a cast.
    """
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
        cached = await redis.get(redis_key)
    except (RedisError, OSError) as exc:
        logger.warning("system_setting_cache_read_failed", setting=spec.key.value, error=str(exc))
        return None
    return _decode_cached(spec, cached)


async def _write_to_cache(spec: SettingSpec[T], redis_key: str, value: T | None) -> None:
    """Populate the cache — an absence as its marker; a failure only costs the next lookup."""
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
        await redis.set(redis_key, _cache_payload(spec, value), ex=spec.cache_ttl_seconds)
    except (RedisError, OSError) as exc:
        logger.warning("system_setting_cache_write_failed", setting=spec.key.value, error=str(exc))


async def invalidate_setting_cache(key: SystemSettingKey) -> None:
    """Drop the cached value after an administrator changed it.

    A failure is survivable — the TTL bounds the staleness — so it is logged
    rather than propagated to the admin request.

    Args:
        key: The setting whose cache must be dropped.
    """
    from src.infrastructure.cache.redis import get_redis_cache

    spec = get_setting_spec(key)
    if spec.redis_key is None:
        return
    try:
        redis = await get_redis_cache()
        await redis.delete(spec.redis_key)
        logger.debug("system_setting_cache_invalidated", setting=key.value)
    except (RedisError, OSError) as exc:
        logger.warning(
            "system_setting_cache_invalidation_failed",
            setting=key.value,
            error=str(exc),
        )
