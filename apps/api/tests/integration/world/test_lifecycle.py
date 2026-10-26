"""A deleted/deactivated account cannot re-enter through a stale world controller."""

import fnmatch
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.users.account_deletion_service import AccountDeletionService
from src.domains.users.models import User
from src.domains.world import lifecycle as world_lifecycle
from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.collision import SCENE
from src.domains.world.schemas import ControlCommand, WorldState
from src.domains.world.service import WorldService
from src.domains.world.store import WorldStore
from src.domains.world.tickets import WorldTicket, WorldTickets, cookie_binding
from src.infrastructure.cache.key_families import is_user_scoped, scan_patterns_for

pytestmark = pytest.mark.integration


async def test_ticket_keys_participate_in_the_native_account_purge(redis_world: Redis) -> None:
    owner = str(uuid4())
    tickets = WorldTickets(redis_world, namespace=uuid4().hex, ttl=30)
    token = await tickets.create(
        WorldTicket(account_id=owner, alias="Visitor", binding=cookie_binding("proof"))
    )
    try:
        key = tickets.key(token)
        assert is_user_scoped(key)
        assert any(fnmatch.fnmatchcase(key, pattern) for pattern in scan_patterns_for(owner))
        assert await tickets.consume(token, "proof") is not None
    finally:
        await redis_world.delete(tickets.key(token))


@pytest.mark.parametrize("scene", [None, "lia-campus:1", SCENE])
async def test_selective_purge_keeps_peers_and_refuses_stale_reentry(
    scene: str | None,
    redis_world: Redis,
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)

    async def cache() -> Redis:
        return redis_world

    async def wrong_session_database() -> Redis:
        raise AssertionError("world runtime belongs to the cache database, never session storage")

    monkeypatch.setattr(world_lifecycle, "get_redis_session", wrong_session_database, raising=False)
    monkeypatch.setattr(world_lifecycle, "get_redis_cache", cache, raising=False)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        accounts = [
            User(email=f"world-{uuid4().hex}@example.invalid", is_active=True) for _ in range(2)
        ]
        db.add_all(accounts)
        await db.flush()
        committed_user_ids.extend(user.id for user in accounts)
        await db.commit()
    namespace = uuid4().hex
    store = WorldStore(redis_world, namespace=namespace, ttl=1800, scene=scene)
    service = WorldService(store)
    try:
        owner, peer = [
            Identity(str(user.id), f"Visitor {index}", "fr") for index, user in enumerate(accounts)
        ]
        connection = await service.enter(owner, None)
        await service.enter(peer, None)
        before, _ = await store.read()
        async with factory() as db:
            row = await db.get(User, accounts[0].id)
            assert row is not None
            row.is_active = False
            await db.commit()
        async with factory() as db:
            # Exercise the native account-deletion port installed by the router,
            # not merely the selective helper in isolation.
            await AccountDeletionService(db)._cleanup_world_presence(accounts[0].id)
        after, _ = await store.read()
        assert after.epoch == before.epoch and set(after.actors) == {peer.account_id}
        with pytest.raises(BaseAPIException):
            await service.command(
                connection, ControlCommand(type="accept", version=1, epoch=after.epoch)
            )
        with pytest.raises(BaseAPIException):
            await service.enter(owner, connection.controller)
        assert set((await store.read())[0].actors) == {peer.account_id}
    finally:
        await redis_world.delete(store.key)


async def test_purge_removes_waiters_without_touching_non_state_keys(redis_world: Redis) -> None:
    namespace = uuid4().hex
    owner, peer = str(uuid4()), str(uuid4())
    store = WorldStore(redis_world, namespace=namespace, ttl=1800)
    authority = Authority(Limits(capacity=1))
    sentinels = [
        f"world:runtime:{namespace}:connect:127.0.0.1",
        f"world:runtime:{namespace}:sockets",
        f"world:runtime:{namespace}:lia-campus:invalid",
        f"world:runtime:{namespace}:",
    ]
    try:
        for key in sentinels:
            await redis_world.set(key, "sentinel", ex=60)
        await store.update(
            lambda state, now: authority.join(
                state, Identity(peer, "Peer", "en"), "peer-controller", now
            )
        )
        before, _ = await store.update(
            lambda state, now: authority.join(
                state, Identity(owner, "Owner", "en"), "owner-controller", now
            )
        )
        assert [waiter.account_id for waiter in before.queue] == [owner]
        await world_lifecycle.purge_world_account(redis_world, owner)
        after, _ = await store.read()
        assert after.epoch == before.epoch
        assert set(after.actors) == {peer}
        assert after.queue == []
        assert await redis_world.mget(sentinels) == ["sentinel"] * len(sentinels)
    finally:
        await redis_world.delete(store.key, *sentinels)


async def test_account_purge_removes_idle_presence_after_capacity_was_released(
    redis_world: Redis,
) -> None:
    store = WorldStore(redis_world, namespace=uuid4().hex, ttl=1800)
    authority = Authority(Limits())
    owner, peer = str(uuid4()), str(uuid4())

    def setup(state: WorldState, now: float) -> None:
        authority.join(state, Identity(owner, "Owner", "en"), "owner-controller", now)
        authority.join(state, Identity(peer, "Peer", "en"), "peer-controller", now)
        state.actors[owner].activity_at = now - 601
        authority.prune(state, now)

    try:
        before, _ = await store.update(setup)
        assert owner not in before.actors and owner in before.presences
        await world_lifecycle.purge_world_account(redis_world, owner)
        after, _ = await store.read()
        assert owner not in after.presences
        assert after.presences[peer] == before.presences[peer]
        assert set(after.actors) == {peer} and after.epoch == before.epoch
    finally:
        await redis_world.delete(store.key)
