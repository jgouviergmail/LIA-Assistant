"""Real commits for tests whose collaborators use independent SQL connections.

Only importing modules opt in. Every ORM account created by the session is
registered before commit, and the session closes before those accounts are removed.
"""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from src.domains.users.models import User


@pytest.fixture
async def async_session(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> AsyncIterator[AsyncSession]:
    """Keep actual commit/rollback semantics and precisely owned cleanup."""
    async with AsyncSession(async_engine, expire_on_commit=False) as db:

        def remember(session: Session, _context: object) -> None:
            for row in session.new:
                if isinstance(row, User) and row.id not in committed_user_ids:
                    committed_user_ids.append(row.id)

        event.listen(db.sync_session, "after_flush", remember)
        try:
            yield db
        finally:
            event.remove(db.sync_session, "after_flush", remember)
