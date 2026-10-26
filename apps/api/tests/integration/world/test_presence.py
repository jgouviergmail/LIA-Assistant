"""Real Redis fencing for idle reconnection, stale epochs and transport teardown."""

from collections.abc import Callable
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.domains.world import service as service_module
from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.presence import peer_presence
from src.domains.world.schemas import ControlCommand, HeartbeatCommand, WorldState
from src.domains.world.service import WorldConnection, WorldService
from src.domains.world.store import WorldStore

pytestmark = pytest.mark.integration


async def test_idle_resume_preserves_released_capacity_and_fences_old_teardown(
    redis_world: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def admission[R](
        account: str, store: WorldStore, transition: Callable[[WorldState, float], R]
    ) -> tuple[WorldState, R]:
        return await store.update(transition)

    monkeypatch.setattr(service_module, "commit_admission", admission)
    store = WorldStore(redis_world, namespace="test-presence-" + uuid4().hex, ttl=3600)
    identity = Identity(str(uuid4()), "Idle peer", "en", "cookie-digest")
    service = WorldService(store)
    old = await service.enter(identity, None)

    def idle(state: WorldState, now: float) -> None:
        state.actors[identity.account_id].activity_at = now - 601
        Authority(Limits()).prune(state, now)

    await store.update(idle)
    resumed = await service.enter(identity, old.controller)
    state, now = await store.read()
    assert identity.account_id not in state.actors
    assert peer_presence(state, identity.account_id, now) == "away"
    await service.disconnect(old)
    state, now = await store.read()
    assert state.presences[identity.account_id].controller == resumed.controller
    expiry = state.presences[identity.account_id].expires_at
    await service.command(
        resumed, HeartbeatCommand(version=1, type="heartbeat", epoch=str(uuid4()), visible=True)
    )
    state, _ = await store.read()
    assert state.presences[identity.account_id].expires_at == expiry
    await service.command(resumed, ControlCommand(version=1, type="accept", epoch=state.epoch))
    state, now = await store.read()
    assert peer_presence(state, identity.account_id, now) == "online"
    await service.disconnect(WorldConnection(identity, "forged"))
    state, now = await store.read()
    assert peer_presence(state, identity.account_id, now) == "online"
