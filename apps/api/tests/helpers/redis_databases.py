"""One Redis server and its separate databases, in memory, for tests.

Redis databases are separate keyspaces: a key written through a client bound to
one database index does not exist for a client bound to another. The test
conftest points every client at ONE index, which hid a door reading the wrong
database — the Telegram doors read the pending question from the session
database while the engine writes it in the cache database, so every button press
read « expired » (review 12). This fake keeps one keyspace per index and answers
the few commands the channel doors, the turn claim and the HITL store send.
"""

from __future__ import annotations

from src.infrastructure.locks.redis_claim import REFRESH_SCRIPT, RELEASE_SCRIPT


class DatabaseClient:
    """A client bound to ONE database of a :class:`RedisServer`."""

    def __init__(self, keyspace: dict[str, str]) -> None:
        self._keys = keyspace

    async def get(self, key: str) -> str | None:
        return self._keys.get(key)

    async def set(
        self, key: str, value: str | int | float, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        if nx and key in self._keys:
            return False
        self._keys[key] = str(value)
        return True

    async def exists(self, *keys: str) -> int:
        return sum(1 for key in keys if key in self._keys)

    async def delete(self, *keys: str) -> int:
        return sum(1 for key in keys if self._keys.pop(key, None) is not None)

    async def eval(self, script: str, numkeys: int, *args: str | int) -> int:
        """The turn claim's two owner-conditioned scripts: refresh and release."""
        key, token = str(args[0]), str(args[1])
        if self._keys.get(key) != token:
            return 0
        if script == RELEASE_SCRIPT:
            del self._keys[key]
            return 1
        if script == REFRESH_SCRIPT:
            return 1
        raise NotImplementedError(f"script not modelled: {script[:40]!r}")


class RedisServer:
    """One Redis server: one keyspace per database index."""

    def __init__(self) -> None:
        self._databases: dict[int, dict[str, str]] = {}

    def client(self, db: int) -> DatabaseClient:
        """A client bound to database ``db``."""
        return DatabaseClient(self._databases.setdefault(db, {}))
