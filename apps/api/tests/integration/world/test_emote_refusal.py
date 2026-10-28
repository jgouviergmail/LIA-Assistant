"""A refused gesture settles on real Redis without a native policy read; a publishable one does not."""

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.domains.world import service as world_service
from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.receipt_models import EmoteReceipt
from src.domains.world.service import WorldConnection, WorldService
from src.domains.world.socket_models import EmoteCommand
from src.domains.world.store import WorldStore

pytestmark = pytest.mark.integration


async def test_a_cooling_gesture_is_refused_without_reading_native_policy(
    redis_world: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = WorldStore(redis_world, namespace=f"emote-test-{uuid4().hex}", ttl=60, timeout=3)
    service = WorldService(store)
    identity = Identity(str(uuid4()), "Visitor", "fr")
    connection = WorldConnection(identity, "controller")
    authority = Authority(Limits())

    async def forbidden(*args: object) -> None:
        pytest.fail("a gesture that publishes nothing must not read native policy")

    monkeypatch.setattr(world_service, "read_policy", forbidden)
    try:
        await store.update(lambda state, now: authority.join(state, identity, "controller", now))
        state, _ = await store.read()

        def gesture(seq: int) -> EmoteCommand:
            return EmoteCommand(version=2, type="emote", epoch=state.epoch, seq=seq, emote="wave")

        # Publishable: nothing is settled, nothing is written.
        assert not await service.refuse_emote(connection, gesture(1))
        assert (await store.read())[0].revision == state.revision
        await service.command(connection, gesture(1))
        # Inside the two-second cooldown: settled under its own sequence, unpublished.
        assert await service.refuse_emote(connection, gesture(2))
        actor = (await store.read())[0].actors[identity.account_id]
        assert actor.seq == 2
        assert actor.receipts[-1] == EmoteReceipt(seq=2, result="rate_limited")
        assert actor.emote is not None and actor.emote.serial == 1
        # A gesture from another scene lifetime is never settled here.
        stale = gesture(3).model_copy(update={"epoch": str(uuid4())})
        assert not await service.refuse_emote(connection, stale)
    finally:
        await redis_world.delete(store.key)
