"""Explicit ownership for accounts that must be visible across SQL connections."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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


async def commit_owner(
    engine: AsyncEngine, identities: list[UUID], *, full_name: str = "Fictional account owner"
) -> UUID:
    """Commit one account other connections can see, registered for removal.

    Args:
        engine: The test engine.
        identities: The scope's registry (``committed_user_ids``).
        full_name: The account's display name.

    Returns:
        The account's identifier.
    """
    identity = uuid4()
    async with AsyncSession(engine) as db:
        db.add(
            User(
                id=identity,
                email=f"owner-{identity}@example.test",
                full_name=full_name,
                is_active=True,
                is_verified=True,
                is_superuser=False,
                timezone="UTC",
            )
        )
        await db.flush()
        identities.append(identity)
        await db.commit()
    return identity
