"""Integration tests for subject-selection repository additions (ADR-131).

Covers the query-shaped methods a mocked session cannot prove:
- case-insensitive topic lookup (SQL lower())
- per-user notification lookback window
- duplicate merge with notification repointing

Requires a real database (external via TEST_DATABASE_URL or Testcontainers).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.interests.models import UserInterest
from src.domains.interests.repository import (
    InterestNotificationRepository,
    InterestRepository,
)
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def owner(async_session: AsyncSession) -> User:
    """A committed user owning the interests under test."""
    user = User(
        email=f"interests-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="x",
        full_name="Interest Owner",
        is_active=True,
        is_verified=True,
    )
    async_session.add(user)
    await async_session.flush()
    return user


@pytest_asyncio.fixture
async def repo(async_session: AsyncSession) -> InterestRepository:
    return InterestRepository(async_session)


@pytest_asyncio.fixture
async def notif_repo(async_session: AsyncSession) -> InterestNotificationRepository:
    return InterestNotificationRepository(async_session)


class TestCaseInsensitiveLookup:
    async def test_finds_topic_regardless_of_case(
        self, repo: InterestRepository, owner: User
    ) -> None:
        await repo.create(user_id=owner.id, topic="Anthropic", category="technology")
        found = await repo.get_by_user_and_topic_ci(owner.id, "anthropic")
        assert found is not None
        assert found.topic == "Anthropic"

    async def test_returns_none_when_absent(self, repo: InterestRepository, owner: User) -> None:
        assert await repo.get_by_user_and_topic_ci(owner.id, "missing") is None


class TestGetRecentForUser:
    async def test_filters_by_lookback_window(
        self,
        repo: InterestRepository,
        notif_repo: InterestNotificationRepository,
        owner: User,
    ) -> None:
        interest = await repo.create(user_id=owner.id, topic="langgraph", category="technology")
        recent = await notif_repo.create(
            user_id=owner.id,
            interest_id=interest.id,
            run_id=f"r_{uuid.uuid4().hex[:8]}",
            content_hash="h1",
            source="wikipedia",
        )
        old = await notif_repo.create(
            user_id=owner.id,
            interest_id=interest.id,
            run_id=f"r_{uuid.uuid4().hex[:8]}",
            content_hash="h2",
            source="wikipedia",
        )
        old.created_at = datetime.now(UTC) - timedelta(days=40)
        await notif_repo.db.flush()

        rows = await notif_repo.get_recent_for_user(owner.id, days=30)
        ids = {r.id for r in rows}
        assert recent.id in ids
        assert old.id not in ids


class TestMergeInterests:
    async def test_merge_sums_signals_and_repoints_notifications(
        self,
        repo: InterestRepository,
        notif_repo: InterestNotificationRepository,
        owner: User,
    ) -> None:
        keep = await repo.create(user_id=owner.id, topic="Anthropic", category="technology")
        keep.positive_signals, keep.negative_signals = 10, 1
        dup = await repo.create(user_id=owner.id, topic="anthropic", category="technology")
        dup.positive_signals, dup.negative_signals = 4, 2
        dup.last_notified_at = datetime.now(UTC)
        dup.subject = "IA"
        notif = await notif_repo.create(
            user_id=owner.id,
            interest_id=dup.id,
            run_id=f"r_{uuid.uuid4().hex[:8]}",
            content_hash="h",
            source="wikipedia",
        )

        merged = await repo.merge_interests(keep, dup)

        assert merged.positive_signals == 14
        assert merged.negative_signals == 3
        assert merged.last_notified_at is not None
        assert merged.subject is None  # re-clustering trigger
        refreshed = await notif_repo.get_by_id(notif.id)
        assert refreshed is not None and refreshed.interest_id == keep.id
        assert await repo.get_by_id(dup.id) is None


class TestGetAllForUserOrdering:
    async def test_returns_most_recent_first(self, repo: InterestRepository, owner: User) -> None:
        first = await repo.create(user_id=owner.id, topic="older", category="other")
        first.created_at = datetime.now(UTC) - timedelta(days=2)
        await repo.create(user_id=owner.id, topic="newer", category="other")
        await repo.db.flush()

        rows = await repo.get_all_for_user(owner.id)
        topics = [r.topic for r in rows]
        assert topics.index("newer") < topics.index("older")
        assert isinstance(rows[0], UserInterest)
