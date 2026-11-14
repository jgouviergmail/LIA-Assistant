"""A run clears ITS pending question, and nothing else (N10).

A routine that stops on a question nobody can answer must not leave it on the
person's thread. It must not clear what it did not ask either: another invocation
may have saved its question since. This file covers legacy records; the current
invocation protocol is exercised by test_hitl_runtime_authority.
The comparison and the deletion are one server-side step, so this is proven on
a real Redis — a mocked client would only echo the call it was given.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import REDIS_KEY_HITL_PENDING_PREFIX
from src.core.field_names import FIELD_RUN_ID
from src.domains.agents.utils.hitl_store import HITLStore

pytestmark = pytest.mark.integration


@pytest.fixture
async def store() -> AsyncGenerator[HITLStore]:
    """A store on required disposable Redis; an unavailable boundary fails the suite."""
    async with Redis.from_url(str(settings.redis_url), decode_responses=True) as redis:
        await redis.ping()
        yield HITLStore(redis, ttl_seconds=60)


async def seed_legacy(store: HITLStore, thread: str, run_id: str) -> None:
    """Seed the pre-migration envelope, not a current production write."""
    await store.redis.set(
        f"{REDIS_KEY_HITL_PENDING_PREFIX}{thread}",
        json.dumps(
            {"schema_version": 1, "interrupt_data": {"action_requests": [], FIELD_RUN_ID: run_id}}
        ),
        ex=60,
    )


def _thread() -> str:
    return f"test-clear-for-run-{uuid.uuid4().hex}"


async def test_the_question_of_the_run_is_cleared(store: HITLStore) -> None:
    thread = _thread()
    await seed_legacy(store, thread, "run-routine")

    assert await store.clear_interrupt_for_run(thread, "run-routine") is True
    assert await store.get_pending(thread) is None


async def test_another_run_s_question_survives(store: HITLStore) -> None:
    """The person's own turn saved its question after the routine's."""
    thread = _thread()
    await seed_legacy(store, thread, "run-person")

    assert await store.clear_interrupt_for_run(thread, "run-routine") is False
    pending = await store.get_pending(thread)
    assert pending is not None and pending[FIELD_RUN_ID] == "run-person"
    await store.redis.delete(f"{REDIS_KEY_HITL_PENDING_PREFIX}{thread}")


async def test_nothing_pending_clears_nothing(store: HITLStore) -> None:
    assert await store.clear_interrupt_for_run(_thread(), "run-routine") is False


@pytest.mark.parametrize(
    "stored",
    [
        "not json at all",
        json.dumps(["a", "list"]),
        # The legacy, unversioned shape carries its run id at the top level:
        # nothing has written it for months, and doubt never deletes.
        json.dumps({FIELD_RUN_ID: "run-routine", "action_requests": []}),
    ],
)
async def test_a_record_it_cannot_read_is_kept(store: HITLStore, stored: str) -> None:
    thread = _thread()
    key = f"{REDIS_KEY_HITL_PENDING_PREFIX}{thread}"
    await store.redis.set(key, stored, ex=60)

    assert await store.clear_interrupt_for_run(thread, "run-routine") is False
    assert await store.redis.exists(key) == 1
    await store.redis.delete(key)
