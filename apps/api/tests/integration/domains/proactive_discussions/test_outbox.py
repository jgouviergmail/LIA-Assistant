"""No duplicate external send, including withdrawal while transport is in flight."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.proactive_discussions.models import DiscussionOutbox
from src.domains.proactive_discussions.outbox_repository import DiscussionOutboxRepository
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.infrastructure.proactive.discussion_persistence import publication_repository
from tests.integration.domains.proactive_discussions.test_repository import NOW, draft, prepare

pytestmark = pytest.mark.integration


async def test_outbox_can_be_claimed_only_once(async_engine, discussion_owner):
    claim = await prepare(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        receipt = await publication_repository(db).commit_opening(claim, draft(), now=NOW)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        first = await DiscussionOutboxRepository(db).claim_delivery(
            discussion_owner, receipt.opening_id, now=NOW
        )
        await db.commit()
    assert first is not None
    async with AsyncSession(async_engine) as db:
        assert (
            await DiscussionOutboxRepository(db).claim_delivery(
                discussion_owner, receipt.opening_id, now=NOW
            )
            is None
        )


async def test_withdrawal_during_send_is_uncertain_until_receipt_not_falsely_cancelled(
    async_engine, discussion_owner
):
    claim = await prepare(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        receipt = await publication_repository(db).commit_opening(claim, draft(), now=NOW)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        envelope = await DiscussionOutboxRepository(db).claim_delivery(
            discussion_owner, receipt.opening_id, now=NOW
        )
        await db.commit()
    assert envelope is not None
    async with AsyncSession(async_engine) as db:
        await DiscussionOutboxRepository(db).update_policy(
            discussion_owner, DiscussionPolicyPatch(enabled=False), expected_revision=1
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        row = await db.scalar(
            select(DiscussionOutbox).where(DiscussionOutbox.opening_id == receipt.opening_id)
        )
        assert row.state == "uncertain"
        assert not await DiscussionOutboxRepository(db).may_send(envelope, now=NOW)
        assert await DiscussionOutboxRepository(db).settle_delivery(
            envelope, accepted=True, uncertain=False
        )
        await db.commit()
        await db.refresh(row)
        assert row.state == "delivered"


async def test_an_attempt_stalls_only_once_its_proofs_could_no_longer_send(
    async_engine, discussion_owner, monkeypatch
):
    # The stall threshold is the proofs' freshness, never a second number: a slow
    # attempt younger than it may still be sending, and marking it uncertain would
    # stop its remaining pushes and channels.
    monkeypatch.setattr(settings, "discussion_delivery_proof_max_age_minutes", 30)
    claim = await prepare(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        receipt = await publication_repository(db).commit_opening(claim, draft(), now=NOW)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        assert await DiscussionOutboxRepository(db).claim_delivery(
            discussion_owner, receipt.opening_id, now=NOW
        )
        await db.commit()
    states = []
    for minutes in (10, 31):
        async with AsyncSession(async_engine) as db:
            await DiscussionOutboxRepository(db).recover_deliveries(
                now=NOW + timedelta(minutes=minutes)
            )
            await db.commit()
            states.append(
                await db.scalar(
                    select(DiscussionOutbox.state).where(
                        DiscussionOutbox.opening_id == receipt.opening_id
                    )
                )
            )
    assert states == ["dispatching", "uncertain"]


async def test_lost_ack_is_never_blindly_retried(async_engine, discussion_owner):
    claim = await prepare(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        receipt = await publication_repository(db).commit_opening(claim, draft(), now=NOW)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        envelope = await DiscussionOutboxRepository(db).claim_delivery(
            discussion_owner, receipt.opening_id, now=NOW
        )
        await db.commit()
    assert envelope is not None
    async with AsyncSession(async_engine) as db:
        await DiscussionOutboxRepository(db).recover_deliveries(now=NOW + timedelta(minutes=10))
        await db.commit()
        assert (
            await DiscussionOutboxRepository(db).claim_delivery(
                discussion_owner, receipt.opening_id, now=NOW + timedelta(minutes=10)
            )
            is None
        )
