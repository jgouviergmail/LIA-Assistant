"""An in-memory Redis with the semantics the claim seams rely on.

``SET NX EX`` takes a claim only when the key is free, and the release script deletes
the key only for the token that took it — the owner-token rule every claim follows.
Several "workers" of a test share one instance, which is what makes a cross-worker
claim observable without a server. ``broken`` makes every call raise, the outage a
seam must survive by falling back.
"""

from __future__ import annotations

from src.infrastructure.locks.redis_claim import REFRESH_SCRIPT


class InMemoryRedis:
    """The subset of the async Redis client the claim and marker seams call."""

    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.broken = broken
        #: Owner-token renewals that found the caller's token (``held_claim``'s keeper).
        self.refreshes = 0

    def _check(self) -> None:
        if self.broken:
            raise ConnectionError("redis unavailable")

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        self._check()
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def get(self, key: str) -> str | None:
        self._check()
        return self.store.get(key)

    async def delete(self, *keys: str) -> int:
        self._check()
        removed = [key for key in keys if self.store.pop(key, None) is not None]
        return len(removed)

    async def eval(self, script: str, numkeys: int, key: str, token: str, *args: object) -> int:
        """The owner-token scripts: renew, or release, only when the key holds ``token``."""
        self._check()
        if self.store.get(key) != token:
            return 0
        if script == REFRESH_SCRIPT:
            self.refreshes += 1
            return 1
        del self.store[key]
        return 1
