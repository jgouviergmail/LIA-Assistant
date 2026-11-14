"""Test doubles of the live domain: a small Redis with claims and a sorted set."""

from __future__ import annotations

import json
from collections import Counter

from src.domains.live import session_scripts


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

    async def lmpop(self, num_keys: int, *keys: str, direction: str, count: int = 1):
        """Pop up to ``count`` items of the first non-empty list, atomically (Redis 7)."""
        self.ops["lmpop"] += 1
        self._check()
        for key in keys[:num_keys]:
            held = self.lists.get(key)
            if not held:
                continue
            taken = held[:count] if direction == "LEFT" else held[-count:][::-1]
            remaining = held[count:] if direction == "LEFT" else held[: len(held) - count]
            if remaining:
                self.lists[key] = remaining
            else:
                del self.lists[key]
            return [key, taken]
        return None

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

    async def eval(self, script: str, numkeys: int, *args: str) -> object:
        """The session commands; real atomicity is tested separately on native Redis."""
        self.ops["eval"] += 1
        self._check()
        keys, values = args[:numkeys], args[numkeys:]
        token = self.store.get(keys[0])
        if script == session_scripts.CLAIM:
            if token is not None:
                return 0
            await self.set(keys[0], values[0], ex=int(values[2]))
            await self.set(keys[1], values[1], ex=int(values[2]))
            await self.delete(*keys[2:])
            return 1
        if script == session_scripts.READ:
            raw = self.store.get(keys[1])
            return raw if raw and json.loads(raw).get("token") == token else None
        if token != values[0]:
            return -1 if script == session_scripts.APPEND else None
        if script == session_scripts.RELEASE:
            await self.delete(*keys)
            return 1
        if script == session_scripts.EXTEND:
            raw = self.store.get(keys[1])
            if not raw or json.loads(raw).get("record_revision", 0) != int(values[3]):
                return 0
            await self.expire(keys[0], int(values[2]))
            await self.set(keys[1], values[1], ex=int(values[2]))
            for key in keys[2:]:
                await self.expire(key, int(values[2]))
            return 1
        if script == session_scripts.APPEND:
            maximum = int(values[2])
            room = len(values) if maximum < 0 else max(0, maximum - await self.llen(keys[1]))
            kept = values[3:][:room]
            if kept:
                await self.rpush(keys[1], *kept)
            await self.expire(keys[1], int(values[1]))
            return len(kept)
        rows = list(self.lists.get(keys[1], []))
        if script == session_scripts.READ_LIST:
            return rows
        if script == session_scripts.DRAIN:
            count = int(values[1])
            self.lists[keys[1]] = rows[count:]
            return rows[:count]
        raise AssertionError("Unmodelled Redis command")

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
