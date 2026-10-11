"""Real independent transactions prove GUI pair creation cannot cross native comparison."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.peer_request import execute_peer_request, prepare_peer_request
from src.domains.agents.application.peer_request_schemas import PeerRequestInput
from src.domains.peers.models import PeerConnection
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_source_request_uses_real_canonical_account_fence(async_engine):
    identities = [uuid4(), uuid4()]
    async with AsyncSession(async_engine) as seed:
        seed.add_all(
            [
                User(
                    id=identity,
                    email=f"pair-fence-{identity}@example.com",
                    full_name="Controlled peer",
                    is_active=True,
                    discovery_enabled=True,
                )
                for identity in identities
            ]
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine) as holder:
            for identity in identities:
                await assert_independent_lock_control(holder, async_engine, identity)
            await lock_peer_pair(holder, *identities)
            pid = await holder.scalar(select(func.pg_backend_pid()))
            async with AsyncSession(async_engine) as writer:
                assert await writer.scalar(select(func.pg_backend_pid())) != pid
                await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(DBAPIError) as blocked:
                    await PeersService(writer).request_connection(
                        identities[1], identities[0], None
                    )
                assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                await writer.rollback()
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id.in_(identities)))
            await cleanup.commit()


async def test_invitation_notifications_see_committed_pair_and_free_parent_locks(
    async_engine, monkeypatch
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    identities = [uuid4(), uuid4()]
    async with AsyncSession(async_engine) as seed:
        seed.add_all(
            [
                User(
                    id=identity,
                    email=f"pair-notice-{identity}@example.com",
                    full_name="Controlled peer",
                    is_active=True,
                    discovery_enabled=True,
                )
                for identity in identities
            ]
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            for identity in identities:
                await assert_independent_lock_control(db, async_engine, identity)
            parent_pid = await db.scalar(select(func.pg_backend_pid()))
            observed = []

            async def notify(events, source_db):
                async with AsyncSession(async_engine) as observer:
                    assert await observer.scalar(select(func.pg_backend_pid())) != parent_pid
                    for identity in identities:
                        assert (
                            await observer.scalar(
                                select(User.id)
                                .where(User.id == identity)
                                .with_for_update(nowait=True)
                            )
                            == identity
                        )
                    assert (
                        await observer.scalar(
                            select(PeerConnection.status).where(
                                PeerConnection.id == events[0].connection_id
                            )
                        )
                        == "pending"
                    )
                    observed.extend(events)

            monkeypatch.setattr(
                "src.domains.agents.application.peer_request.dispatch_peer_events", notify
            )
            draft = await prepare_peer_request(
                db, identities[0], PeerRequestInput(peer_id=identities[1])
            )
            receipt = PreferenceWriteReceipt()
            await execute_peer_request(db, identities[0], draft, receipt)
            assert receipt.committed and len(observed) == 1
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id.in_(identities)))
            await cleanup.commit()
