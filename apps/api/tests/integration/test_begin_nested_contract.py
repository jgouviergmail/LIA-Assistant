"""Savepoint contract of ``async with session.begin_nested()`` (audit AC-012).

Production code relies on BOTH protocols of ``AsyncSession.begin_nested()``:
``await`` (UnitOfWork) and ``async with`` (conversations best-effort cleanup,
usage_limits creation). The ``async with`` form is exactly what a bare
AsyncMock double silently broke — so its real semantics are pinned here
against PostgreSQL: an exception inside the block rolls back ONLY the
savepoint (outer transaction stays usable and commits), and a clean block
makes the inner changes durable with the outer commit.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User

pytestmark = pytest.mark.integration


def _user(tag: str) -> User:
    return User(
        email=f"ac012-{tag}-{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="hash",
        full_name=f"AC012 {tag}",
        is_active=True,
        is_verified=True,
    )


async def test_savepoint_rollback_preserves_outer_transaction(
    async_session: AsyncSession,
) -> None:
    """A failure inside ``async with begin_nested()`` must not poison the outer tx."""
    outer = _user("outer")
    async_session.add(outer)
    await async_session.flush()

    inner = _user("inner")
    with pytest.raises(RuntimeError, match="boom"):
        async with async_session.begin_nested():
            async_session.add(inner)
            await async_session.flush()
            raise RuntimeError("boom")

    # The outer transaction is still usable and commits the outer row only.
    await async_session.commit()

    result = await async_session.execute(select(User).where(User.email == outer.email))
    assert result.scalar_one_or_none() is not None, "outer row must survive"
    result = await async_session.execute(select(User).where(User.email == inner.email))
    assert result.scalar_one_or_none() is None, "savepoint rows must be rolled back"


async def test_savepoint_commit_persists_with_outer_commit(
    async_session: AsyncSession,
) -> None:
    """A clean ``async with begin_nested()`` block releases the savepoint."""
    inner = _user("kept")
    async with async_session.begin_nested():
        async_session.add(inner)
        await async_session.flush()

    await async_session.commit()

    result = await async_session.execute(select(User).where(User.email == inner.email))
    assert result.scalar_one_or_none() is not None, "released savepoint rows must persist"
