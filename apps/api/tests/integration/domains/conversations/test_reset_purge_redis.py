"""The conversation reset against a REAL Redis (ADR-260, plan test T3/T4).

The unit tests prove the DECISION (which family is purgeable); this one
proves the EFFECT on a live server, which is where the defect lived: the
historical purge scanned ``*:{user_id}*`` and deleted everything it matched,
so 161 resets in 56 days destroyed the recurrence ledger, the Gmail
consumption anchor, the adaptive thresholds and the briefing's last-known-good
values — weeks of learning, silently, on every "new conversation".

Two oracles, one per surface:

* a reset keeps every LEARNING and RUNTIME key and removes the conversation
  and cache ones;
* account deletion, which must be total, leaves not one user-scoped key —
  while a global key belonging to nobody survives it.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from src.domains.conversations.reset_purge import purge_conversation_keys
from src.infrastructure.cache.key_families import (
    is_user_scoped,
    scan_keys,
    scan_patterns_for,
)
from src.infrastructure.cache.redis import get_redis_cache

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def redis():  # type: ignore[no-untyped-def]
    """A live Redis client, with every key of this test's user removed after."""
    client = await get_redis_cache()
    yield client


def _keys_for(user_id: str) -> dict[str, str]:
    """One key per family the reset used to destroy, plus what it must remove.

    Keys are keyed by the ANSWER expected of them, so a future family added
    to the wrong table fails here with its own name.
    """
    return {
        # --- learning: destroyed by the historical purge, must survive ---
        "recurrence": f"recurrence:{user_id}:email",
        "gmail_anchor": f"gmail_history_anchor:{user_id}",
        "adaptive": f"adaptive:thr:journal_injection:{user_id}",
        "briefing_lastgood": f"briefing:v2:lastgood:{user_id}:mails",
        "presence": f"presence:{user_id}:2026-09-03:08",
        "presence_last": f"presence:last:{user_id}",
        "psyche": f"psyche:state:{user_id}",
        # --- runtime: a live connection is not a conversation ---
        "sse": f"sse:connection:{user_id}",
        "session": f"session:{user_id}:abc",
        # --- conversation + caches: what a reset IS. The prefixes are the
        # REAL ones (core.constants): a made-up key would prove nothing but
        # that an unknown family is kept — which the next test asserts on
        # purpose.
        "hitl_pending": f"hitl_pending:{user_id}",
        "hitl_request_ts": f"hitl:request_ts:{user_id}",
        "contacts_cache": f"contacts_search:{user_id}:jean",
        "gmail_cache": f"gmail:message:{user_id}:m1:full",
        "briefing_cache": f"briefing:v2:{user_id}:cards",
    }


KEPT = (
    "recurrence",
    "gmail_anchor",
    "adaptive",
    "briefing_lastgood",
    "presence",
    "presence_last",
    "psyche",
    "sse",
    "session",
)
REMOVED = (
    "hitl_pending",
    "hitl_request_ts",
    "contacts_cache",
    "gmail_cache",
    "briefing_cache",
)


async def _seed(redis, keys: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    for key in keys.values():
        await redis.set(key, "1", ex=300)


async def _alive(redis, key: str) -> bool:  # type: ignore[no-untyped-def]
    return bool(await redis.exists(key))


class TestConversationReset:
    async def test_a_reset_keeps_the_learning_and_removes_the_conversation(self, redis) -> None:  # type: ignore[no-untyped-def]
        user_id = str(uuid.uuid4())
        keys = _keys_for(user_id)
        await _seed(redis, keys)
        try:
            # In production conversation.id == user.id for the reset path; the
            # patterns carry both ids either way.
            deleted = await purge_conversation_keys(redis, user_id=user_id, conversation_id=user_id)

            for name in KEPT:
                assert await _alive(redis, keys[name]), f"{name} was destroyed by a reset"
            for name in REMOVED:
                assert not await _alive(redis, keys[name]), f"{name} survived a reset"
            # The report is exact, per family.
            assert sum(deleted.values()) == len(REMOVED)
        finally:
            await redis.delete(*keys.values())

    async def test_an_undeclared_family_is_kept_not_guessed(self, redis) -> None:  # type: ignore[no-untyped-def]
        user_id = str(uuid.uuid4())
        unknown = f"brand_new_subsystem:{user_id}:x"
        await redis.set(unknown, "1", ex=300)
        try:
            await purge_conversation_keys(redis, user_id=user_id, conversation_id=user_id)
            assert await _alive(redis, unknown), "an unknown family must never be deleted"
        finally:
            await redis.delete(unknown)


class TestAccountDeletion:
    async def test_account_deletion_leaves_no_user_scoped_key(self, redis) -> None:  # type: ignore[no-untyped-def]
        """The deletion surface removes everything the scan reaches that is
        user-scoped — learning included — and nothing global."""
        user_id = str(uuid.uuid4())
        keys = _keys_for(user_id)
        # A key belonging to nobody: the user patterns cannot even reach it,
        # which is the first line of defence before any scope decision.
        global_key = "bm25:corpus:system"
        await _seed(redis, keys)
        await redis.set(global_key, "1", ex=300)
        try:
            matched = await scan_keys(redis, scan_patterns_for(user_id))
            to_delete = [key for key in matched if is_user_scoped(key)]
            assert to_delete, "the scan must reach this user's keys"
            await redis.delete(*to_delete)

            for name, key in keys.items():
                assert not await _alive(redis, key), f"{name} survived account deletion"
            assert await _alive(redis, global_key), "a global key is not the user's"
        finally:
            await redis.delete(global_key, *keys.values())
