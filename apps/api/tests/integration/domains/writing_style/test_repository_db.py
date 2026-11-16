"""Real PostgreSQL proves the writing-style profile's writes (ADR-383)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import CursorResult
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


async def _standing(repo: WritingStyleRepository, user: User) -> datetime | None:
    """When the record that stands was learned, or None when none does."""
    stored = await repo.read(user.id)
    assert stored is not None
    return stored.row.built_at if stored.row is not None else None


async def test_one_profile_per_account_a_learning_replacing_the_record_asked_on(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = WritingStyleRepository(async_session)

    assert await repo.save(
        test_user.id, profile_encrypted="first", mails_read=12, built_at=BUILT, replaces=None
    )
    later = BUILT + timedelta(days=31)
    assert await repo.save(
        test_user.id, profile_encrypted=None, mails_read=2, built_at=later, replaces=BUILT
    )

    stored = await repo.read(test_user.id)
    assert stored is not None and stored.enabled and stored.row is not None
    assert (stored.row.profile_encrypted, stored.row.mails_read) == (None, 2)
    assert stored.row.built_at == later
    assert await _rows(async_session, test_user) == 1


async def test_nothing_is_kept_while_the_switch_is_off(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = WritingStyleRepository(async_session)
    assert await repo.save(
        test_user.id, profile_encrypted="x", mails_read=12, built_at=BUILT, replaces=None
    )
    test_user.writing_style_enabled = False
    await async_session.flush()

    # Neither in place of the record that stands, nor where nothing stands.
    later = BUILT + timedelta(days=1)
    assert not await repo.save(
        test_user.id, profile_encrypted="y", mails_read=30, built_at=later, replaces=BUILT
    )
    assert await repo.forget(test_user.id)
    assert not await repo.save(
        test_user.id, profile_encrypted="y", mails_read=30, built_at=later, replaces=None
    )
    assert await repo.read(test_user.id) == StoredStyle(enabled=False, row=None)


async def test_a_learning_keeps_nothing_over_a_record_forgotten_meanwhile(
    async_session: AsyncSession, test_user: User
) -> None:
    """Asked to replace a record the person forgot while it ran: the forgetting stands."""
    repo = WritingStyleRepository(async_session)
    await repo.save(
        test_user.id, profile_encrypted="x", mails_read=12, built_at=BUILT, replaces=None
    )
    assert await repo.forget(test_user.id)

    learned = BUILT + timedelta(hours=1)
    assert not await repo.save(
        test_user.id, profile_encrypted="y", mails_read=12, built_at=learned, replaces=BUILT
    )

    assert await _rows(async_session, test_user) == 0


async def test_a_learning_asked_on_nothing_keeps_nothing_once_a_record_stands(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = WritingStyleRepository(async_session)
    assert await repo.save(
        test_user.id, profile_encrypted="x", mails_read=12, built_at=BUILT, replaces=None
    )

    later = BUILT + timedelta(hours=1)
    assert not await repo.save(
        test_user.id, profile_encrypted="y", mails_read=30, built_at=later, replaces=None
    )

    assert await _standing(repo, test_user) == BUILT
    assert await _rows(async_session, test_user) == 1


async def test_a_learning_replaces_the_record_it_was_asked_on_and_nothing_since(
    async_session: AsyncSession, test_user: User
) -> None:
    """Two learnings asked on the same record: the first replaces it, the second keeps
    nothing over the record the first one wrote."""
    repo = WritingStyleRepository(async_session)
    asked_on = BUILT.replace(microsecond=123456)
    await repo.save(
        test_user.id, profile_encrypted="x", mails_read=12, built_at=asked_on, replaces=None
    )
    first = asked_on + timedelta(minutes=1)
    second = asked_on + timedelta(minutes=2)

    # What a card carries is the ISO text of the instant: it names the row exactly.
    named = datetime.fromisoformat(asked_on.isoformat())
    assert await repo.save(
        test_user.id, profile_encrypted="y", mails_read=30, built_at=first, replaces=named
    )
    assert not await repo.save(
        test_user.id, profile_encrypted="z", mails_read=30, built_at=second, replaces=named
    )

    stored = await repo.read(test_user.id)
    assert stored is not None and stored.row is not None
    assert (stored.row.built_at, stored.row.profile_encrypted) == (first, "y")


async def test_forget_removes_the_profile_and_says_whether_there_was_one(
    async_session: AsyncSession, test_user: User
) -> None:
    repo = WritingStyleRepository(async_session)
    assert not await repo.forget(test_user.id)

    await repo.save(
        test_user.id, profile_encrypted="x", mails_read=12, built_at=BUILT, replaces=None
    )

    assert await repo.forget(test_user.id)
    stored = await repo.read(test_user.id)
    assert stored is not None and stored.row is None


async def test_forgetting_a_named_record_keeps_one_learned_since(
    async_session: AsyncSession, test_user: User
) -> None:
    """The assistant's card names one record: a style learned after it is another, kept."""
    repo = WritingStyleRepository(async_session)
    shown = BUILT.replace(microsecond=123456)
    await repo.save(
        test_user.id, profile_encrypted="x", mails_read=12, built_at=shown, replaces=None
    )
    since = shown + timedelta(minutes=5)
    await repo.save(
        test_user.id, profile_encrypted="y", mails_read=30, built_at=since, replaces=shown
    )

    assert not await repo.forget(test_user.id, learned_at=shown)
    stored = await repo.read(test_user.id)
    assert stored is not None and stored.row is not None and stored.row.built_at == since

    # What a card carries is the ISO text of the instant: it names the row exactly.
    named = datetime.fromisoformat(stored.row.built_at.isoformat())
    assert await repo.forget(test_user.id, learned_at=named)
    assert await _rows(async_session, test_user) == 0


async def test_an_unknown_account_reads_as_none(async_session: AsyncSession) -> None:
    assert await WritingStyleRepository(async_session).read(uuid4()) is None


async def test_the_account_purge_removes_the_profile(
    async_session: AsyncSession, test_user: User
) -> None:
    """Deletion SCRUBS the users row, so no FK cascade fires: the profile has its own DELETE."""
    await WritingStyleRepository(async_session).save(
        test_user.id, profile_encrypted="x", mails_read=12, built_at=BUILT, replaces=None
    )
    _, purge = next(
        item for item in build_purge_statements(test_user.id) if item[0] == "writing_styles"
    )

    removed = await async_session.execute(purge)

    assert isinstance(removed, CursorResult) and removed.rowcount == 1
    assert await _rows(async_session, test_user) == 0
