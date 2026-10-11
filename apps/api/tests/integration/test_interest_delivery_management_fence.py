"""The delivered-notification writer must share management's parent-first lock order."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.interests.proactive_task import InterestProactiveTask
from src.domains.interests.repository import InterestNotificationRepository
from src.domains.users.models import User
from src.infrastructure.proactive.base import ProactiveTaskResult
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("target_scope", ["deleted", "foreign"])
async def test_delivered_content_is_retained_without_an_unowned_or_deleted_target(
    async_session: AsyncSession,
    test_user: User,
    target_scope: str,
) -> None:
    owner = test_user.id
    target = UserInterest(
        id=uuid4(),
        user_id=owner,
        topic="Delivered topic",
        category="science",
        last_mentioned_at=datetime.now(UTC),
    )
    if target_scope == "foreign":
        foreign = User(
            id=uuid4(),
            email=f"delivery-other-{uuid4()}@example.test",
            full_name="Other",
            is_active=True,
            is_verified=True,
        )
        async_session.add(foreign)
        await async_session.flush()
        target.user_id = foreign.id
        async_session.add(target)
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        patch("src.domains.interests.proactive_task.get_db_context", session),
        patch(
            "src.domains.interests.helpers.generate_interest_embedding",
            new=AsyncMock(return_value=None),
        ),
    ):
        await InterestProactiveTask().on_notification_sent(
            owner,
            target,
            ProactiveTaskResult(success=True, content="Actually delivered text", source="test"),
        )
    audit = await async_session.scalar(
        select(InterestNotification).where(InterestNotification.user_id == owner)
    )
    assert (
        audit is not None
        and audit.interest_id is None
        and audit.content == "Actually delivered text"
    )
    if target_scope == "foreign":
        await async_session.refresh(target)
        assert target.last_notified_at is None


async def test_protocol_feedback_invalidates_old_learning_runs_and_refuses_foreign_targets(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    owner = test_user.id
    target = UserInterest(
        user_id=owner,
        topic="Protocol topic",
        category="science",
        positive_signals=3,
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(target)
    await async_session.commit()
    revision = test_user.extraction_revision

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with patch("src.domains.interests.proactive_task.get_db_context", session):
        await InterestProactiveTask().on_feedback(owner, target, "thumbs_up")
    await async_session.refresh(target)
    await async_session.refresh(test_user)
    assert target.positive_signals == 5 and test_user.extraction_revision == revision + 1
    foreign = User(
        id=uuid4(),
        email=f"protocol-other-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(foreign)
    await async_session.commit()
    with patch("src.domains.interests.proactive_task.get_db_context", session):
        await InterestProactiveTask().on_feedback(foreign.id, target, "thumbs_up")
    await async_session.refresh(target)
    assert target.positive_signals == 5


async def test_delivery_embedding_precedes_locks_and_audit_insert_holds_the_parent(
    async_engine: AsyncEngine,
) -> None:
    owner, identity = uuid4(), uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        seed.add(
            User(
                id=owner,
                email=f"delivery-fence-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
                is_verified=True,
            )
        )
        await seed.commit()
        row = UserInterest(
            id=identity,
            user_id=owner,
            topic="Source topic",
            category="science",
            last_mentioned_at=datetime.now(UTC),
        )
        seed.add(row)
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)

            @asynccontextmanager
            async def session() -> AsyncIterator[AsyncSession]:
                yield db

            async def embedding(topic: str):
                async with AsyncSession(async_engine) as observer:
                    assert (
                        await observer.scalar(
                            select(User.id).where(User.id == owner).with_for_update(nowait=True)
                        )
                        == owner
                    )
                    await observer.rollback()
                return None

            original = InterestNotificationRepository.create

            async def insert(repository, *args, **kwargs):
                writer_pid = await db.scalar(text("SELECT pg_backend_pid()"))
                async with AsyncSession(async_engine) as observer:
                    assert await observer.scalar(text("SELECT pg_backend_pid()")) != writer_pid
                    with pytest.raises(DBAPIError) as refusal:
                        await observer.scalar(
                            select(User.id).where(User.id == owner).with_for_update(nowait=True)
                        )
                    assert getattr(refusal.value.orig, "sqlstate", None) == "55P03"
                    await observer.rollback()
                return await original(repository, *args, **kwargs)

            with (
                patch("src.domains.interests.proactive_task.get_db_context", session),
                patch(
                    "src.domains.interests.helpers.generate_interest_embedding",
                    side_effect=embedding,
                ),
                patch.object(InterestNotificationRepository, "create", insert),
            ):
                await InterestProactiveTask().on_notification_sent(
                    owner,
                    row,
                    ProactiveTaskResult(success=True, content="Delivered text", source="test"),
                )
            audit = await db.scalar(
                select(InterestNotification).where(InterestNotification.user_id == owner)
            )
            assert (
                audit is not None
                and audit.interest_id == identity
                and audit.content == "Delivered text"
            )
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
