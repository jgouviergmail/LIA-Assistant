"""A real Redis arbitrates two workers and rejects stale ownership transitions."""

import asyncio
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.avatars.leases import AvatarLease, AvatarLeaseStore, LeasePhase

pytestmark = pytest.mark.integration


async def test_two_workers_share_one_credential_slot_and_stale_release_cannot_remove_successor():
    redis = Redis.from_url(str(settings.redis_url), db=15, decode_responses=True)
    digest = uuid4().hex * 2
    first = AvatarLease(user_id=uuid4(), owner_id=uuid4(), digest=digest, credential_version="one")
    second = AvatarLease(user_id=uuid4(), owner_id=uuid4(), digest=digest, credential_version="two")
    stores = [AvatarLeaseStore(redis), AvatarLeaseStore(redis)]
    try:
        await redis.ping()
        results = await asyncio.gather(stores[0].claim(first, 60), stores[1].claim(second, 60))
        assert sum(results) == 1
        winner = first if results[0] else second
        loser = second if results[0] else first
        store = stores[0]
        ready = await store.mark(winner, LeasePhase.READY)
        assert ready is not None
        assert await store.get(winner.user_id, winner.owner_id) == ready
        assert await store.get(loser.user_id, loser.owner_id) is None
        assert 0 < await redis.ttl(f"avatar:lease:{digest}") <= 60
        assert await store.release(ready)
        assert await store.claim(loser, 60)
        assert not await store.release(ready)
        assert await store.mark(winner, LeasePhase.UNKNOWN) is None
        assert await store.get(loser.user_id, loser.owner_id) == loser
        unknown = await store.mark(loser, LeasePhase.UNKNOWN)
        assert unknown is not None and not await store.release(unknown)
    finally:
        # Test-owned, random keys only; no broad delete against an instance.
        await redis.delete(
            f"avatar:lease:{digest}",
            f"avatar:owner:{first.user_id}:{first.owner_id}",
            f"avatar:owner:{second.user_id}:{second.owner_id}",
        )
        await redis.aclose()
