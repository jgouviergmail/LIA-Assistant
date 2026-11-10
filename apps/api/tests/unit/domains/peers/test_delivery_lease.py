"""A delivery owner waits for its renewal session even under repeated cancellation."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from src.domains.peers.delivery_repository import DeliveryClaim
from src.infrastructure.scheduler import peer_delivery_lease as lease

pytestmark = pytest.mark.unit


async def test_second_cancellation_cannot_abandon_renewal_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renewing, cleaning, release, closed = (asyncio.Event() for _ in range(4))

    class Database:
        pass

    @asynccontextmanager
    async def session() -> AsyncIterator[Database]:
        try:
            yield Database()
        finally:
            cleaning.set()
            await release.wait()
            closed.set()

    class Repository:
        def __init__(self, db: Database) -> None:
            pass

        async def renew(self, claim: DeliveryClaim) -> bool:
            renewing.set()
            await asyncio.Event().wait()
            return True

    monkeypatch.setattr(lease, "get_db_context", session)
    monkeypatch.setattr(lease, "PeerDeliveryRepository", Repository)
    monkeypatch.setattr(lease.settings, "peers_delivery_lease_seconds", 0.003)

    async def owner() -> None:
        async with lease.delivery_lease(DeliveryClaim(uuid4(), uuid4(), 1)):
            await asyncio.Event().wait()

    task = asyncio.create_task(owner())
    try:
        await asyncio.wait_for(renewing.wait(), 2)
        task.cancel()
        await asyncio.wait_for(cleaning.wait(), 2)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done(), "The owner returned before its session closed"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert closed.is_set()
