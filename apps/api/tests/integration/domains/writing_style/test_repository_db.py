"""Real PostgreSQL proves the writing-style profile's writes (ADR-383)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.account_deletion_service import build_purge_statements
from src.domains.users.models import User
from src.domains.writing_style.models import WritingStyle
from src.domains.writing_style.repository import StoredStyle, WritingStyleRepository

pytestmark = pytest.mark.integration
BUILT = datetime(2026, 11, 13, 9, tzinfo=UTC)


async def _rows(db: AsyncSession, user: User) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(WritingStyle).where(WritingStyle.user_id == user.id)
        )
        or 0
    )


async def test_one_profile_per_account_the_last_learning_winning(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = WritingStyleRepository(async_session)

    assert await repo.save(test_user.id, profile_encrypted="first", mails_read=12, built_at=BUILT)
    later = BUILT + timedelta(days=31)
    assert await repo.save(test_user.id, profile_encrypted=None, mails_read=2, built_at=later)

    stored = await repo.read(test_user.id)
    assert stored is not None and stored.enabled and stored.row is not None
    assert (stored.row.profile_encrypted, stored.row.mails_read) == (None, 2)
    assert stored.row.built_at == later
    assert await _rows(async_session, test_user) == 1


async def test_nothing_is_kept_while_the_switch_is_off(
    async_session: AsyncSession, test_user: User
) -> None:
    test_user.writing_style_enabled = False
    await async_session.flush()
    repo = WritingStyleRepository(async_session)

    assert not await repo.save(test_user.id, profile_encrypted="x", mails_read=12, built_at=BUILT)
    assert await repo.read(test_user.id) == StoredStyle(enabled=False, row=None)


async def test_forget_removes_the_profile_and_says_whether_there_was_one(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = WritingStyleRepository(async_session)
    assert not await repo.forget(test_user.id)

    await repo.save(test_user.id, profile_encrypted="x", mails_read=12, built_at=BUILT)

    assert await repo.forget(test_user.id)
    stored = await repo.read(test_user.id)
    assert stored is not None and stored.row is None


async def test_an_unknown_account_reads_as_none(async_session: AsyncSession) -> None:
    assert await WritingStyleRepository(async_session).read(uuid4()) is None


async def test_the_account_purge_removes_the_profile(
    async_session: AsyncSession, test_user: User
) -> None:
    """Deletion SCRUBS the users row, so no FK cascade fires: the profile has its own DELETE."""
    await WritingStyleRepository(async_session).save(
        test_user.id, profile_encrypted="x", mails_read=12, built_at=BUILT
    )
    _, purge = next(
        item for item in build_purge_statements(test_user.id) if item[0] == "writing_styles"
    )

    removed = await async_session.execute(purge)

    assert removed.rowcount == 1
    assert await _rows(async_session, test_user) == 0
