"""Publication consumes one logical opening in the same transaction as archive/outbox."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.repository import ConversationRepository
from src.domains.proactive_discussions.models import DiscussionOpeningRecord, DiscussionOutbox
from src.domains.proactive_discussions.publication_types import OpeningDraft
from src.domains.proactive_discussions.replies import REPLY_TO
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.schemas import EngageDecision
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.infrastructure.proactive.discussion_persistence import publication_repository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


def draft() -> OpeningDraft:
    return OpeningDraft(
        decision=EngageDecision(
            action="engage", topic="project", reason="follow-up", references=("event:1",)
        ),
        text="How did your project go?",
        fingerprint="event:1:v2",
    )


async def prepare(engine: AsyncEngine, owner: UUID):
    async with AsyncSession(engine) as db:
        await ConversationRepository(db).create_with_audit(owner, "Fictional conversation")
        repository = DiscussionRepository(db)
        await repository.update_policy(
            owner, DiscussionPolicyPatch(enabled=True, daily_max=1), expected_revision=0
        )
        claim = await repository.claim_run(owner, now=NOW, lease_seconds=60)
        await db.commit()
        assert claim is not None
        return claim


async def test_archive_opening_outbox_and_logical_count_are_atomic(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    claim = await prepare(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        receipt = await publication_repository(db).commit_opening(claim, draft(), now=NOW)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        message = await db.get(ConversationMessage, receipt.message_id)
        assert (
            message is not None
            and message.role == "assistant"
            and message.content == "How did your project go?"
        )
        assert message.message_metadata["type"] == "proactive_discussion"
        assert (
            await db.scalar(
                select(func.count())
                .select_from(DiscussionOpeningRecord)
                .where(DiscussionOpeningRecord.user_id == discussion_owner)
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(DiscussionOutbox)
                .where(DiscussionOutbox.opening_id == receipt.opening_id)
            )
            == 1
        )
        await db.execute(
            update(DiscussionOpeningRecord)
            .where(DiscussionOpeningRecord.id == receipt.opening_id)
            .values(state="dismissed")
        )
        await db.commit()
        assert (
            await DiscussionRepository(db).claim_run(discussion_owner, now=NOW, lease_seconds=60)
            is None
        )


async def test_rollback_consumes_neither_message_nor_quota(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    claim = await prepare(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        await publication_repository(db).commit_opening(claim, draft(), now=NOW)
        await db.rollback()
    async with AsyncSession(async_engine) as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(DiscussionOpeningRecord)
                .where(DiscussionOpeningRecord.user_id == discussion_owner)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ConversationMessage)
                .where(ConversationMessage.conversation_id == discussion_owner)
            )
            == 0
        )
        receipt = await publication_repository(db).commit_opening(claim, draft(), now=NOW)
        await db.commit()
        assert receipt.created


async def test_concurrent_replay_creates_one_archive(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    claim = await prepare(async_engine, discussion_owner)

    async def publish():
        async with AsyncSession(async_engine) as db:
            receipt = await publication_repository(db).commit_opening(claim, draft(), now=NOW)
            await db.commit()
            return receipt

    first, second = await asyncio.gather(publish(), publish())
    assert first.message_id == second.message_id and first.opening_id == second.opening_id
    assert sum(item.created for item in (first, second)) == 1


async def test_disabled_after_generation_blocks_archive(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    claim = await prepare(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        await DiscussionRepository(db).update_policy(
            discussion_owner, DiscussionPolicyPatch(enabled=False), expected_revision=1
        )
        await db.commit()
    async with AsyncSession(async_engine) as db:
        with pytest.raises(ResourceConflictError):
            await publication_repository(db).commit_opening(claim, draft(), now=NOW)


async def test_replay_cannot_substitute_a_different_message(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    claim = await prepare(async_engine, discussion_owner)
    async with AsyncSession(async_engine) as db:
        await publication_repository(db).commit_opening(claim, draft(), now=NOW)
        await db.commit()
    async with AsyncSession(async_engine) as db:
        changed = draft().model_copy(update={"text": "Different message"})
        with pytest.raises(ResourceConflictError):
            await publication_repository(db).commit_opening(claim, changed, now=NOW)


async def _open_all_day(engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(engine) as db:
        await ConversationRepository(db).create_with_audit(owner, "Fictional conversation")
        await DiscussionRepository(db).update_policy(
            owner, DiscussionPolicyPatch(enabled=True, daily_max=None), expected_revision=0
        )
        await db.commit()


async def _publish_at(
    engine: AsyncEngine, owner: UUID, *, at: datetime, fingerprint: str, pending_seconds: int
) -> UUID:
    async with AsyncSession(engine) as db:
        claim = await DiscussionRepository(db).claim_run(owner, now=at, lease_seconds=60)
        await db.commit()
    assert claim is not None
    async with AsyncSession(engine) as db:
        receipt = await publication_repository(db).commit_opening(
            claim,
            draft().model_copy(update={"fingerprint": fingerprint}),
            now=at,
            pending_seconds=pending_seconds,
        )
        await db.commit()
    return receipt.opening_id


async def _openings(engine: AsyncEngine, owner: UUID) -> dict[UUID, DiscussionOpeningRecord]:
    async with AsyncSession(engine) as db:
        rows = await db.scalars(
            select(DiscussionOpeningRecord).where(DiscussionOpeningRecord.user_id == owner)
        )
        return {row.id: row for row in rows}


async def test_a_new_opening_closes_the_one_still_awaiting_a_reply(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    # Owner decision 2026-10-23: an unanswered opening holds the next run back for an
    # hour, no longer for its whole reply window, so the next opening can find it still
    # pending. It closes it then — the one-pending-opening index would refuse otherwise.
    await _open_all_day(async_engine, discussion_owner)
    day = 24 * 3600
    first = await _publish_at(
        async_engine, discussion_owner, at=NOW, fingerprint="event:1:v2", pending_seconds=day
    )
    later = NOW + timedelta(hours=2)
    second = await _publish_at(
        async_engine, discussion_owner, at=later, fingerprint="event:2:v1", pending_seconds=day
    )
    rows = await _openings(async_engine, discussion_owner)
    assert (rows[first].state, rows[first].expires_at) == ("expired", later)
    assert rows[second].state == "pending"


async def test_an_opening_that_lapsed_keeps_its_own_deadline(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    await _open_all_day(async_engine, discussion_owner)
    hour = 3600
    first = await _publish_at(
        async_engine, discussion_owner, at=NOW, fingerprint="event:1:v2", pending_seconds=hour
    )
    await _publish_at(
        async_engine,
        discussion_owner,
        at=NOW + timedelta(hours=2),
        fingerprint="event:2:v1",
        pending_seconds=hour,
    )
    rows = await _openings(async_engine, discussion_owner)
    assert (rows[first].state, rows[first].expires_at) == (
        "expired",
        NOW + timedelta(seconds=hour),
    )


async def test_a_reply_written_before_the_next_opening_stays_bound_to_its_own(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    # A message a channel archives after the run's last check, under no conversation
    # lock, answers the opening it was written for: it is never filed as a lapse.
    await _open_all_day(async_engine, discussion_owner)
    day = 24 * 3600
    first = await _publish_at(
        async_engine, discussion_owner, at=NOW, fingerprint="event:1:v2", pending_seconds=day
    )
    replied = NOW + timedelta(minutes=90)
    reply_id = uuid4()
    async with AsyncSession(async_engine) as db:
        conversation = await ConversationRepository(db).get_active_for_user(discussion_owner)
        assert conversation is not None
        db.add(
            ConversationMessage(
                id=reply_id,
                conversation_id=conversation.id,
                role="user",
                content="A fictional reply",
                message_metadata={},
                created_at=replied,
            )
        )
        await db.commit()
    await _publish_at(
        async_engine,
        discussion_owner,
        at=NOW + timedelta(hours=2),
        fingerprint="event:2:v1",
        pending_seconds=day,
    )
    rows = await _openings(async_engine, discussion_owner)
    assert rows[first].state == "engaged"
    async with AsyncSession(async_engine) as db:
        bound = await db.get(ConversationMessage, reply_id)
    assert bound is not None and bound.message_metadata[REPLY_TO] == str(first)
