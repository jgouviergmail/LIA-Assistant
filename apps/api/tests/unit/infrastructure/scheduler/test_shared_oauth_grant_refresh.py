"""A proactive refresh run processes a provider grant only once."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.infrastructure.scheduler import token_refresh


@pytest.mark.asyncio
async def test_proactive_refresh_deduplicates_linked_connectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_id = uuid4()
    user_id = uuid4()
    connectors = [
        Connector(
            id=uuid4(),
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted="encrypted",
            oauth_grant_id=shared_id,
        )
        for connector_type in (ConnectorType.GOOGLE_CALENDAR, ConnectorType.GOOGLE_TASKS)
    ]
    calls: list[object] = []

    @asynccontextmanager
    async def database():
        class Session:
            commit = AsyncMock()

        yield Session()

    class Repository:
        def __init__(self, db: object) -> None:
            pass

        async def get_active_oauth_connectors(self) -> list[Connector]:
            return connectors

    async def process(connector: Connector, threshold: object, db: object) -> str:
        calls.append(connector.id)
        return "refreshed"

    monkeypatch.setattr(token_refresh, "get_redis_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(token_refresh, "get_db_context", database)
    monkeypatch.setattr(token_refresh, "ConnectorRepository", Repository)
    monkeypatch.setattr(token_refresh, "_process_connector", process)

    await token_refresh.refresh_expiring_tokens()

    assert calls == [connectors[0].id]
