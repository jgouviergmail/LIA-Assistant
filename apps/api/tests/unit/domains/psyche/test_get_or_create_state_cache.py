"""Characterization for ``PsycheService.get_or_create_state`` — no pseudo-cache.

Audit finding F035: the former Redis "cache" never served a value. Its read path
(``_load_from_cache``) returned ``None`` unconditionally ("v1: always read from
DB"), so the ``if cached: return cached`` branch was dead and the DB was queried
on every call — while ``_save_to_cache`` still wrote a marker to Redis on every
access. Two network round-trips per call for provably zero benefit, and a
docstring/comment claiming it "saves the DB query".

The honest fix (measured statically: hit-rate benefit is exactly zero) is to
remove the pseudo-cache. This test pins the resulting contract: a DB-backed read
returns the persisted state and performs no Redis interaction.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.psyche.service import PsycheService

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_get_or_create_state_serves_db_without_redis_roundtrip():
    """A DB-backed psyche state is returned without touching Redis at all."""
    user_id = uuid4()
    db_state = MagicMock(name="PsycheState")

    service = PsycheService(AsyncMock())
    service.repo = MagicMock()
    service.repo.get_by_user_id = AsyncMock(return_value=db_state)

    with patch("src.infrastructure.cache.redis.get_redis_cache", new=AsyncMock()) as redis_factory:
        result = await service.get_or_create_state(user_id)

    assert result is db_state
    service.repo.get_by_user_id.assert_awaited_once_with(user_id)
    redis_factory.assert_not_called()
