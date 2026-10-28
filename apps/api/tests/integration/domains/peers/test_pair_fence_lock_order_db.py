"""The canonical pair fence never deadlocks a share write that already holds the pair row.

``block_peer`` fences both accounts, then rewrites the pair row. ``set_share``
locks the pair row, then inserts a share whose foreign key reads the owner's
account row (``FOR KEY SHARE``). A ``FOR UPDATE`` fence conflicts with that read,
so the two writers waited on each other and PostgreSQL aborted one of them with
40P01. The fence is ``FOR NO KEY UPDATE``: it still orders every fence taker and
every UPDATE/DELETE of the accounts, never a reference to them. Only a real
server can show it — the lock compatibility matrix is PostgreSQL's.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.domains.peers.models import (
    PeerBlock,
    PeerConnection,
    PeerConnectionStatus,
    PeerDomainShare,
    PeerShareDomain,
    PeerShareLevel,
    canonical_pair,
)
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.repository import PeersRepository
from src.domains.peers.service import PeersService
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


async def _accepted_pair(engine: AsyncEngine, identities: list[UUID]) -> tuple[UUID, UUID, UUID]:
    """Commit two accounts and their accepted connection, visible to every connection."""
    first = await commit_owner(engine, identities, full_name="Fictional sharer")
    second = await commit_owner(engine, identities, full_name="Fictional blocker")
    user_a, user_b = canonical_pair(first, second)
    now = datetime.now(UTC)
    async with AsyncSession(engine) as db:
        connection = PeerConnection(
            user_a_id=user_a,
            user_b_id=user_b,
            requested_by_id=first,
            status=PeerConnectionStatus.ACCEPTED.value,
            requested_at=now,
            responded_at=now,
        )
        db.add(connection)
        await db.flush()
        connection_id = connection.id
        await db.commit()
    return first, second, connection_id


async def _await_lock_wait(engine: AsyncEngine, pid: int) -> None:
    """Return once the backend ``pid`` is actually waiting for a row lock."""
    async with async_sessionmaker(engine)() as monitor:
        for _ in range(250):
            waiting = await monitor.scalar(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pid},
            )
            if waiting == "Lock":
                return
            await asyncio.sleep(0.02)
    pytest.fail("the block never waited for the pair row the share write holds")


async def test_a_block_waiting_on_a_share_writer_completes_instead_of_deadlocking(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    sharer_id, blocker_id, connection_id = await _accepted_pair(async_engine, committed_user_ids)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as sharer, factory() as blocker:
        # The share write's first statement, exactly as PeersService.set_share runs it.
        repository = PeersRepository(sharer)
        assert await repository.get_by_id(connection_id, for_update=True) is not None
        pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(pid, int)
        block = asyncio.create_task(PeersService(blocker).block_peer(blocker_id, sharer_id))
        try:
            await _await_lock_wait(async_engine, pid)
            # The insert's foreign key reads the account row the block has fenced.
            await repository.upsert_share(
                connection_id,
                sharer_id,
                PeerShareDomain.CALENDAR.value,
                PeerShareLevel.DETAILS.value,
            )
            await sharer.commit()
            await asyncio.wait_for(block, timeout=10)
            await blocker.commit()
        except DBAPIError as error:
            pytest.fail(f"pair writers aborted: {getattr(error.orig, 'sqlstate', None)}")
        finally:
            if not block.done():
                block.cancel()
            await asyncio.gather(block, return_exceptions=True)
    async with factory() as reader:
        connection = await reader.get(PeerConnection, connection_id)
        assert connection is not None
        assert connection.status == PeerConnectionStatus.REMOVED.value
        blocks = await reader.scalars(
            select(PeerBlock).where(
                PeerBlock.blocker_id == blocker_id, PeerBlock.blocked_id == sharer_id
            )
        )
        assert len(blocks.all()) == 1
        # The block ran after the share committed, so it severed that share too.
        shares = await reader.scalars(
            select(PeerDomainShare).where(PeerDomainShare.connection_id == connection_id)
        )
        assert shares.all() == []


async def test_the_fence_still_serializes_fence_takers_and_account_updates(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    sharer_id, blocker_id, _ = await _accepted_pair(async_engine, committed_user_ids)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    for contender in ("fence", "update"):
        async with factory() as holder, factory() as other:
            await lock_peer_pair(holder, sharer_id, blocker_id)
            await other.execute(text("SET LOCAL lock_timeout = '150ms'"))
            with pytest.raises(DBAPIError) as waited:
                if contender == "fence":
                    await lock_peer_pair(other, blocker_id, sharer_id)
                else:
                    await other.execute(
                        text("UPDATE users SET full_name = full_name WHERE id = :id"),
                        {"id": sharer_id},
                    )
            assert getattr(waited.value.orig, "sqlstate", None) == "55P03", contender
            await other.rollback()
            await holder.rollback()
