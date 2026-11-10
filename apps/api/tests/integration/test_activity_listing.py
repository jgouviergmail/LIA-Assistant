"""Timeline filters and pool boundaries proved against real source rows."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.activity.fetchers import fetch_open_loops
from src.domains.open_loops.models import OpenLoop
from src.domains.users.models import User

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 1, tzinfo=UTC)


async def test_created_and_closed_loops_get_independent_ordered_pools(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    """A recently closed old loop must not evict a recently created loop."""
    old = OpenLoop(
        id=uuid4(),
        user_id=test_user.id,
        subject="Old, closed today",
        direction="user_owes",
        status="closed",
        created_at=NOW - timedelta(days=20),
        updated_at=NOW,
    )
    recent = OpenLoop(
        id=uuid4(),
        user_id=test_user.id,
        subject="Created yesterday",
        direction="user_owes",
        status="closed",
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(hours=1),
    )
    async_session.add_all([old, recent])
    await async_session.flush()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with patch("src.domains.activity.fetchers.get_db_context", session):
        bundles = await fetch_open_loops(
            user_id=test_user.id, since=NOW - timedelta(days=30), cap=1
        )
    by_kind = {bundle.kind: bundle for bundle in bundles}
    assert by_kind["open_loop_created"].events[0].ref_id == str(recent.id)
    assert by_kind["open_loop_closed"].events[0].ref_id == str(old.id)
    assert all(bundle.total == 2 and bundle.truncated for bundle in bundles)
