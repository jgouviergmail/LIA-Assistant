"""Once per submission, against a REAL Redis (ADR-369, ADR-221).

The unit tests prove the decisions on a double; this file proves what a double
cannot: that ``SET NX`` really lets ONE of two concurrent submissions through,
that the TTL is set on the server, and that a holder whose claim was taken over
cannot write its outcome over its successor's (the compare-and-set script).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from src.core.exceptions import BaseAPIException
from src.domains.workbench.idempotency import SETTLE_SCRIPT, run_once, submission_key
from src.infrastructure.cache.redis import get_redis_cache

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Any]:
    client = await get_redis_cache()
    yield client


@pytest_asyncio.fixture
async def user_id(redis: Any) -> AsyncIterator[uuid.UUID]:
    user = uuid.uuid4()
    yield user
    async for key in redis.scan_iter(match=f"workbench:idem:{user}:*"):
        await redis.delete(key)


async def test_two_concurrent_submissions_reach_the_provider_once(
    redis: Any, user_id: uuid.UUID
) -> None:
    key = uuid.uuid4()
    calls = 0
    gate = asyncio.Event()

    async def send() -> dict[str, str]:
        nonlocal calls
        calls += 1
        await gate.wait()
        return {"id": "sent-once"}

    first = asyncio.create_task(run_once(user_id, key, send, tool="mail"))
    second = asyncio.create_task(run_once(user_id, key, send, tool="mail"))
    await asyncio.sleep(0.05)
    gate.set()
    outcomes = await asyncio.gather(first, second, return_exceptions=True)

    assert calls == 1
    refused = [o for o in outcomes if isinstance(o, BaseAPIException)]
    assert len(refused) == 1
    assert refused[0].detail == {"code": "already_submitted", "outcome": "pending"}


async def test_the_server_holds_the_outcome_for_the_configured_time(
    redis: Any, user_id: uuid.UUID
) -> None:
    key = uuid.uuid4()

    async def send() -> dict[str, str]:
        return {"id": "sent-1"}

    await run_once(user_id, key, send, tool="mail", record=lambda sent: {"id": sent["id"]})

    stored = json.loads(await redis.get(submission_key(user_id, key)))
    assert stored == {"state": "done", "id": "sent-1"}
    ttl = await redis.ttl(submission_key(user_id, key))
    assert 0 < ttl <= 86_400


async def test_a_stale_holder_cannot_settle_over_its_successor(
    redis: Any, user_id: uuid.UUID
) -> None:
    redis_key = submission_key(user_id, uuid.uuid4())
    await redis.set(redis_key, "successor-token", ex=60)

    written = await redis.eval(
        SETTLE_SCRIPT, 1, redis_key, "stale-token", json.dumps({"state": "done"}), 60
    )

    assert written == 0
    assert await redis.get(redis_key) == "successor-token"
