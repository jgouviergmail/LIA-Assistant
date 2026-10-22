"""Autonomous reads recheck native connector rows instead of a cached directory."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.connectors.models import Connector, ConnectorGlobalConfig, ConnectorType
from src.domains.connectors.provider_authority import resolve_active_connector_fresh
from src.domains.connectors.service import ConnectorService

pytestmark = pytest.mark.integration


async def test_global_withdrawal_and_revocation_close_the_fresh_provider_door(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async with AsyncSession(async_engine) as db:
        row = Connector(
            user_id=discussion_owner,
            connector_type=ConnectorType.GOOGLE_CALENDAR,
            credentials_encrypted="fictional-not-read",
            status="ACTIVE",
        )
        config = ConnectorGlobalConfig(
            connector_type=ConnectorType.GOOGLE_CALENDAR, is_enabled=True
        )
        db.add_all([row, config])
        await db.flush()
        service = ConnectorService(db)
        assert (
            await resolve_active_connector_fresh(discussion_owner, "calendar", service)
            == ConnectorType.GOOGLE_CALENDAR
        )
        config.is_enabled = False
        await db.flush()
        assert await resolve_active_connector_fresh(discussion_owner, "calendar", service) is None
        config.is_enabled = True
        row.status = "REVOKED"
        await db.flush()
        assert await resolve_active_connector_fresh(discussion_owner, "calendar", service) is None
