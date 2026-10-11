"""Independent SQL transactions prove GUI block/unblock cannot bypass native comparison."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.peer_block import execute_peer_block, prepare_peer_block
from src.domains.agents.application.peer_block_schemas import PeerBlockInput
from src.domains.peers.models import PeerBlock, PeerConnection, canonical_pair
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("blocked", [True, False])
async def test_block_real_transaction_fence(async_engine, monkeypatch, blocked):
    monkeypatch.setattr(settings, "peers_enabled", True)
    identities = [uuid4(), uuid4()]
    lo, hi = canonical_pair(*identities)
    identity = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add_all(
            [
                User(
                    id=value,
                    email=f"block-fence-{value}@example.com",
                    full_name="Controlled",
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
                status="accepted" if blocked else "removed",
                requested_at=datetime.now(UTC),
            )
        )
        if not blocked:
            seed.add(PeerBlock(blocker_id=identities[0], blocked_id=identities[1]))
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            for value in identities:
                await assert_independent_lock_control(db, async_engine, value)
            pid = await db.scalar(select(func.pg_backend_pid()))
            source = PeersService.block_peer if blocked else PeersService.unblock_peer

            async def probe(service, *args):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as waiting:
                        await source(PeersService(writer), *identities)
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source(service, *args)

            monkeypatch.setattr(PeersService, "block_peer" if blocked else "unblock_peer", probe)
            draft = await prepare_peer_block(
                db, identities[0], PeerBlockInput(peer_id=identities[1], blocked=blocked)
            )
            receipt = PreferenceWriteReceipt()
            await execute_peer_block(db, identities[0], draft, receipt)
            assert receipt.committed
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id.in_(identities)))
            await cleanup.commit()
