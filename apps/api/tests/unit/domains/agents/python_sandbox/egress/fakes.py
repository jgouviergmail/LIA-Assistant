"""A Redis double for the egress registry: strings with TTL, sets, MGET."""

from __future__ import annotations

from collections import Counter


class FakeRedis:
    """Enough of redis.asyncio for the registry and the ruleset writer."""

    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}
        self.ops: Counter[str] = Counter()
        self.broken = broken

    def _check(self) -> None:
        if self.broken:
            raise ConnectionError("redis down")

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        self.ops["set"] += 1
        self._check()
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key: str):
        self.ops["get"] += 1
        self._check()
        return self.store.get(key)

    async def mget(self, keys: list[str]):
        self.ops["mget"] += 1
        self._check()
        return [self.store.get(k) for k in keys]

    async def delete(self, *keys: str) -> int:
        self.ops["delete"] += 1
        self._check()
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
        return removed

    async def sadd(self, key: str, *members: str) -> int:
        self.ops["sadd"] += 1
        self._check()
        target = self.sets.setdefault(key, set())
        before = len(target)
        target.update(members)
        return len(target) - before

    async def srem(self, key: str, *members: str) -> int:
        self.ops["srem"] += 1
        self._check()
        target = self.sets.get(key, set())
        before = len(target)
        target.difference_update(members)
        return before - len(target)

    async def smembers(self, key: str) -> set[str]:
        self.ops["smembers"] += 1
        self._check()
        return set(self.sets.get(key, set()))

    async def eval(self, script: str, numkeys: int, *args):
        self.ops["eval"] += 1
        self._check()
        key, token = args[0], args[1]
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0

    def expire_now(self, key: str) -> None:
        """Simulate the TTL firing on one entry."""
        self.store.pop(key, None)
