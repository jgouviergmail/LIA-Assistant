"""Real Redis transitions, exclusively on explicit disposable test DB 15."""

import asyncio
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.store import WorldStore
from src.domains.world.tickets import WorldTicket, WorldTickets, cookie_binding

pytestmark = pytest.mark.integration


async def test_independent_workers_never_overadmit_and_share_the_same_epoch(
    redis_world: Redis,
) -> None:
    namespace = uuid4().hex
    stores = [WorldStore(redis_world, namespace=namespace, ttl=1800) for _ in range(12)]
    authority = Authority(Limits())
    identities = [Identity(str(uuid4()), f"Player {n}", "en") for n in range(12)]
    try:
        await asyncio.gather(
            *[
                store.update(
                    lambda state, now, identity=identity: authority.join(
                        state, identity, identity.account_id, now
                    )
                )
                for store, identity in zip(stores, identities, strict=True)
            ]
        )
        state, _ = await stores[0].read()
        assert len(state.actors) == 5 and len(state.queue) == 7
        assert state.revision == 12
        assert len({(await store.read())[0].epoch for store in stores}) == 1
        assert await redis_world.ttl(stores[0].key) > 0
    finally:
        await redis_world.delete(stores[0].key)


async def test_controller_takeover_fences_a_stale_worker_and_release(redis_world: Redis) -> None:
    store = WorldStore(redis_world, namespace=uuid4().hex, ttl=1800)
    authority, identity = Authority(Limits()), Identity(str(uuid4()), "Player", "fr")
    try:
        await store.update(lambda state, now: authority.join(state, identity, "old", now))
        await store.update(
            lambda state, now: authority.takeover(state, identity.account_id, "new", now)
        )
        state, moved = await store.update(
            lambda state, now: authority.move(state, identity.account_id, "old", 1, 1, 0, now)
        )
        assert not moved
        await store.update(lambda state, now: authority.leave(state, identity.account_id, "old"))
        state, _ = await store.read()
        assert state.actors[identity.account_id].controller == "new"
    finally:
        await redis_world.delete(store.key)


async def test_ticket_is_single_use_and_bound_to_the_actual_browser_cookie(
    redis_world: Redis,
) -> None:
    tickets = WorldTickets(redis_world, namespace=uuid4().hex, ttl=30)
    data = WorldTicket(account_id=str(uuid4()), binding=cookie_binding("browser-a"), alias="Player")
    token = await tickets.create(data)
    results = await asyncio.gather(*[tickets.consume(token, "browser-a") for _ in range(12)])
    assert sum(result is not None for result in results) == 1
    token = await tickets.create(data)
    assert await tickets.consume(token, "browser-b") is None
    assert await tickets.consume(token, "browser-a") is None


async def test_missing_or_corrupt_state_is_not_a_silent_local_fallback(redis_world: Redis) -> None:
    store = WorldStore(redis_world, namespace=uuid4().hex, ttl=1800)
    try:
        await redis_world.set(store.key, "corrupt", ex=30)
        with pytest.raises(ValueError):
            await store.read()
        assert await redis_world.get(store.key) == "corrupt"
    finally:
        await redis_world.delete(store.key)


async def test_two_workers_racing_for_one_seat_commit_one_occupant(redis_world: Redis) -> None:
    from src.domains.world.collision import private_home
    from src.domains.world.poses import SLOTS, apply_pose

    namespace = uuid4().hex
    stores = [WorldStore(redis_world, namespace=namespace, ttl=1800) for _ in range(2)]
    authority = Authority(Limits())
    slot = next(s for s in SLOTS.values() if not private_home(s.position))

    def enter(state, now):
        for account in ("a", "b"):
            authority.join(state, Identity(account, account, "en"), account, now)
            state.actors[account].position = slot.approach.copy()

    try:
        await stores[0].update(enter)
        results = await asyncio.gather(
            *[
                store.update(
                    lambda state, now, account=account: apply_pose(
                        state, account, account, 1, slot.id, now
                    )
                )
                for store, account in zip(stores, ("a", "b"), strict=True)
            ]
        )
        assert sum(accepted for _, accepted in results) == 1
        state, _ = await stores[1].read()
        assert sum(actor.pose == slot.id for actor in state.actors.values()) == 1
        assert {actor.pose_result for actor in state.actors.values()} == {"accepted", "occupied"}
    finally:
        await redis_world.delete(stores[0].key)


async def test_geometry_upgrade_cannot_restore_positions_or_seats_from_another_scene(
    redis_world: Redis,
) -> None:
    namespace = uuid4().hex
    previous = WorldStore(redis_world, namespace=namespace, ttl=1800, scene="lia-campus:1")
    authority = Authority(Limits())
    try:
        old_state, _ = await previous.update(
            lambda state, now: authority.join(
                state, Identity("old", "Old scene", "en"), "controller", now
            )
        )
        current = WorldStore(redis_world, namespace=namespace, ttl=1800)
        state, _ = await current.read()
        assert state.epoch != old_state.epoch
        assert not state.actors
        assert (await previous.read())[0].epoch == old_state.epoch
        assert await redis_world.ttl(previous.key) > 0
    finally:
        await redis_world.delete(previous.key)
