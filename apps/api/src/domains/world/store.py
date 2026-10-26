"""Redis is the one serial authority, with bounded optimistic transactions.

There is no process-local fallback or background worker simulator to elect.
Every committed movement has the actor controller fence and epoch of this state.
Cancellation after EXEC may lose an acknowledgment, never the sequence fence.
"""

import asyncio
import hashlib
from collections.abc import Callable

from redis.asyncio import Redis
from redis.exceptions import WatchError

from src.core.constants import (
    REDIS_KEY_WORLD_RUNTIME_PREFIX,
    WORLD_AUTHORITY_TIMEOUT_DEFAULT,
)
from src.domains.world.collision import SCENE
from src.domains.world.schemas import WorldState

MAX_STATE_BYTES = 128 * 1024
MAX_CAS_ATTEMPTS = 16


class WorldUnavailable(RuntimeError):
    """The shared authority cannot establish an outcome; re-read, never simulate locally."""


class WorldStore:
    def __init__(
        self,
        redis: Redis,
        *,
        namespace: str,
        ttl: int,
        timeout: float = WORLD_AUTHORITY_TIMEOUT_DEFAULT,
        scene: str | None = SCENE,
    ) -> None:
        """Bind Redis authority and message fencing to the full instance/scene identity."""
        self.redis = redis
        # Only lifecycle cleanup selects an older scene; admission uses SCENE.
        suffix = f":{scene}" if scene is not None else ""
        self.key = f"{REDIS_KEY_WORLD_RUNTIME_PREFIX}{namespace}{suffix}"
        # Preserve the full instance AND scene identity in Redis content and
        # SQL spend fences; a trailing scene version alone is not a namespace.
        # The durable namespace column admits forty characters.
        self.message_namespace = hashlib.sha256(self.key.encode("utf-8")).hexdigest()[:40]
        self.ttl = ttl
        self.timeout = timeout

    @staticmethod
    def decode(raw: str | bytes | None) -> WorldState:
        """Decode strict bounded state; only a missing key creates a new epoch."""
        if raw is None:
            return WorldState()
        if len(raw) > MAX_STATE_BYTES:
            raise WorldUnavailable("world_state_limit")
        return WorldState.model_validate_json(raw)

    async def read(self) -> tuple[WorldState, float]:
        """Read authoritative state and Redis wall-clock time under the configured I/O deadline."""
        async with asyncio.timeout(self.timeout):
            seconds, micros = await self.redis.time()
            return (
                self.decode(await self.redis.get(self.key)),
                float(seconds) + float(micros) / 1e6,
            )

    async def update[R](self, transition: Callable[[WorldState, float], R]) -> tuple[WorldState, R]:
        """Commit a pure transition under a bounded optimistic transaction.

        Args:
            transition: In-place snapshot mutation receiving Redis Unix seconds.
                It may run again after contention, so it must have no external effects.

        Returns:
            Committed state and the result of its accepted transition invocation.

        Raises:
            WorldUnavailable: State size, corruption or contention prevents a commit.
            TimeoutError: The overall authority deadline expires. Re-read before retrying
                a business operation: cancellation can lose an already committed ack.
        """
        async with asyncio.timeout(self.timeout):
            return await self._update(transition)

    async def _update[R](
        self, transition: Callable[[WorldState, float], R]
    ) -> tuple[WorldState, R]:
        """Watch authority, run the transition and atomically publish its incremented revision and TTL."""
        for _ in range(MAX_CAS_ATTEMPTS):
            try:
                async with self.redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(self.key)
                    state = self.decode(await pipe.get(self.key))
                    seconds, micros = await self.redis.time()
                    result = transition(state, float(seconds) + float(micros) / 1e6)
                    state.revision += 1
                    serialized = state.model_dump_json()
                    if len(serialized.encode("utf-8")) > MAX_STATE_BYTES:
                        raise WorldUnavailable("world_state_limit")
                    pipe.multi()
                    pipe.set(self.key, serialized, ex=self.ttl)
                    await pipe.execute()
                    return state, result
            except WatchError:
                continue
        raise WorldUnavailable("world_contention")
