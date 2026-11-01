"""Doubles shared by the workbench tests (ADR-369)."""

from __future__ import annotations

from typing import Any


class FakeRedis:
    """Strings with TTL, SET NX, and the two compare-and-act scripts."""

    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.broken = broken

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> Any:
        if self.broken:
            raise ConnectionError("redis down")
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def eval(self, script: str, numkeys: int, key: str, token: str, *args: Any) -> int:
        if self.store.get(key) != token:
            return 0
        if "'del'" in script:
            del self.store[key]
            return 1
        payload, ttl = args
        self.store[key] = payload
        self.ttls[key] = int(ttl)
        return 1
