"""A revoked waiter must not retain a FIFO offer ahead of an eligible person."""

from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.domains.users.models import User
from src.domains.world import policy
from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.schemas import WorldState
from src.domains.world.service import WorldConnection, WorldService
from src.domains.world.store import WorldStore
from src.domains.world.tickets import cookie_binding
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


async def test_deactivated_waiter_releases_its_position_before_an_offer(
    async_engine: AsyncEngine,
    redis_world: Redis,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    monkeypatch.setattr(settings, "world_capacity", 1)

    async def sessions() -> Redis:
        return redis_world

    monkeypatch.setattr(policy, "get_redis_session", sessions)
    async with async_sessionmaker(async_engine, expire_on_commit=False)() as db:
        users = [
            User(email=f"queue-{uuid4().hex}@example.invalid", is_active=True) for _ in range(3)
        ]
        db.add_all(users)
        await db.flush()
        committed_user_ids.extend(user.id for user in users)
        await db.commit()
    session_store = SessionStore(redis_world)
    cookie = (await session_store.create_session(str(users[0].id))).session_id
    people = [
        Identity(str(user.id), f"Person {i}", "fr", cookie_binding(cookie))
        for i, user in enumerate(users)
    ]
    authority = Authority(Limits(capacity=1))
    world = WorldStore(redis_world, namespace="test-" + uuid4().hex, ttl=3600)

    def join(state: WorldState, now: float) -> None:
        for person in people:
            authority.join(state, person, "controller-" + person.account_id, now)

    try:
        await world.update(join)
        async with async_sessionmaker(async_engine)() as db:
            waiting = await db.get(User, users[1].id)
            assert waiting is not None
            waiting.is_active = False
            await db.commit()
        service = WorldService(world)
        await service.policy(
            cookie, WorldConnection(people[0], "controller-" + people[0].account_id)
        )
        state, _ = await world.read()
        assert [waiter.account_id for waiter in state.queue] == [people[2].account_id]
    finally:
        await session_store.delete_session(cookie)
