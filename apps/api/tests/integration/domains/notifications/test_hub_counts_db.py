"""The hub badge and the page it describes count the SAME set.

Against a real PostgreSQL, because that is the only place the question can be
settled: two SQL filters that look alike in review can still disagree on NULLs,
on a join, or on a row another test inserted.

The invariant under test is not "the number is 7". It is that
``count_history_for_user`` and the total ``get_history`` returns are ONE
implementation — the page now delegates to the counter rather than repeating
its filter, so a filter added to one can no longer be missing from the other.
That is the defect class ADR-185 names: a figure shown to the reader is a
claim, and two claims about one set is one claim too many.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.heartbeat.repository import HeartbeatNotificationRepository
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.interests.repository import InterestNotificationRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _make_user(db: AsyncSession) -> uuid.UUID:
    """A user row the foreign keys can point at."""
    from src.domains.users.models import User

    user = User(
        email=f"hub-counts-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 60,
        full_name="Hub Counts",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return user.id


class TestHeartbeatCountsAgreeWithItsPage:
    async def test_the_badge_and_the_page_report_the_same_total(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _make_user(db_session)
        repo = HeartbeatNotificationRepository(db_session)

        for index in range(13):
            db_session.add(
                HeartbeatNotification(
                    user_id=user_id,
                    run_id=f"run-{uuid.uuid4().hex[:12]}",
                    content=f"notification {index}",
                    content_hash=f"hash-{index}",
                    sources_used="test",
                )
            )
        await db_session.flush()

        counted = await repo.count_history_for_user(user_id)
        # A page far smaller than the set: the total must describe the SET.
        page, page_total = await repo.get_history(user_id, limit=5)

        assert counted == 13
        assert page_total == counted
        assert len(page) == 5

    async def test_an_empty_history_counts_zero_not_none(self, db_session: AsyncSession) -> None:
        user_id = await _make_user(db_session)

        assert (
            await HeartbeatNotificationRepository(db_session).count_history_for_user(user_id) == 0
        )

    async def test_another_account_is_never_counted(self, db_session: AsyncSession) -> None:
        """The count is scoped, like the page it describes."""
        mine = await _make_user(db_session)
        theirs = await _make_user(db_session)
        repo = HeartbeatNotificationRepository(db_session)

        db_session.add(
            HeartbeatNotification(
                user_id=theirs,
                run_id=f"run-{uuid.uuid4().hex[:12]}",
                content="not mine",
                content_hash="hash-theirs",
                sources_used="test",
            )
        )
        await db_session.flush()

        assert await repo.count_history_for_user(mine) == 0
        assert await repo.count_history_for_user(theirs) == 1


class TestInterestCountsAgreeWithItsPage:
    async def test_the_badge_and_the_page_report_the_same_total(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _make_user(db_session)
        interest = UserInterest(
            user_id=user_id,
            topic="astronomy",
            category="science",
            status="active",
            last_mentioned_at=datetime.now(UTC),
        )
        db_session.add(interest)
        await db_session.flush()

        repo = InterestNotificationRepository(db_session)
        for index in range(7):
            db_session.add(
                InterestNotification(
                    user_id=user_id,
                    interest_id=interest.id,
                    run_id=f"run-{uuid.uuid4().hex[:12]}",
                    content_hash=f"hash-{index}",
                    source="perplexity",
                )
            )
        await db_session.flush()

        counted = await repo.count_history_for_user(user_id)
        page, page_total = await repo.get_history(user_id, limit=3)

        assert counted == 7
        assert page_total == counted
        assert len(page) == 3

    async def test_another_account_is_never_counted(self, db_session: AsyncSession) -> None:
        mine = await _make_user(db_session)

        assert await InterestNotificationRepository(db_session).count_history_for_user(mine) == 0
