"""Recurrence store: the forget surface deletes one user's ledger (ADR-260).

The conversation reset no longer touches ``recurrence:{uid}:*``; the explicit
"forget everything" surface must, or the candidates under observation would
come back from data the user asked to forget.
"""

from __future__ import annotations

import fnmatch

import pytest

from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.unit

UID = "08dfb351-5336-42c8-92a9-ee46c6e7f0d0"
OTHER = "dea7604e-84b6-45f9-9f6e-000000000000"


class _FakeRedis:
    def __init__(self, keys: list[str]) -> None:
        self.data = dict.fromkeys(keys, "1")

    def scan_iter(self, match: str) -> object:
        async def _iter() -> object:
            for key in list(self.data):
                if fnmatch.fnmatchcase(key, match):
                    yield key.encode()

        return _iter()

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                removed += 1
        return removed


async def test_delete_user_ledger_removes_only_that_user() -> None:
    redis = _FakeRedis(
        [
            recurrence_store.redis_key(UID, "email"),
            recurrence_store.redis_key(UID, "web_search"),
            recurrence_store.redis_key(OTHER, "event"),
            f"presence:{UID}:2026-09-03:14",
        ]
    )

    deleted = await recurrence_store.delete_user_ledger(redis, UID)

    assert deleted == 2
    assert set(redis.data) == {
        recurrence_store.redis_key(OTHER, "event"),
        f"presence:{UID}:2026-09-03:14",
    }


async def test_delete_user_ledger_on_empty_ledger_is_zero_without_a_delete_call() -> None:
    redis = _FakeRedis([])
    assert await recurrence_store.delete_user_ledger(redis, UID) == 0
