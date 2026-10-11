"""Authoritative post-command reads remain available when cache invalidation fails."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.connectors.service import ConnectorService

pytestmark = pytest.mark.unit


async def test_fresh_connector_list_cannot_be_blocked_or_falsified_by_redis() -> None:
    actor_id = uuid4()
    service = ConnectorService(AsyncMock(spec=AsyncSession))
    service.repository.get_all_by_user = AsyncMock(return_value=[])
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        side_effect=AssertionError("An authoritative read consulted the unavailable cache"),
    ):
        result = await service.get_user_connectors(actor_id, fresh=True)
    assert result.connectors == [] and result.total == 0
    service.repository.get_all_by_user.assert_awaited_once_with(actor_id)
