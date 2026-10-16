"""A run clears ITS pending question, and nothing else (N10).

A routine that stops on a question nobody can answer must not leave it on the
person's thread. It must not clear what it did not ask either: routines hold no
conversation lock, so the person's own turn may have saved its question since.
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
    """A store on the real Redis (the engine's decode mode). Skips if down."""
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as exc:  # noqa: BLE001 — no server, no proof to run
        pytest.skip(f"Redis unavailable: {exc}")
    yield HITLStore(redis, ttl_seconds=60)
    await redis.aclose()


def _thread() -> str:
    return f"test-clear-for-run-{uuid.uuid4().hex}"


async def test_the_question_of_the_run_is_cleared(store: HITLStore) -> None:
    thread = _thread()
    await store.save_interrupt(thread, {"action_requests": [], FIELD_RUN_ID: "run-routine"})

    assert await store.clear_interrupt_for_run(thread, "run-routine") is True
    assert await store.get_pending(thread) is None


async def test_another_run_s_question_survives(store: HITLStore) -> None:
    """The person's own turn saved its question after the routine's."""
    thread = _thread()
    await store.save_interrupt(thread, {"action_requests": [], FIELD_RUN_ID: "run-person"})

    assert await store.clear_interrupt_for_run(thread, "run-routine") is False
    pending = await store.get_pending(thread)
    assert pending is not None and pending[FIELD_RUN_ID] == "run-person"
    await store.delete_interrupt(thread)


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
