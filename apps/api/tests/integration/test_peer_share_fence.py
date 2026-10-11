"""A GUI share cannot change the selected domain while the native pair is locked."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.models import (
    PeerConnection,
    PeerDomainShare,
    PeerShareDomain,
    PeerShareLevel,
    canonical_pair,
)
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_source_share_respects_independently_locked_pair(async_engine, operation):
    identities = [uuid4(), uuid4()]
    lo, hi = canonical_pair(*identities)
    identity = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add_all(
            [
                User(
                    id=value,
                    email=f"share-fence-{value}@example.com",
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
                requested_by_id=identities[0],
                status="accepted",
                requested_at=datetime.now(UTC),
            )
        )
        await seed.flush()
        if operation != "create":
            seed.add(
                PeerDomainShare(
                    connection_id=identity,
                    owner_user_id=identities[0],
                    domain="calendar",
                    level="availability",
                )
            )
        await seed.commit()
    try:
        async with AsyncSession(async_engine) as holder:
            await assert_independent_lock_control(holder, async_engine, identities[0])
            await holder.scalar(
                select(PeerConnection.id).where(PeerConnection.id == identity).with_for_update()
            )
            pid = await holder.scalar(select(func.pg_backend_pid()))
            async with AsyncSession(async_engine) as writer:
                assert await writer.scalar(select(func.pg_backend_pid())) != pid
                await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(DBAPIError) as blocked:
                    await PeersService(writer).set_share(
                        identities[0],
                        identity,
                        PeerShareDomain.CALENDAR,
                        None if operation == "delete" else PeerShareLevel.DETAILS,
                    )
                assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                await writer.rollback()
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id.in_(identities)))
            await cleanup.commit()
