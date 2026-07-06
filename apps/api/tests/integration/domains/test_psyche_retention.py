"""Integration tests for psyche_history rolling retention (N-201).

Verifies the actual window-based purge against a live database: snapshots older
than the configured retention window are deleted, recent ones are kept, and the
purge is strictly scoped to the target user.

Phase: 2026-07 latent-debt remediation (N-201).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import get_password_hash
from src.domains.auth.models import User
from src.domains.psyche.constants import SNAPSHOT_TYPE_MESSAGE
from src.domains.psyche.models import PsycheHistory
from src.domains.psyche.repository import PsycheStateRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _count(session: AsyncSession, user_id) -> int:
    """Return the number of history snapshots for a user."""
    result = await session.execute(
        select(func.count()).select_from(PsycheHistory).where(PsycheHistory.user_id == user_id)
    )
    return int(result.scalar_one())


def _snapshot(user_id, created_at: datetime) -> PsycheHistory:
    """Build a minimal message snapshot with an explicit creation time."""
    return PsycheHistory(
        user_id=user_id,
        snapshot_type=SNAPSHOT_TYPE_MESSAGE,
        created_at=created_at,
    )


class TestSnapshotRetention:
    """Window-based purge behaviour against a real database."""

    async def test_purges_only_snapshots_older_than_window(
        self, async_session: AsyncSession, test_user: User
    ):
        """Snapshots older than the window are deleted; recent ones survive."""
        now = datetime.now(UTC)
        for i in range(3):  # beyond a 90-day window
            async_session.add(_snapshot(test_user.id, now - timedelta(days=120 + i)))
        for i in range(2):  # within the window
            async_session.add(_snapshot(test_user.id, now - timedelta(days=i)))
        await async_session.flush()
        assert await _count(async_session, test_user.id) == 5

        repo = PsycheStateRepository(async_session)
        deleted = await repo.delete_snapshots_older_than(test_user.id, 90, now=now)

        assert deleted == 3
        assert await _count(async_session, test_user.id) == 2

    async def test_noop_when_disabled(self, async_session: AsyncSession, test_user: User):
        """days == 0 keeps everything (retention disabled)."""
        now = datetime.now(UTC)
        async_session.add(_snapshot(test_user.id, now - timedelta(days=400)))
        await async_session.flush()

        repo = PsycheStateRepository(async_session)
        deleted = await repo.delete_snapshots_older_than(test_user.id, 0, now=now)

        assert deleted == 0
        assert await _count(async_session, test_user.id) == 1

    async def test_purge_is_scoped_to_the_target_user(
        self, async_session: AsyncSession, test_user: User
    ):
        """Another user's old snapshots are never touched by the purge."""
        other = User(
            email="other-psyche@example.com",
            hashed_password=get_password_hash("OtherPass123!!"),
            full_name="Other User",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        async_session.add(other)
        await async_session.flush()

        now = datetime.now(UTC)
        async_session.add(_snapshot(test_user.id, now - timedelta(days=400)))
        async_session.add(_snapshot(other.id, now - timedelta(days=400)))
        await async_session.flush()

        repo = PsycheStateRepository(async_session)
        deleted = await repo.delete_snapshots_older_than(test_user.id, 90, now=now)

        assert deleted == 1
        assert await _count(async_session, test_user.id) == 0
        assert await _count(async_session, other.id) == 1  # untouched
