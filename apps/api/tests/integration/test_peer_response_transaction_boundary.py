"""Independent PostgreSQL probes verify response row fencing and post-ACK notification timing."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.peer_response import (
    execute_peer_response,
    prepare_peer_response,
)
from src.domains.agents.application.peer_response_schemas import PeerResponseInput
from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["source_writer", "committed_notice"])
async def test_response_real_transaction_boundary(async_engine, monkeypatch, scenario):
    monkeypatch.setattr(settings, "peers_enabled", True)
    identities = [uuid4(), uuid4()]
    lo, hi = canonical_pair(*identities)
    identity = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add_all(
            [
                User(
                    id=value,
                    email=f"response-fence-{value}@example.com",
                    full_name="Controlled peer",
                    is_active=True,
                )
                for value in identities
            ]
        )
        await seed.flush()
        seed.add(
            PeerConnection(
                id=identity,
                user_a_id=lo,
                user_b_id=hi,
                requested_by_id=identities[1],
                status="pending",
                requested_at=datetime.now(UTC),
            )
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            for value in identities:
                await assert_independent_lock_control(db, async_engine, value)
            pid = await db.scalar(select(func.pg_backend_pid()))
            observed = []

            async def notify(events, source_db):
                async with AsyncSession(async_engine) as observer:
                    assert await observer.scalar(select(func.pg_backend_pid())) != pid
                    for value in identities:
                        assert (
                            await observer.scalar(
                                select(User.id).where(User.id == value).with_for_update(nowait=True)
                            )
                            == value
                        )
                    assert (
                        await observer.scalar(
                            select(PeerConnection.status).where(PeerConnection.id == identity)
                        )
                        == "accepted"
                    )
                    observed.extend(events)

            monkeypatch.setattr(
                "src.domains.agents.application.peer_response.dispatch_peer_events", notify
            )
            source = PeersService.respond_request

            async def probe(service, *args, **kwargs):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as blocked:
                        await source(PeersService(writer), identities[0], identity, False)
                    assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source(service, *args, **kwargs)

            if scenario == "source_writer":
                monkeypatch.setattr(PeersService, "respond_request", probe)
            draft = await prepare_peer_response(
                db, identities[0], PeerResponseInput(connection_id=identity, accept=True)
            )
            receipt = PreferenceWriteReceipt()
            await execute_peer_response(db, identities[0], draft, receipt)
            assert receipt.committed and len(observed) == 1
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id.in_(identities)))
            await cleanup.commit()
