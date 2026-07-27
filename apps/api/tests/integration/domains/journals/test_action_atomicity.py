"""Per-action atomicity of the journal maintenance loops, against PostgreSQL.

``extraction_service`` and ``consolidation_service`` apply the LLM's actions in
one loop, each iteration wrapped in ``try/except ... continue``, with a single
``commit()`` at the end. That reads as "a bad action is skipped, the good ones
still land" — and on PostgreSQL it is not true: any statement error aborts the
whole transaction, so every later action fails on the poisoned session and the
final commit raises. The `continue` silently degraded into all-or-nothing.

These tests pin the mechanism against the real database:

- the control reproduces the poisoning, so the guard below cannot be mistaken
  for a no-op;
- the guarded case proves ``begin_nested()`` (a SAVEPOINT) isolates the failure.

Both run the real ``JournalService`` on real ``JournalEntry`` rows: the failure
is a genuine column-length violation, not a synthetic exception.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.models import JournalEntry
from src.domains.journals.service import JournalService
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# `title` is String(200); PostgreSQL rejects anything longer. `content` is Text
# and `create_entry` truncates it, so the title is the reachable failure.
_OVERLONG_TITLE = "x" * 400


async def _make_user(session: AsyncSession) -> User:
    """Insert a minimal user owning the journal entries."""
    user = User(
        email=f"atomicity-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _count_entries(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Count the user's journal entries."""
    result = await session.execute(
        select(func.count(JournalEntry.id)).where(JournalEntry.user_id == user_id)
    )
    return int(result.scalar() or 0)


@pytest.fixture
def _no_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the embedding network call — this suite is about transactions."""

    async def _none(_text: str) -> None:
        return None

    monkeypatch.setattr("src.domains.journals.service._generate_document_embedding", _none)


class TestActionLoopAtomicity:
    """A failing action must not take the whole batch down with it."""

    async def test_control_without_savepoint_poisons_the_transaction(
        self, async_session: AsyncSession, _no_embeddings: None
    ) -> None:
        """Without a SAVEPOINT, the action AFTER the failure also fails.

        This is the control: it demonstrates the defect the guard fixes. If it
        ever stops failing, the guard below has become meaningless and this
        whole suite should be re-derived.
        """
        user = await _make_user(async_session)
        service = JournalService(async_session)

        await service.create_entry(user_id=user.id, theme="learnings", title="first", content="ok")

        with pytest.raises((DBAPIError, SQLAlchemyError)):
            await service.create_entry(
                user_id=user.id, theme="learnings", title=_OVERLONG_TITLE, content="bad"
            )

        # The session is now aborted: a perfectly valid third action fails too,
        # which is exactly what the `except ... continue` hid.
        with pytest.raises(SQLAlchemyError):
            await service.create_entry(
                user_id=user.id, theme="learnings", title="third", content="ok"
            )

    async def test_savepoint_isolates_the_failing_action(
        self, async_session: AsyncSession, _no_embeddings: None
    ) -> None:
        """With one SAVEPOINT per action, the good actions still land.

        Mirrors the production loop: three actions, the middle one invalid,
        each wrapped in ``begin_nested()`` under ``try/except ... continue``.
        """
        user = await _make_user(async_session)
        service = JournalService(async_session)

        planned = [
            ("first", "ok"),
            (_OVERLONG_TITLE, "bad"),
            ("third", "ok"),
        ]
        applied = 0
        for title, content in planned:
            try:
                async with async_session.begin_nested():
                    await service.create_entry(
                        user_id=user.id, theme="learnings", title=title, content=content
                    )
                    applied += 1
            except SQLAlchemyError:
                continue

        assert applied == 2, "the two valid actions should have been applied"
        assert await _count_entries(async_session, user.id) == 2

        titles = (
            (
                await async_session.execute(
                    select(JournalEntry.title).where(JournalEntry.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        assert sorted(titles) == ["first", "third"]

    async def test_savepoint_leaves_the_session_usable_after_the_batch(
        self, async_session: AsyncSession, _no_embeddings: None
    ) -> None:
        """The final commit succeeds even though one action failed.

        Before the guard, the batch-terminating ``commit()`` raised and the
        caller logged a whole-run failure while the per-action warnings
        suggested a partial degradation.
        """
        user = await _make_user(async_session)
        service = JournalService(async_session)

        try:
            async with async_session.begin_nested():
                await service.create_entry(
                    user_id=user.id, theme="learnings", title=_OVERLONG_TITLE, content="bad"
                )
        except SQLAlchemyError:
            pass

        await service.create_entry(user_id=user.id, theme="learnings", title="after", content="ok")
        await async_session.commit()

        assert await _count_entries(async_session, user.id) == 1
