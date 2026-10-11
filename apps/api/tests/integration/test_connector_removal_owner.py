"""Real SQL local unlink preserves shared access and does not invert OAuth lock order."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.exceptions import ResourceConflictError
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType, OAuthGrant
from src.domains.connectors.oauth_grant_runtime import OAuthGrantRuntime
from src.domains.connectors.removal_commands import (
    connector_removal_snapshot,
    locked_connector_for_removal,
)
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


def link(actor_id, grant_id=None, kind=ConnectorType.GOOGLE_GMAIL) -> Connector:
    return Connector(
        id=uuid4(),
        user_id=actor_id,
        connector_type=kind,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="private-token",
        oauth_grant_id=grant_id,
    )


def grant_for(actor_id) -> OAuthGrant:
    return OAuthGrant(
        id=uuid4(),
        user_id=actor_id,
        provider="google",
        client_id="test-only",
        subject=str(uuid4()),
        scopes=[],
        credentials_encrypted="private-shared-token",
    )


@pytest.mark.parametrize("sibling", [False, True])
async def test_local_unlink_preserves_other_services_and_drops_only_the_last_local_grant(
    async_session: AsyncSession,
    test_user: User,
    sibling: bool,
) -> None:
    grant = grant_for(test_user.id)
    target = link(test_user.id, grant.id)
    remaining = link(test_user.id, grant.id, ConnectorType.GOOGLE_CALENDAR)
    async_session.add(grant)
    await async_session.flush()
    async_session.add(target)
    if sibling:
        async_session.add(remaining)
    await async_session.commit()
    await async_session.refresh(target)
    expected = connector_removal_snapshot(target)
    service = ConnectorService(async_session)
    service._invalidate_user_connectors_cache = AsyncMock()
    receipt = PreferenceWriteReceipt()
    await service.delete_connector(test_user.id, target.id, expected=expected, receipt=receipt)
    assert receipt.committed
    assert await async_session.scalar(select(Connector.id).where(Connector.id == target.id)) is None
    assert (
        await async_session.scalar(select(OAuthGrant.id).where(OAuthGrant.id == grant.id))
        is not None
    ) is sibling
    if sibling:
        assert (
            await async_session.scalar(select(Connector.id).where(Connector.id == remaining.id))
            == remaining.id
        )


async def test_changed_connection_is_not_removed_by_the_previous_preview(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    target = link(test_user.id)
    async_session.add(target)
    await async_session.commit()
    await async_session.refresh(target)
    expected = connector_removal_snapshot(target)
    target.status = ConnectorStatus.INACTIVE
    await async_session.commit()
    with pytest.raises(ResourceConflictError):
        await ConnectorService(async_session).delete_connector(
            test_user.id, target.id, expected=expected
        )
    assert (
        await async_session.scalar(select(Connector.id).where(Connector.id == target.id))
        == target.id
    )


async def test_committed_unlink_and_authoritative_read_survive_cache_failure(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    target = link(test_user.id)
    async_session.add(target)
    await async_session.commit()
    await async_session.refresh(target)
    expected = connector_removal_snapshot(target)
    service = ConnectorService(async_session)
    service._invalidate_user_connectors_cache = AsyncMock(
        side_effect=ConnectionError("cache unavailable")
    )
    receipt = PreferenceWriteReceipt()
    with pytest.raises(ConnectionError):
        await service.delete_connector(test_user.id, target.id, expected=expected, receipt=receipt)
    assert receipt.committed
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        side_effect=AssertionError("Cache consulted"),
    ):
        current = await service.get_user_connectors(test_user.id, fresh=True)
    assert all(row.id != target.id for row in current.connectors)


async def test_oauth_writer_and_unlink_can_finish_without_a_grant_connection_deadlock(
    async_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(
        id=uuid4(),
        email=f"unlink-race-{uuid4()}@example.test",
        hashed_password="test-only",
        is_active=True,
        is_verified=True,
    )
    grant = grant_for(actor.id)
    target = link(actor.id, grant.id)
    try:
        async with sessions() as seed:
            seed.add(actor)
            await seed.flush()
            seed.add(grant)
            await seed.flush()
            seed.add(target)
            await seed.commit()
        async with sessions() as writer, sessions() as unlink:
            held = await writer.scalar(
                select(OAuthGrant).where(OAuthGrant.id == grant.id).with_for_update()
            )
            assert held is not None
            awaiting_grant = asyncio.Event()
            connection = await unlink.connection()

            def notice(_conn, _cursor, statement, _parameters, _context, _executemany):
                if "oauth_grants" in statement and "FOR UPDATE" in statement:
                    awaiting_grant.set()

            event.listen(connection.sync_connection, "before_cursor_execute", notice)
            pending = asyncio.create_task(locked_connector_for_removal(unlink, actor.id, target.id))
            try:
                await asyncio.wait_for(awaiting_grant.wait(), timeout=5)
                linked = await asyncio.wait_for(OAuthGrantRuntime(writer)._linked(held), timeout=5)
                assert [row.id for row in linked] == [target.id]
                await writer.commit()
                assert (await asyncio.wait_for(pending, timeout=5)).id == target.id
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                event.remove(connection.sync_connection, "before_cursor_execute", notice)
    finally:
        async with sessions() as cleanup:
            await cleanup.execute(delete(User).where(User.id == actor.id))
            await cleanup.commit()
