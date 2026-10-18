"""Real Redis claims and TTLs, with deterministic native responses and zero paid calls."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from src.core.constants import JEV_CLASSIFICATION_UNKNOWN_TTL_SECONDS
from src.domains.agents.services.qualification import service
from src.domains.agents.services.qualification.cache import (
    ClassificationCache,
    classification_cache_key,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.llm.decision_types import DecisionAttempt
from tests.unit.domains.agents.services.test_classification_batches import observed
from tests.unit.domains.agents.services.test_classification_service import (
    ready,
    successful,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def cache_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[Redis, UUID]]:
    redis = await get_redis_cache()
    await redis.ping()
    owner = uuid4()
    monkeypatch.setattr(service, "load_jev_snapshot", AsyncMock(return_value=ready()))
    monkeypatch.setattr(service, "record_action", AsyncMock())
    monkeypatch.setattr(
        service,
        "open_classification_cache",
        AsyncMock(side_effect=lambda: ClassificationCache(redis)),
    )
    yield redis, owner
    for prefix in (
        f"content:classification:{owner}:*",
        f"shared_flight:content_classification:{owner}:*",
    ):
        keys = [key async for key in redis.scan_iter(match=prefix)]
        if keys:
            await redis.delete(*keys)


async def test_overlapping_workers_recheck_the_cache_under_the_source_claim(
    cache_owner: tuple[Redis, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, owner = cache_owner
    started, release = asyncio.Event(), asyncio.Event()
    counts: list[int] = []

    async def native(**kwargs: object) -> DecisionAttempt:
        questions = kwargs["questions"]
        assert isinstance(questions, dict)
        counts.append(len(questions))
        if len(counts) == 1:
            started.set()
            await release.wait()
        return await successful(**kwargs)

    monkeypatch.setattr(service, "choose_many_with_jev", native)

    async def run(indices: list[int]):
        return await service.qualify_observations(
            user_id=owner,
            provider="google_gmail",
            source_scope="grant-1",
            observations=[observed(i) for i in indices],
            run_id=str(uuid4()),
            timezone="UTC",
        )

    first = asyncio.create_task(run([0, 1]))
    await started.wait()
    second = asyncio.create_task(run([1, 2]))
    await asyncio.sleep(0.05)
    release.set()
    left, right = await asyncio.gather(first, second)
    assert set(left) == {"private-0", "private-1"}
    assert set(right) == {"private-1", "private-2"}
    assert counts == [4, 2]  # Three observations, two independent email questions each.
    await run([0, 1, 2])
    assert counts == [4, 2]
    assert not [
        key
        async for key in redis.scan_iter(match=f"shared_flight:content_classification:{owner}:*")
    ]
    retained = [
        await redis.get(key)
        async for key in redis.scan_iter(match=f"content:classification:{owner}:*")
    ]
    assert all(
        "Please review" not in str(value) and "grant-1" not in str(value) for value in retained
    )


async def test_negative_cache_is_short_and_a_changed_grant_never_reuses_it(
    cache_owner: tuple[Redis, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, owner = cache_owner

    async def uncertain(**kwargs: object) -> DecisionAttempt:
        result = await successful(**kwargs)
        return DecisionAttempt(
            outcome="success",
            answers={
                key: answer.model_copy(update={"confidence": 0.1})
                for key, answer in result.answers.items()
            },
        )

    native = AsyncMock(side_effect=uncertain)
    monkeypatch.setattr(service, "choose_many_with_jev", native)

    async def run(binding: str):
        return await service.qualify_observations(
            user_id=owner,
            provider="google_gmail",
            source_scope=binding,
            observations=[observed(1)],
            run_id=str(uuid4()),
            timezone="UTC",
        )

    result = await run("first-grant")
    assert result["private-1"].category == "unknown"
    await run("first-grant")
    assert native.await_count == 1
    keys = [key async for key in redis.scan_iter(match=f"content:classification:{owner}:*")]
    assert len(keys) == 1
    assert 0 < await redis.ttl(keys[0]) <= JEV_CLASSIFICATION_UNKNOWN_TTL_SECONDS
    await run("second-grant")
    assert native.await_count == 2


async def test_cancelled_holder_releases_its_claim_before_a_waiter_continues(
    cache_owner: tuple[Redis, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, owner = cache_owner
    started = asyncio.Event()

    async def held(**kwargs: object) -> DecisionAttempt:
        started.set()
        await asyncio.Event().wait()
        return DecisionAttempt()

    monkeypatch.setattr(service, "choose_many_with_jev", held)

    async def run():
        return await service.qualify_observations(
            user_id=owner,
            provider="google_gmail",
            source_scope="grant-1",
            observations=[observed(1)],
            run_id=str(uuid4()),
            timezone="UTC",
        )

    task = asyncio.create_task(run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    monkeypatch.setattr(service, "choose_many_with_jev", successful)
    result = await run()
    assert result["private-1"].category == "professional"


async def test_corrupt_or_expired_cache_never_becomes_an_accepted_label(
    cache_owner: tuple[Redis, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, owner = cache_owner
    now = datetime.now(UTC)
    key = classification_cache_key(
        observed(1),
        user_id=owner,
        provider="google_gmail",
        source_scope="grant-1",
        model="jev-pinned",
        policy=service.policy_fingerprint(),
        now=now,
        timezone="UTC",
    )
    await redis.set(key, '{"kind":"email","category":"administrator"}', ex=60)
    native = AsyncMock(side_effect=successful)
    monkeypatch.setattr(service, "choose_many_with_jev", native)
    result = await service.qualify_observations(
        user_id=owner,
        provider="google_gmail",
        source_scope="grant-1",
        observations=[observed(1)],
        run_id="test-run",
        timezone="UTC",
        now=now,
    )
    assert result["private-1"].category == "professional"
    assert native.await_count == 1
