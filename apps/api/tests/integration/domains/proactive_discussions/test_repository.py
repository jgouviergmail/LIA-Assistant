"""Publication consumes one logical opening in the same transaction as archive/outbox."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.repository import ConversationRepository
from src.domains.proactive_discussions.models import DiscussionOpeningRecord, DiscussionOutbox
from src.domains.proactive_discussions.publication_types import OpeningDraft
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
