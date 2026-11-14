"""PostgreSQL proves cardinality and identity constraints, including deleted rows."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_target import ConversationKind
from src.domains.conversations.models import Conversation
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    """Own one account in the fixture's external rollback transaction."""
    user = User(email=f"conversations-{uuid4()}@example.test", hashed_password="unused")
    async_session.add(user)
    await async_session.flush()
    return user


async def test_an_account_can_keep_main_and_two_independent_annexes(
    async_session: AsyncSession, owner: User
) -> None:
    main = Conversation(id=owner.id, user_id=owner.id, runtime_id=owner.id)
    annexes = [
        Conversation(user_id=owner.id, title=title, kind=ConversationKind.SECONDARY)
        for title in ("Trip", "Reading")
    ]
    async_session.add_all([main, *annexes])
    await async_session.flush()
    rows = list(
        await async_session.scalars(select(Conversation).where(Conversation.user_id == owner.id))
    )
    assert {row.id for row in rows} == {main.id, *(row.id for row in annexes)}
    assert len({row.runtime_id for row in rows}) == 3
    assert main.runtime_id == main.id == owner.id


@pytest.mark.parametrize("retired", [False, True])
async def test_a_main_cannot_be_duplicated_even_when_legacy_soft_deleted(
    async_session: AsyncSession, owner: User, retired: bool
) -> None:
    async_session.add(
        Conversation(
            id=owner.id,
            user_id=owner.id,
            deleted_at=datetime.now(UTC) if retired else None,
        )
    )
    await async_session.flush()
    with pytest.raises(IntegrityError, match="uq_conversations_primary_user"):
        async with async_session.begin_nested():
            async_session.add(Conversation(user_id=owner.id, title="Another main"))
            await async_session.flush()


@pytest.mark.parametrize("title", [None, "", " ", "\t\r\n", "\u00a0\u3000"])
async def test_an_annex_needs_a_nonblank_title_at_the_database_boundary(
    async_session: AsyncSession, owner: User, title: str | None
) -> None:
    with pytest.raises(IntegrityError, match="ck_conversations_secondary_title"):
        async with async_session.begin_nested():
            async_session.add(
                Conversation(user_id=owner.id, title=title, kind=ConversationKind.SECONDARY)
            )
            await async_session.flush()


async def test_a_revision_cannot_be_negative(async_session: AsyncSession, owner: User) -> None:
    with pytest.raises(IntegrityError, match="ck_conversations_revision"):
        async with async_session.begin_nested():
            async_session.add(Conversation(user_id=owner.id, revision=-1))
            await async_session.flush()
