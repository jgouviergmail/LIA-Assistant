"""Independent PostgreSQL connections prove lease ownership and fencing."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


async def enable(engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(engine) as db:
        await DiscussionRepository(db).update_policy(
            owner, DiscussionPolicyPatch(enabled=True), expected_revision=0
        )
        await db.commit()


async def test_disabled_account_cannot_claim(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async with AsyncSession(async_engine) as db:
        assert (
            await DiscussionRepository(db).claim_run(discussion_owner, now=NOW, lease_seconds=60)
            is None
        )


async def test_two_workers_only_one_claims(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    await enable(async_engine, discussion_owner)

    async def claim():
        async with AsyncSession(async_engine) as db:
            result = await DiscussionRepository(db).claim_run(
                discussion_owner, now=NOW, lease_seconds=60
            )
            await db.commit()
            return result

    results = await asyncio.gather(claim(), claim())
    assert sum(item is not None for item in results) == 1


async def test_expiry_takeover_blocks_old_renew_and_settle(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    await enable(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        repository = DiscussionRepository(db)
        old = await repository.claim_run(discussion_owner, now=NOW, lease_seconds=60)
        assert old is not None
        await db.commit()
        later = NOW + timedelta(seconds=60)
        new = await repository.claim_run(discussion_owner, now=later, lease_seconds=60)
        assert new is not None and new.fence > old.fence and new.run_id != old.run_id
        await db.commit()
        assert not await repository.renew_claim(old, now=later, lease_seconds=60)
        assert not await repository.settle_run(old, status="failed", now=later)
        await db.commit()
        assert await repository.renew_claim(new, now=later, lease_seconds=90)
        assert await repository.settle_run(new, status="skipped", now=later)
        await db.commit()


async def test_policy_change_revokes_inflight_claim(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    await enable(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as worker:
        claim = await DiscussionRepository(worker).claim_run(
            discussion_owner, now=NOW, lease_seconds=60
        )
        assert claim is not None
        await worker.commit()
    async with AsyncSession(async_engine) as manager:
        await DiscussionRepository(manager).update_policy(
            discussion_owner, DiscussionPolicyPatch(enabled=False), expected_revision=1
        )
        await manager.commit()
    async with AsyncSession(async_engine) as worker:
        assert not await DiscussionRepository(worker).renew_claim(claim, now=NOW, lease_seconds=60)


async def test_rollback_leaves_no_claim(async_engine: AsyncEngine, discussion_owner: UUID) -> None:
    await enable(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        assert (
            await DiscussionRepository(db).claim_run(discussion_owner, now=NOW, lease_seconds=60)
            is not None
        )
        await db.rollback()
        assert (
            await DiscussionRepository(db).claim_run(discussion_owner, now=NOW, lease_seconds=60)
            is not None
        )
