"""Personal records keep their own statuses, independent of notification switches."""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.interests.discussion_source import InterestDiscussionSource
from src.domains.interests.models import UserInterest
from src.domains.open_loops.discussion_source import OpenLoopDiscussionSource
from src.domains.open_loops.models import OpenLoop
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey
from src.domains.users.models import User
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def seed_records(engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(engine) as db:
        user = await db.get(User, owner)
        assert user is not None
        user.interests_enabled = (
            False  # Native switch controls notifications, not reading saved interests.
        )
        db.add_all(
            [
                UserInterest(user_id=owner, topic="Fictional jazz", last_mentioned_at=NOW),
                UserInterest(
                    user_id=owner, topic="Blocked topic", status="blocked", last_mentioned_at=NOW
                ),
                OpenLoop(
                    user_id=owner,
                    subject="Send a fictional score",
                    direction="user_owes",
                    status="open",
                ),
                OpenLoop(
                    user_id=owner,
                    subject="Dismissed fictional concert",
                    direction="waiting_on_other",
                    status="closed",
                    closed_reason="dismissed",
                ),
            ]
        )
        await db.commit()


async def test_only_active_interests_remain_readable_when_notifications_off(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "interest_extraction_enabled", True)
    await seed_records(async_engine, discussion_owner)
    result = await InterestDiscussionSource().read(
        read_request(discussion_owner, SourceKey.INTERESTS)
    )
    assert result.total == 1 and result.complete
    assert "Fictional jazz" in result.items[0].excerpt
    assert "Blocked topic" not in result.model_dump_json()
    assert result.items[0].occurred_at is None


async def test_closed_loop_is_not_invented_as_completed_action(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "open_loops_enabled", True)
    await seed_records(async_engine, discussion_owner)
    result = await OpenLoopDiscussionSource().read(
        read_request(discussion_owner, SourceKey.OPEN_LOOPS)
    )
    assert result.total == 2 and result.complete
    closed = next(item for item in result.items if "Dismissed" in item.excerpt)
    assert "closed" in closed.excerpt and "dismissed" in closed.excerpt
    assert closed.occurred_at is None and closed.assertion == "inferred"


async def test_native_alert_bookkeeping_does_not_reopen_analysis(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "interest_extraction_enabled", True)
    monkeypatch.setattr(settings, "open_loops_enabled", True)
    await seed_records(async_engine, discussion_owner)
    interests, loops = InterestDiscussionSource(), OpenLoopDiscussionSource()
    interest_scope, loop_scope = read_request(discussion_owner, SourceKey.INTERESTS), read_request(
        discussion_owner, SourceKey.OPEN_LOOPS
    )
    first, original = await interests.read(interest_scope), await loops.read(loop_scope)
    async with AsyncSession(async_engine) as db:
        row = await db.scalar(
            select(UserInterest).where(
                UserInterest.user_id == discussion_owner, UserInterest.status == "active"
            )
        )
        assert row is not None
        row.last_notified_at = NOW
        for loop in (
            await db.scalars(select(OpenLoop).where(OpenLoop.user_id == discussion_owner))
        ).all():
            loop.nudge_count += 1
            loop.last_nudged_at = NOW
        await db.commit()
    later, changed = await interests.read(interest_scope), await loops.read(loop_scope)
    assert first.items[0].version == later.items[0].version
    assert {item.reference: item.version for item in original.items} == {
        item.reference: item.version for item in changed.items
    }


async def test_search_filters_before_native_page_and_total(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "open_loops_enabled", True)
    await seed_records(async_engine, discussion_owner)
    scope = read_request(discussion_owner, SourceKey.OPEN_LOOPS).model_copy(
        update={
            "request": ResearchRequest(
                source=SourceKey.OPEN_LOOPS, operation="search", query="score"
            )
        }
    )
    result = await OpenLoopDiscussionSource().read(scope)
    assert result.total == 1 and "score" in result.items[0].excerpt and not result.complete
