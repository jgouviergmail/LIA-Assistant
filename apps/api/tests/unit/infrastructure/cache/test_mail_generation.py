"""A mailbox's cache generation: every write makes every cached read of it stale (ADR-369).

Gmail's search (60 s) and message (300 s) caches were never invalidated by a
trash or a label change, so a trashed mail stayed listed for a minute — an
anti-goal of the « Tools » section. A search key is a hash of its query and
cannot be enumerated; a GENERATION prefixed to every key can be bumped once.
The cache is a help, never an authority: an unreadable generation means
« bypass the cache », and a bump that fails never fails the write.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.constants import MAIL_GENERATION_TTL_SECONDS
from src.infrastructure.cache.mail_generation import bump_mail_generation, mail_generation

pytestmark = pytest.mark.unit

ACCOUNT = "4f7c0c1e-0000-4000-8000-000000000001:grant:abc"


class _Redis:
    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.broken = broken

    def _check(self) -> None:
        if self.broken:
            raise ConnectionError("redis down")

    async def get(self, key: str) -> Any:
        self._check()
        return self.store.get(key)

    async def incr(self, key: str) -> int:
        self._check()
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    async def expire(self, key: str, seconds: int) -> bool:
        self._check()
        self.ttls[key] = seconds
        return True


@pytest.fixture
def redis() -> _Redis:
    return _Redis()


async def test_a_mailbox_never_written_is_generation_zero(redis: _Redis) -> None:
    assert await mail_generation(redis, ACCOUNT) == 0


async def test_each_write_moves_the_generation_and_keeps_it_alive(redis: _Redis) -> None:
    await bump_mail_generation(redis, ACCOUNT)
    await bump_mail_generation(redis, ACCOUNT)
    assert await mail_generation(redis, ACCOUNT) == 2
    (key,) = redis.ttls
    assert key.startswith("mail:generation:") and ACCOUNT in key
    assert redis.ttls[key] == MAIL_GENERATION_TTL_SECONDS


async def test_two_mailboxes_have_their_own_generation(redis: _Redis) -> None:
    await bump_mail_generation(redis, ACCOUNT)
    assert await mail_generation(redis, "other-account") == 0


async def test_an_unreadable_generation_says_bypass_the_cache() -> None:
    broken = _Redis(broken=True)
    assert await mail_generation(broken, ACCOUNT) is None
    await bump_mail_generation(broken, ACCOUNT)  # never raises: the write already happened


async def test_a_corrupted_generation_says_bypass_the_cache(redis: _Redis) -> None:
    redis.store[f"mail:generation:{ACCOUNT}"] = "not-a-number"
    assert await mail_generation(redis, ACCOUNT) is None


def test_the_generation_outlives_every_mail_cache() -> None:
    """Its expiry resets it to 0: only safe when no entry of an older 0 can still live."""
    from src.core.config import settings

    assert MAIL_GENERATION_TTL_SECONDS > settings.emails_cache_search_ttl_seconds
    assert MAIL_GENERATION_TTL_SECONDS > settings.emails_cache_details_ttl_seconds
