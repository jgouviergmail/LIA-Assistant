"""Committed fictional owners make cross-connection races observable."""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.users.models import User


@pytest_asyncio.fixture
async def discussion_owner(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> AsyncIterator[UUID]:
    identity = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            User(
                id=identity,
                email=f"discussion-{identity}@example.test",
                full_name="Fictional discussion owner",
                is_active=True,
                is_verified=True,
                is_superuser=False,
                timezone="UTC",
            )
        )
        await db.flush()
        committed_user_ids.append(identity)
        await db.commit()
    yield identity
