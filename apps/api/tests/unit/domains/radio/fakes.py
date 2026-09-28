"""Test doubles of the radio: enough of redis.asyncio for the session store, and the register.

Strings, hashes, a sorted set, the claim scripts of ``redis_claim`` and a
non-transactional pipeline — every value kept as the text a
``decode_responses`` client hands back. The integration suite runs the same
store against a real Redis; this double only keeps the unit tests fast.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from redis.exceptions import ResponseError

from src.domains.radio.formats import FORMAT_SPECS, RadioFormat
from src.domains.radio.session import EndReason


class FakeRedis:
    """A dict-backed Redis: what the store calls, with Redis's answers."""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.ttls: dict[str, int] = {}
        self.ops: Counter[str] = Counter()

    def _exists(self, key: str) -> bool:
        return any(key in table for table in (self.strings, self.hashes, self.sets, self.zsets))

    def _sorted_set(self, key: str) -> None:
        """Refuse a sorted-set call on a key holding another type, as Redis does."""
        if any(key in table for table in (self.strings, self.hashes, self.sets)):
            raise ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")

    async def sadd(self, name: str, *members: str) -> int:
        self.ops["sadd"] += 1
        target = self.sets.setdefault(name, set())
        added = len(set(members) - target)
        target.update(members)
        return added

    async def smembers(self, name: str) -> set[str]:
        self.ops["smembers"] += 1
        return set(self.sets.get(name, set()))

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> Any:
        self.ops["set"] += 1
        if nx and key in self.strings:
            return None
        self.strings[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        self.ops["get"] += 1
        return self.strings.get(key)

    async def mget(self, keys: list[str]) -> list[str | None]:
        self.ops["mget"] += 1
        return [self.strings.get(key) for key in keys]

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            for store in (self.strings, self.hashes, self.sets, self.zsets):
                if key in store:
                    del store[key]
                    removed += 1
        return removed

    async def exists(self, *keys: str) -> int:
        self.ops["exists"] += 1
        return sum(1 for key in keys if self._exists(key))

    async def expire(self, key: str, seconds: int) -> bool:
        self.ops["expire"] += 1
        if not self._exists(key):
            return False
        self.ttls[key] = seconds
        return True

    async def hset(
        self,
        name: str,
        key: str | None = None,
        value: str | None = None,
        mapping: dict[str, str] | None = None,
    ) -> int:
        self.ops["hset"] += 1
        target = self.hashes.setdefault(name, {})
        fields = dict(mapping or {})
        if key is not None:
            fields[key] = str(value)
        added = sum(1 for field in fields if field not in target)
        target.update({field: str(item) for field, item in fields.items()})
        return added

    async def hget(self, name: str, key: str) -> str | None:
        self.ops["hget"] += 1
        return self.hashes.get(name, {}).get(key)

    async def hmget(self, name: str, keys: list[str]) -> list[str | None]:
        self.ops["hmget"] += 1
        held = self.hashes.get(name, {})
        return [held.get(key) for key in keys]

    async def hgetall(self, name: str) -> dict[str, str]:
        self.ops["hgetall"] += 1
        return dict(self.hashes.get(name, {}))

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.ops["zadd"] += 1
        self._sorted_set(key)
        target = self.zsets.setdefault(key, {})
        added = sum(1 for member in mapping if member not in target)
        target.update(mapping)
        return added

    async def zrem(self, key: str, *members: str) -> int:
        self.ops["zrem"] += 1
        target = self.zsets.get(key, {})
        removed = [member for member in members if member in target]
        for member in removed:
            del target[member]
        return len(removed)

    async def zremrangebyscore(self, key: str, low: str | float, high: str | float) -> int:
        self.ops["zremrangebyscore"] += 1
        self._sorted_set(key)
        target = self.zsets.get(key, {})
        floor = float("-inf") if low == "-inf" else float(low)
        doomed = [member for member, score in target.items() if floor <= score <= float(high)]
        for member in doomed:
            del target[member]
        return len(doomed)

    async def zrangebyscore(self, key: str, low: str | float, high: str | float) -> list[str]:
        self.ops["zrangebyscore"] += 1
        self._sorted_set(key)
        floor = float("-inf") if low == "-inf" else float(low)
        ceiling = float("inf") if high == "+inf" else float(high)
        ordered = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1])
        return [member for member, score in ordered if floor <= score <= ceiling]

    async def zrange(self, key: str, start: int, stop: int) -> list[str]:
        self.ops["zrange"] += 1
        ordered = sorted(self.zsets.get(key, {}).items(), key=lambda item: item[1])
        members = [member for member, _ in ordered]
        return members[start:] if stop == -1 else members[start : stop + 1]

    async def eval(self, script: str, numkeys: int, *args: Any) -> int:
        """The compare-and-delete and the compare-and-refresh of ``redis_claim``."""
        self.ops["eval"] += 1
        key, token = args[0], args[1]
        if self.strings.get(key) != token:
            return 0
        if "'del'" in script:
            del self.strings[key]
            return 1
        self.ttls[key] = int(args[2])
        return 1

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)


class FakePipeline:
    """Buffers commands like redis.asyncio's pipeline; ``execute`` runs them in order."""

    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def __aenter__(self) -> FakePipeline:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._calls.clear()

    def __getattr__(self, name: str) -> Any:
        def buffered(*args: Any, **kwargs: Any) -> FakePipeline:
            self._calls.append((name, args, kwargs))
            return self

        return buffered

    async def execute(self) -> list[Any]:
        results = [
            await getattr(self._redis, name)(*args, **kwargs) for name, args, kwargs in self._calls
        ]
        self._calls.clear()
        return results


@dataclass(frozen=True, slots=True)
class ClosedBooks:
    """One session's end, as the register was asked to file it."""

    user_id: UUID
    run_id: str
    started_at: datetime
    reason: EndReason


class Books:
    """Stands for the register's filing of a session's end (``register.file_session``)."""

    def __init__(self, *, fails: bool = False) -> None:
        self.closed: list[ClosedBooks] = []
        self.fails = fails

    async def __call__(
        self, *, user_id: UUID, run_id: str, started_at: datetime, reason: EndReason
    ) -> None:
        self.closed.append(ClosedBooks(user_id, run_id, started_at, reason))
        if self.fails:
            raise RuntimeError("the register is down")


def voices_by_format(count: int) -> dict[RadioFormat, int]:
    """Every programme heard with at most ``count`` distinct voices — a cast of ``count``
    voices, each role its own while they last (a programme's roles bound it)."""
    return {fmt: min(count, len(spec.roles)) for fmt, spec in FORMAT_SPECS.items()}
