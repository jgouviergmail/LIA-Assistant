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
"""

from __future__ import annotations

from collections.abc import Callable
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
                return cached
        value = await _read_from_database(spec)
        if value is None:
            return spec.default
        if redis_key is not None:
            await _write_to_cache(spec, redis_key, value)
        return value
    except Exception as exc:  # noqa: BLE001 — bounded: a toggle never 500s
        logger.error("system_setting_read_failed", setting=key.value, error=str(exc))
        return spec.default


async def _read_from_cache(spec: SettingSpec[T], redis_key: str) -> T | None:
    """Return the cached value, or ``None`` on a miss or a Redis outage.

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
    if cached is None:
        return None
    raw = cached.decode() if isinstance(cached, bytes) else str(cached)
    return spec.decode(raw)


async def _write_to_cache(spec: SettingSpec[T], redis_key: str, value: T) -> None:
    """Populate the cache; a failure only costs the next lookup."""
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
        await redis.set(redis_key, spec.serialize(value), ex=spec.cache_ttl_seconds)
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
