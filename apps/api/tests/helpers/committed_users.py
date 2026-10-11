"""Explicit ownership for accounts that must be visible across SQL connections."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.users.models import User


@asynccontextmanager
async def committed_user_scope(engine: AsyncEngine) -> AsyncIterator[list[UUID]]:
    """Remove precisely the registered accounts, even after a failed assertion.

    Register identifiers after flush and before commit. Dependent rows are removed
    by the real foreign-key cascades; unrelated accounts are never touched.
    """
    identities: list[UUID] = []
    try:
        yield identities
    finally:
        if identities:
            async with async_sessionmaker(engine)() as db:
                await db.execute(delete(User).where(User.id.in_(identities)))
                await db.commit()
