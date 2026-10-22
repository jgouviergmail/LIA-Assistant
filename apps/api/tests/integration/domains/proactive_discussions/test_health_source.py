"""Only available consented measurements become bounded UTC daily signals."""

import json
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.health_metrics.discussion_source import HealthDiscussionSource
from src.domains.health_metrics.models import HealthSample
from src.domains.shared.discussion_sources import SourceKey, SourceReadRequest
from src.domains.users.models import User
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def enable_health(engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(engine) as db:
        user = await db.get(User, owner)
        assert user is not None
        user.health_metrics_agents_enabled = True
        await db.commit()


async def seed_samples(engine: AsyncEngine, owner: UUID) -> None:
    day = NOW.replace(hour=0) - timedelta(days=1)
    async with AsyncSession(engine) as db:
        db.add_all(
            HealthSample(
                user_id=owner,
                kind=kind,
                date_start=day + timedelta(hours=hour),
                date_end=day + timedelta(hours=hour, minutes=1),
                value=value,
            )
            for kind, hour, value in (
                ("heart_rate", 8, 60),
                ("heart_rate", 9, 80),
                ("steps", 10, 0),
                ("steps", 33, 120),
                ("heart_rate", 60, 95),  # Future client date is not current health evidence.
            )
        )
        await db.commit()


def health_request(owner: UUID, *, limit: int = 10, chars: int = 2000) -> SourceReadRequest:
    return read_request(owner, SourceKey.HEALTH, limit=limit, chars=chars).model_copy(
        update={"sensitive_topics": ("health",)}
    )


async def test_health_uses_native_daily_aggregates_without_inventing_missing_values(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    await enable_health(async_engine, discussion_owner)
    await seed_samples(async_engine, discussion_owner)
    result = await HealthDiscussionSource().read(health_request(discussion_owner))
    assert result.status == "ok" and result.coverage_kind == "signal"
    assert result.window_end == NOW and result.total == 3
    frames = [json.loads(item.excerpt) for item in result.items]
    assert next(frame for frame in frames if frame["kind"] == "heart_rate")["metrics"] == {
        "avg": 70.0,
        "min": 60,
        "max": 80,
    }
    assert sorted(frame["metrics"]["sum"] for frame in frames if frame["kind"] == "steps") == [
        0,
        120,
    ]
    assert all(frame["coverage"] == "available_samples_only" for frame in frames)
    assert all(frame["timezone"] == "UTC" for frame in frames)
    assert all(
        item.sensitive_topics == ("health",) and item.occurred_at is None for item in result.items
    )
    assert all(item.interval_start < item.interval_end <= NOW for item in result.items)
    assert all(item.derived and item.assertion == "reported" for item in result.items)


@pytest.mark.parametrize("refusal", ["feature", "owner", "source", "topic"])
async def test_health_refusal_precedes_measurement_access(
    refusal: str, async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock

    monkeypatch.setattr(settings, "health_metrics_enabled", refusal != "feature")
    if refusal != "owner":
        await enable_health(async_engine, discussion_owner)
    aggregate = AsyncMock(side_effect=AssertionError("Refused health measurements were read"))
    monkeypatch.setattr(
        "src.domains.health_metrics.discussion_source.read_chart_statistics", aggregate
    )
    request = health_request(discussion_owner)
    if refusal == "source":
        request = request.model_copy(update={"allowed_sources": ()})
    if refusal == "topic":
        request = request.model_copy(update={"sensitive_topics": ()})
    result = await HealthDiscussionSource().read(request)
    assert result.status == "disabled" and not result.items
    aggregate.assert_not_awaited()


async def test_health_cursor_is_owner_scope_and_content_bound(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    await enable_health(async_engine, discussion_owner)
    await seed_samples(async_engine, discussion_owner)
    source = HealthDiscussionSource()
    request = health_request(discussion_owner, limit=1)
    first = await source.read(request)
    assert first.cursor and first.total == 3 and not first.complete
    continuation = request.model_copy(update={"cursor": first.cursor})
    second = await source.read(continuation)
    assert first.items[0].reference != second.items[0].reference
    assert second.cursor and not second.complete
    last = await source.read(request.model_copy(update={"cursor": second.cursor}))
    assert not last.complete and last.cursor is None
    async with AsyncSession(async_engine) as db:
        sample = await db.scalar(
            select(HealthSample).where(
                HealthSample.user_id == discussion_owner,
                HealthSample.kind == "steps",
                HealthSample.value == 120,
            )
        )
        assert sample is not None
        sample.value = 200
        await db.commit()
    with pytest.raises(ResourceConflictError):
        await source.read(continuation)
    fresh = await source.read(request)
    assert fresh.revision != first.revision


async def test_health_small_budget_never_cuts_a_measurement_into_a_false_fact(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    await enable_health(async_engine, discussion_owner)
    await seed_samples(async_engine, discussion_owner)
    result = await HealthDiscussionSource().read(health_request(discussion_owner, chars=16))
    assert result.status == "unavailable" and result.reason == "budget" and not result.items


async def test_health_unchanged_values_do_not_trigger_reinterpretation_at_each_tick(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    await enable_health(async_engine, discussion_owner)
    await seed_samples(async_engine, discussion_owner)
    source = HealthDiscussionSource()
    request = health_request(discussion_owner)
    before = await source.read(request)
    later = NOW + timedelta(minutes=15)
    after = await source.read(request.model_copy(update={"now": later}))
    assert {item.reference: item.version for item in before.items} == {
        item.reference: item.version for item in after.items
    }
    assert max(item.interval_end for item in after.items) == later
