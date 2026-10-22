"""Real transactions reserve discretionary funds before any paid work, including competing owners."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.proactive_discussions.finance_models import (
    DiscussionBudgetBucket,
    DiscussionSpendReservation,
)
from src.domains.proactive_discussions.finance_repository import (
    BudgetLimits,
    SpendRepository,
    SpendReservation,
)
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.users.models import User
from tests.integration.domains.proactive_discussions.test_claims import NOW, enable

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def isolated_discretionary_day(async_engine: AsyncEngine):
    async with AsyncSession(async_engine) as db:
        await db.execute(
            delete(DiscussionSpendReservation).where(DiscussionSpendReservation.day == NOW.date())
        )
        await db.execute(
            delete(DiscussionBudgetBucket).where(DiscussionBudgetBucket.day == NOW.date())
        )
        await db.commit()
    yield


async def claim(async_engine, owner):
    await enable(async_engine, owner)
    async with AsyncSession(async_engine) as db:
        result = await DiscussionRepository(db).claim_run(owner, now=NOW, lease_seconds=120)
        await db.commit()
        assert result is not None
        return result


async def test_two_owners_cannot_both_spend_the_last_instance_budget(
    async_engine: AsyncEngine, discussion_owner: UUID, committed_user_ids: list[UUID]
) -> None:
    other = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(User(id=other, email=f"budget-{other}@example.test", is_active=True))
        await db.commit()
    committed_user_ids.append(other)
    first, second = await claim(async_engine, discussion_owner), await claim(async_engine, other)
    limits = BudgetLimits(
        owner_daily=Decimal("1"), instance_daily=Decimal("0.1"), run_max=Decimal("0.1")
    )

    async def reserve(current):
        async with AsyncSession(async_engine) as db:
            accepted = await SpendRepository(db).reserve(
                current,
                estimate=Decimal("0.08"),
                limits=limits,
                now=NOW,
                minimum=Decimal("0.05"),
            )
            await db.commit()
            return accepted

    results = await asyncio.gather(reserve(first), reserve(second))
    # The second is offered what the first left (0.02), less than the 0.05 its first
    # call needs: it starts nothing, and nothing is held for it.
    assert sorted(
        "reserved" if isinstance(result, SpendReservation) else result for result in results
    ) == ["no_room", "reserved"]
    async with AsyncSession(async_engine) as db:
        instance = await db.scalar(
            select(DiscussionBudgetBucket).where(
                DiscussionBudgetBucket.scope_key == "instance",
                DiscussionBudgetBucket.day == NOW.date(),
            )
        )
        assert instance is not None and instance.held_usd == Decimal("0.08")


async def test_a_run_ceiling_below_the_first_call_is_named_not_read_as_no_room(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    current = await claim(async_engine, discussion_owner)
    limits = BudgetLimits(
        owner_daily=Decimal("1"), instance_daily=Decimal("1"), run_max=Decimal("0.01")
    )
    async with AsyncSession(async_engine) as db:
        repository = SpendRepository(db)
        refused = await repository.reserve(
            current, estimate=limits.run_max, limits=limits, now=NOW, minimum=Decimal("0.05")
        )
        availability = await repository.availability(
            discussion_owner, limits=limits, now=NOW, minimum=Decimal("0.05")
        )
        held = await db.scalar(
            select(DiscussionSpendReservation).where(
                DiscussionSpendReservation.run_id == current.run_id
            )
        )
    # The day has every room it needs; the ceiling cannot pay for one call.
    assert refused == "ceiling_too_low" and held is None
    assert availability.run_insufficient and availability.owner_available


async def test_a_reservation_takes_the_room_the_day_has_left_never_more(
    async_engine: AsyncEngine, discussion_owner: UUID, committed_user_ids: list[UUID]
) -> None:
    # Production 2026-10-21: holding the whole run ceiling let one run a day start
    # while most of the day's allowance was never spent.
    other = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(User(id=other, email=f"budget-{other}@example.test", is_active=True))
        await db.commit()
    committed_user_ids.append(other)
    first, second = await claim(async_engine, discussion_owner), await claim(async_engine, other)
    limits = BudgetLimits(
        owner_daily=Decimal("1"), instance_daily=Decimal("0.1"), run_max=Decimal("0.1")
    )

    async def reserve(current):
        async with AsyncSession(async_engine) as db:
            accepted = await SpendRepository(db).reserve(
                current, estimate=Decimal("0.08"), limits=limits, now=NOW
            )
            await db.commit()
            return accepted

    results = await asyncio.gather(reserve(first), reserve(second))
    assert all(isinstance(result, SpendReservation) for result in results)
    assert sorted(result.amount for result in results) == [Decimal("0.02"), Decimal("0.08")]
    async with AsyncSession(async_engine) as db:
        instance = await db.scalar(
            select(DiscussionBudgetBucket).where(
                DiscussionBudgetBucket.scope_key == "instance",
                DiscussionBudgetBucket.day == NOW.date(),
            )
        )
        assert instance is not None and instance.held_usd == Decimal("0.1")


async def test_settlement_is_idempotent_and_unknown_usage_keeps_the_unreconciled_hold(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    current = await claim(async_engine, discussion_owner)
    limits = BudgetLimits(
        owner_daily=Decimal("1"), instance_daily=Decimal("1"), run_max=Decimal("0.1")
    )
    async with AsyncSession(async_engine) as db:
        repository = SpendRepository(db)
        assert isinstance(
            await repository.reserve(current, estimate=Decimal("0.08"), limits=limits, now=NOW),
            SpendReservation,
        )
        assert await repository.issue(current, amount=Decimal("0.05"), now=NOW)
        await db.commit()
        assert await repository.settle(
            current.owner_id, current.run_id, actual=Decimal("0.02"), uncertain=True
        )
        await db.commit()
        assert not await repository.settle(
            current.owner_id, current.run_id, actual=Decimal("0.02"), uncertain=True
        )
        await db.commit()
        row = await db.scalar(
            select(DiscussionBudgetBucket).where(
                DiscussionBudgetBucket.scope_key == "instance",
                DiscussionBudgetBucket.day == NOW.date(),
            )
        )
        # What was issued and not billed yet stays held; the unissued rest is released.
        assert (
            row is not None and row.spent_usd == Decimal("0.02") and row.held_usd == Decimal("0.03")
        )


async def test_crash_recovery_releases_only_unissued_work_and_late_known_usage_still_settles(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    current = await claim(async_engine, discussion_owner)
    limits = BudgetLimits(
        owner_daily=Decimal("1"), instance_daily=Decimal("1"), run_max=Decimal("0.1")
    )
    async with AsyncSession(async_engine) as db:
        repository = SpendRepository(db)
        assert isinstance(
            await repository.reserve(current, estimate=Decimal("0.08"), limits=limits, now=NOW),
            SpendReservation,
        )
        assert await repository.issue(current, amount=Decimal("0.03"), now=NOW)
        await db.commit()
        assert await repository.recover_expired(now=NOW + timedelta(seconds=121), limit=10) == 1
        await db.commit()
        # Measured 2026-10-21: holding the whole estimate, one interrupted run kept the
        # day's room below a first call. Only what it had issued may have been billed.
        recovered = await db.scalar(
            select(DiscussionBudgetBucket).where(
                DiscussionBudgetBucket.scope_key == "instance",
                DiscussionBudgetBucket.day == NOW.date(),
            )
        )
        assert recovered is not None and recovered.held_usd == Decimal("0.03")
        assert await repository.settle(
            current.owner_id, current.run_id, actual=Decimal("0.02"), uncertain=False
        )
        await db.commit()
        instance = await db.scalar(
            select(DiscussionBudgetBucket).where(
                DiscussionBudgetBucket.scope_key == "instance",
                DiscussionBudgetBucket.day == NOW.date(),
            )
        )
        assert (
            instance is not None
            and instance.spent_usd == Decimal("0.02")
            and instance.held_usd == 0
        )
