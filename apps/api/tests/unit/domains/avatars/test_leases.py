"""Lease ownership/phase contracts; Redis commands are external boundaries."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.domains.avatars.leases import AvatarLease, AvatarLeaseStore, LeasePhase

pytestmark = pytest.mark.unit


def lease() -> AvatarLease:
    return AvatarLease(user_id=uuid4(), owner_id=uuid4(), digest="f" * 64, credential_version="v1")


def cache():
    redis = AsyncMock(spec=Redis)
    redis.set = AsyncMock()
    redis.eval = AsyncMock()
    redis.get = AsyncMock()
    return redis


async def test_claim_is_credential_scoped_and_expiring():
    redis = cache()
    redis.set.return_value = True
    record = lease()
    assert await AvatarLeaseStore(redis).claim(record, 100) is True
    assert redis.set.call_args_list[0].kwargs == {"nx": True, "ex": 100}
    assert str(record.user_id) not in redis.set.call_args_list[0].args[0]
    assert record.digest in redis.set.call_args_list[0].args[0]


async def test_conflict_never_overwrites_the_current_owner():
    redis = cache()
    redis.set.return_value = False
    assert await AvatarLeaseStore(redis).claim(lease(), 100) is False
    assert redis.set.await_count == 1


async def test_phase_transition_lost_to_expiry_cannot_publish_ready():
    redis = cache()
    redis.eval.return_value = 0
    assert await AvatarLeaseStore(redis).mark(lease(), LeasePhase.READY) is None


async def test_unknown_or_inflight_mint_cannot_be_released_as_closed():
    redis = cache()
    store = AvatarLeaseStore(redis)
    assert await store.release(lease()) is False
    unknown = lease().model_copy(update={"phase": LeasePhase.UNKNOWN})
    assert await store.release(unknown) is False
    redis.eval.assert_not_awaited()


async def test_ready_release_compares_the_entire_owner_epoch():
    redis = cache()
    redis.eval.return_value = 1
    record = lease().model_copy(update={"phase": LeasePhase.READY})
    assert await AvatarLeaseStore(redis).release(record) is True
    assert record.model_dump_json() in redis.eval.call_args_list[0].args
