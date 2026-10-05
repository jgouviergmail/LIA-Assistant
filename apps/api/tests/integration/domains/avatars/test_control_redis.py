"""Real Redis races: a revoked single-use ticket can never resurrect a paid session."""

import asyncio
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.avatars.control_store import AvatarControlStore
from src.domains.avatars.leases import AvatarLease, LeasePhase

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("decode", [True, False])
async def test_stop_and_consume_are_atomic_and_secrets_are_encrypted(decode):
    redis = Redis.from_url(str(settings.redis_url), db=15, decode_responses=decode)
    store = AvatarControlStore(redis)
    lease = AvatarLease(
        user_id=uuid4(),
        owner_id=uuid4(),
        digest=uuid4().hex * 2,
        credential_version="v",
        phase=LeasePhase.READY,
        controlled=True,
    )
    ticket = await store.issue(lease, "provider-secret", "personal-key", 60)
    try:
        raw = await redis.hget(store.key(lease.lease_id), "envelope")
        assert "provider-secret" not in str(raw) and "personal-key" not in str(raw)
        closed, envelope = await asyncio.gather(store.stop(lease), store.consume(UUID(ticket)))
        assert (closed and envelope is None) or (not closed and envelope is not None)
        assert await store.stopped(lease.lease_id)
        assert await store.consume(UUID(ticket)) is None
        if envelope:
            assert envelope.lease == lease and envelope.token == "provider-secret"
            await store.closed(lease.lease_id)
        assert await store.stop(lease)
        assert await store.phase(lease.lease_id) == "closed"
        assert 0 < await redis.ttl(store.key(lease.lease_id)) <= 60
    finally:
        await redis.delete(
            store.key(lease.lease_id),
            f"{store.key(lease.lease_id)}:presence",
            f"avatar:ticket:{ticket}",
        )
        await redis.aclose()


async def test_only_one_worker_can_take_a_relay_and_expired_presence_cannot_be_revived():
    redis = Redis.from_url(str(settings.redis_url), db=15, decode_responses=True)
    store = AvatarControlStore(redis)
    lease = AvatarLease(
        user_id=uuid4(),
        owner_id=uuid4(),
        digest=uuid4().hex * 2,
        credential_version="v",
        phase=LeasePhase.READY,
        controlled=True,
    )
    ticket = await store.issue(lease, "token", "key", 60)
    try:
        results = await asyncio.gather(store.consume(UUID(ticket)), store.consume(UUID(ticket)))
        assert sum(result is not None for result in results) == 1
        assert await store.present(lease.lease_id)
        await redis.delete(f"{store.key(lease.lease_id)}:presence")
        await store.touch(lease.lease_id)
        assert not await store.present(lease.lease_id)
    finally:
        await redis.delete(
            store.key(lease.lease_id),
            f"{store.key(lease.lease_id)}:presence",
            f"avatar:ticket:{ticket}",
        )
        await redis.aclose()


async def test_unused_expired_ticket_is_closed_without_allowing_a_late_open():
    redis = Redis.from_url(str(settings.redis_url), db=15, decode_responses=True)
    store = AvatarControlStore(redis)
    lease = AvatarLease(
        user_id=uuid4(),
        owner_id=uuid4(),
        digest=uuid4().hex * 2,
        credential_version="v",
        phase=LeasePhase.READY,
        controlled=True,
    )
    ticket = await store.issue(lease, "token", "key", 60)
    try:
        await redis.delete(f"avatar:ticket:{ticket}")
        assert await store.phase(lease.lease_id) == "closed"
        assert await store.stopped(lease.lease_id)
        assert await store.consume(UUID(ticket)) is None
    finally:
        await redis.delete(store.key(lease.lease_id), f"{store.key(lease.lease_id)}:presence")
        await redis.aclose()


async def test_late_closure_does_not_recreate_expired_control_state():
    redis = Redis.from_url(str(settings.redis_url), db=15, decode_responses=True)
    store = AvatarControlStore(redis)
    lease_id = uuid4()
    try:
        await store.closed(lease_id)
        assert not await redis.exists(store.key(lease_id))
    finally:
        await redis.aclose()
