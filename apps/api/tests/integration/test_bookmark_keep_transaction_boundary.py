"""Keeping a native answer defers commit and indexing; account quota survives a real race."""

import asyncio
from unittest.mock import Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import settings
from src.domains.bookmarks.errors import BookmarkLimitReachedError
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.service import BookmarkService
from src.domains.users.models import User
from tests.integration.domains.bookmarks.test_bookmarks_db import _conversation, _message

pytestmark = pytest.mark.integration


async def test_deferred_keep_rollback_has_no_early_commit_or_index_job(
    async_session, test_user, monkeypatch
):
    owner = test_user.id
    conversation = await _conversation(async_session, test_user)
    answer = await _message(
        async_session, conversation, role="assistant", content="Approved answer", minutes=1
    )
    await async_session.commit()
    message_id = answer.id
    index_job = Mock(side_effect=AssertionError("Indexing must wait for known native commit"))
    monkeypatch.setattr("src.domains.bookmarks.service.safe_fire_and_forget", index_job)
    service = BookmarkService(async_session)
    bookmark, created = await service.keep(owner, message_id, commit=False)
    assert created and bookmark.content == "Approved answer"
    assert (
        await async_session.scalar(
            select(func.count(MessageBookmark.id)).where(MessageBookmark.user_id == owner)
        )
        == 1
    )
    index_job.assert_not_called()
    await async_session.rollback()
    assert (
        await async_session.scalar(
            select(func.count(MessageBookmark.id)).where(MessageBookmark.user_id == owner)
        )
        == 0
    )


@pytest_asyncio.fixture
async def independent_bookmark_sessions(async_engine):
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    marker = uuid4().hex
    yield maker, marker
    async with maker() as session:
        await session.execute(
            delete(User).where(User.email == f"bookmark-race-{marker}@example.test")
        )
        await session.commit()


async def test_two_answer_keeps_racing_for_the_last_slot_do_not_exceed_quota(
    independent_bookmark_sessions, monkeypatch
):
    maker, marker = independent_bookmark_sessions
    monkeypatch.setattr(settings, "bookmarks_max_per_user", 1)
    monkeypatch.setattr(
        "src.domains.bookmarks.service.safe_fire_and_forget",
        lambda coroutine, **kwargs: coroutine.close(),
    )
    async with maker() as session:
        user = User(
            email=f"bookmark-race-{marker}@example.test", is_active=True, hashed_password="x"
        )
        session.add(user)
        await session.flush()
        owner = user.id
        conversation = await _conversation(session, user)
        answers = [
            await _message(
                session, conversation, role="assistant", content=f"Answer {i}", minutes=i
            )
            for i in range(2)
        ]
        ids = [answer.id for answer in answers]
        await session.commit()

    async def keep(identity):
        async with maker() as session:
            try:
                await BookmarkService(session).keep(owner, identity)
                return "kept"
            except BookmarkLimitReachedError:
                await session.rollback()
                return "refused"

    assert sorted(await asyncio.gather(*(keep(identity) for identity in ids))) == [
        "kept",
        "refused",
    ]
