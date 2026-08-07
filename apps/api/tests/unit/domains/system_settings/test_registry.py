"""Typed registry of administrator-controlled system settings.

Until now every setting was hand-written: two keys produced ~250 lines of
duplicated cache/fallback/invalidate code each. The live-demonstrator
programme adds a spend ceiling and a family of capability switches, which
would have meant copying that block a dozen times.

What must hold:
- one declaration per key, and the boot asserts EVERY enum member has one
  (ADR-085 doctrine: a missing entry refuses to boot, it never falls back
  silently);
- values are TYPED (bool, Decimal, str): the store is a string column, so
  parsing lives in exactly one place;
- reading never raises: Redis down, database down, absent row, or garbage
  stored by hand all resolve to the declared default;
- a key declared without a cache is read straight from the database (a
  once-per-install marker must not occupy a cache slot);
- writing a setting invalidates its cache; a cache-invalidation failure is
  survivable (the TTL bounds it) and never propagates.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError

from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.registry import (
    SETTING_SPECS,
    assert_registry_completeness,
    get_setting_spec,
    invalidate_setting_cache,
    read_setting,
)

pytestmark = pytest.mark.unit


def _redis(cached: object | None = None, *, failing: bool = False) -> MagicMock:
    redis = MagicMock()
    if failing:
        redis.get = AsyncMock(side_effect=RedisError("redis down"))
        redis.set = AsyncMock(side_effect=RedisError("redis down"))
        redis.delete = AsyncMock(side_effect=RedisError("redis down"))
    else:
        redis.get = AsyncMock(return_value=cached)
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
    return redis


def _db_context(stored_value: str | None) -> MagicMock:
    """A get_db_context() double whose single row holds ``stored_value``."""
    setting = MagicMock(value=stored_value) if stored_value is not None else None
    result = MagicMock()
    result.scalar_one_or_none.return_value = setting
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=context)


def _patched(redis: MagicMock, db_context: MagicMock) -> tuple[object, object]:
    return (
        patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis)),
        patch("src.infrastructure.database.get_db_context", db_context),
    )


# ---------------------------------------------------------------------------
# Completeness (ADR-085)
# ---------------------------------------------------------------------------


def test_every_setting_key_is_declared_in_the_registry() -> None:
    assert_registry_completeness()
    assert set(SETTING_SPECS) == set(SystemSettingKey)


def test_completeness_assert_refuses_a_key_without_a_declaration() -> None:
    incomplete = {
        k: v for k, v in SETTING_SPECS.items() if k != SystemSettingKey.DEBUG_PANEL_ENABLED
    }
    with patch("src.domains.system_settings.registry.SETTING_SPECS", incomplete):
        with pytest.raises(RuntimeError, match="debug_panel_enabled"):
            assert_registry_completeness()


def test_each_cached_key_owns_a_distinct_redis_key() -> None:
    cache_keys = [spec.redis_key for spec in SETTING_SPECS.values() if spec.redis_key]
    # A shared cache key would make one setting read another's value.
    assert len(cache_keys) == len(set(cache_keys))


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


async def test_read_returns_the_cached_value_without_touching_the_database() -> None:
    redis = _redis(b"true")
    db_context = _db_context(None)
    cache_patch, db_patch = _patched(redis, db_context)
    with cache_patch, db_patch:
        value = await read_setting(SystemSettingKey.DEBUG_PANEL_ENABLED)
    assert value is True
    db_context.assert_not_called()


async def test_read_falls_back_to_the_database_and_caches_the_result() -> None:
    redis = _redis(None)
    db_context = _db_context("true")
    cache_patch, db_patch = _patched(redis, db_context)
    with cache_patch, db_patch:
        value = await read_setting(SystemSettingKey.DEBUG_PANEL_ENABLED)
    assert value is True
    redis.set.assert_awaited_once()
    assert (
        redis.set.await_args.args[0]
        == get_setting_spec(SystemSettingKey.DEBUG_PANEL_ENABLED).redis_key
    )


async def test_read_returns_the_declared_default_when_nothing_is_stored() -> None:
    redis = _redis(None)
    cache_patch, db_patch = _patched(redis, _db_context(None))
    with cache_patch, db_patch:
        assert await read_setting(SystemSettingKey.DEBUG_PANEL_ENABLED) is False


async def test_read_survives_a_redis_outage_by_using_the_database() -> None:
    cache_patch, db_patch = _patched(_redis(failing=True), _db_context("true"))
    with cache_patch, db_patch:
        assert await read_setting(SystemSettingKey.DEBUG_PANEL_ENABLED) is True


async def test_read_returns_the_default_when_both_backends_are_down() -> None:
    db_context = MagicMock(side_effect=RuntimeError("db down"))
    cache_patch, db_patch = _patched(_redis(failing=True), db_context)
    with cache_patch, db_patch:
        # An admin toggle must never take the request path down with it.
        assert await read_setting(SystemSettingKey.DEBUG_PANEL_ENABLED) is False


async def test_read_returns_the_default_when_the_stored_value_is_garbage() -> None:
    cache_patch, db_patch = _patched(_redis(None), _db_context("not-a-number"))
    with cache_patch, db_patch:
        value = await read_setting(SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR)
    # A hand-edited row must not become an unbounded ceiling.
    assert value is None


async def test_a_key_declared_without_a_cache_reads_the_database_directly() -> None:
    redis = _redis(b"unexpected")
    db_context = _db_context("abc123")
    cache_patch, db_patch = _patched(redis, db_context)
    with cache_patch, db_patch:
        value = await read_setting(SystemSettingKey.SELF_HOST_SEED_BUNDLE)
    assert value == "abc123"
    redis.get.assert_not_awaited()
    redis.set.assert_not_awaited()


# ---------------------------------------------------------------------------
# Typed decoding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("true", True), ("TRUE", True), ("True", True), ("false", False), ("", False)],
)
async def test_boolean_settings_decode_case_insensitively(stored: str, expected: bool) -> None:
    cache_patch, db_patch = _patched(_redis(None), _db_context(stored))
    with cache_patch, db_patch:
        assert await read_setting(SystemSettingKey.DEBUG_PANEL_ENABLED) is expected


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("1", Decimal("1")), ("0.50", Decimal("0.50")), ("1.234567", Decimal("1.234567"))],
)
async def test_decimal_settings_decode_exactly(stored: str, expected: Decimal) -> None:
    cache_patch, db_patch = _patched(_redis(None), _db_context(stored))
    with cache_patch, db_patch:
        assert await read_setting(SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR) == expected


@pytest.mark.parametrize("stored", ["0", "-1"])
async def test_a_non_positive_ceiling_is_rejected_as_meaningless(stored: str) -> None:
    cache_patch, db_patch = _patched(_redis(None), _db_context(stored))
    with cache_patch, db_patch:
        # "Zero euro allowed" is expressed by disabling the demo, not by a
        # ceiling nobody can satisfy; a negative one is plain corruption.
        assert await read_setting(SystemSettingKey.INSTANCE_DAILY_BUDGET_EUR) is None


def test_every_spec_serializes_its_own_default_back_to_a_storable_string() -> None:
    for key, spec in SETTING_SPECS.items():
        if spec.default is None:
            continue
        stored = spec.serialize(spec.default)
        assert isinstance(stored, str), key
        # Round-trip: what we write must read back identical, or the admin
        # panel would show a value the database does not hold.
        assert spec.decode(stored) == spec.default, key


def test_a_stored_value_never_exceeds_the_database_column() -> None:
    for key, spec in SETTING_SPECS.items():
        if spec.default is None:
            continue
        # system_settings.value is String(255).
        assert len(spec.serialize(spec.default)) <= 255, key


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


async def test_invalidation_deletes_exactly_the_key_cache() -> None:
    redis = _redis()
    with patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis)):
        await invalidate_setting_cache(SystemSettingKey.DEBUG_PANEL_ENABLED)
    redis.delete.assert_awaited_once_with(
        get_setting_spec(SystemSettingKey.DEBUG_PANEL_ENABLED).redis_key
    )


async def test_invalidating_an_uncached_key_is_a_no_op() -> None:
    redis = _redis()
    with patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis)):
        await invalidate_setting_cache(SystemSettingKey.SELF_HOST_SEED_BUNDLE)
    redis.delete.assert_not_awaited()


async def test_invalidation_failure_never_propagates() -> None:
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        AsyncMock(return_value=_redis(failing=True)),
    ):
        # The TTL bounds the staleness; failing the admin write would be worse.
        await invalidate_setting_cache(SystemSettingKey.DEBUG_PANEL_ENABLED)
