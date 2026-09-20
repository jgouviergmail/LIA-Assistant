"""Test doubles of the live domain: a small Redis with claims and a sorted set."""

from __future__ import annotations

from collections import Counter


class FakeRedis:
    """Enough of redis.asyncio for the session store: strings, a claim script, a zset."""

    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
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

    async def delete(self, *keys: str) -> int:
        self.ops["delete"] += 1
        self._check()
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
            if key in self.lists:
                del self.lists[key]
                removed += 1
        return removed

    async def rpush(self, key: str, *values: str) -> int:
        self.ops["rpush"] += 1
        self._check()
        held = self.lists.setdefault(key, [])
        held.extend(values)
        return len(held)

    async def llen(self, key: str) -> int:
        self.ops["llen"] += 1
        self._check()
        return len(self.lists.get(key, []))

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        self.ops["lrange"] += 1
        self._check()
        held = self.lists.get(key, [])
        return held[start:] if stop == -1 else held[start : stop + 1]

    async def incr(self, key: str) -> int:
        self.ops["incr"] += 1
        self._check()
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> bool:
        self.ops["expire"] += 1
        self._check()
        if key not in self.store and key not in self.lists:
            return False
        self.ttls[key] = seconds
        return True

    async def eval(self, script: str, numkeys: int, *args):
        """The compare-and-delete and the compare-and-refresh of ``redis_claim``."""
        self.ops["eval"] += 1
        self._check()
        key, token = args[0], args[1]
        if self.store.get(key) != token:
            return 0
        if "'del'" in script:
            del self.store[key]
            return 1
        # compare-and-refresh: the owner's claim gets the new TTL
        self.ttls[key] = int(args[2])
        return 1

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.ops["zadd"] += 1
        self._check()
        target = self.zsets.setdefault(key, {})
        added = sum(1 for member in mapping if member not in target)
        target.update(mapping)
        return added

    async def zrem(self, key: str, *members: str) -> int:
        self.ops["zrem"] += 1
        self._check()
        target = self.zsets.get(key, {})
        removed = 0
        for member in members:
            if member in target:
                del target[member]
                removed += 1
        return removed

    async def zremrangebyscore(self, key: str, low: str | float, high: str | float) -> int:
        self.ops["zremrangebyscore"] += 1
        self._check()
        target = self.zsets.get(key, {})
        lo = float("-inf") if low == "-inf" else float(low)
        hi = float("inf") if high == "+inf" else float(high)
        doomed = [m for m, score in target.items() if lo <= score <= hi]
        for member in doomed:
            del target[member]
        return len(doomed)

    async def zcard(self, key: str) -> int:
        self.ops["zcard"] += 1
        self._check()
        return len(self.zsets.get(key, {}))
