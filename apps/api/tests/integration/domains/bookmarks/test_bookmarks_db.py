"""The bookmark table and its reads against REAL PostgreSQL (ADR-282).

Four properties of the design belong to the database and to nothing else, so a
unit test over a stub proves none of them:

- **deleting the conversation leaves the bookmark whole** — the two references
  go ``NULL``, the copied answer and request stay (the whole point);
- **deleting the account takes its bookmarks** — ``CASCADE`` on ``user_id``;
- **one bookmark per message per account** — the PARTIAL unique index, which
  also lets two detached bookmarks (message gone) coexist;
- **the request is the last VISIBLE user message before the answer** — a
  hidden run's rows are never it, and another account's message is never
  found.

Everything runs inside the ``async_session`` fixture's transaction: nothing
persists.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.queries import BookmarkFilters
from src.domains.bookmarks.repository import BookmarkRepository
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


async def _user(db: AsyncSession) -> User:
    user = User(
        email=f"bookmarks_{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    return user


async def _conversation(db: AsyncSession, user: User) -> Conversation:
    conversation = Conversation(user_id=user.id, title="B", message_count=0, total_tokens=0)
    db.add(conversation)
    await db.flush()
    return conversation


async def _message(
    db: AsyncSession,
    conversation: Conversation,
    *,
    role: str,
    content: str,
    minutes: int,
    hidden: bool = False,
) -> ConversationMessage:
    row = ConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        hidden=hidden,
        created_at=NOW + timedelta(minutes=minutes),
    )
    db.add(row)
    await db.flush()
    return row


async def _bookmark(
    db: AsyncSession,
    user: User,
    message: ConversationMessage | None,
    *,
    content: str = "**Réservé**",
    request_content: str | None = "Réserve la salle",
    answered_at: datetime = NOW,
) -> MessageBookmark:
    row = MessageBookmark(
        user_id=user.id,
        message_id=message.id if message is not None else None,
        conversation_id=message.conversation_id if message is not None else None,
        content=content,
        request_content=request_content,
        answered_at=answered_at,
    )
    db.add(row)
    await db.flush()
    return row


class TestABookmarkSurvivesItsConversation:
    async def test_deleting_the_conversation_detaches_but_keeps_the_copy(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        conversation = await _conversation(async_session, user)
        answer = await _message(
            async_session, conversation, role="assistant", content="A", minutes=1
        )
        kept = await _bookmark(async_session, user, answer, content="A copy", request_content="Q")

        await async_session.execute(delete(Conversation).where(Conversation.id == conversation.id))
        # Re-read the row explicitly: an expired instance would lazy-load on
        # attribute access, which is sync IO under an async session.
        await async_session.refresh(kept)

        assert kept.message_id is None
        assert kept.conversation_id is None
        assert kept.content == "A copy"
        assert kept.request_content == "Q"

    async def test_deleting_the_account_takes_its_bookmarks(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        conversation = await _conversation(async_session, user)
        answer = await _message(
            async_session, conversation, role="assistant", content="A", minutes=1
        )
        kept = await _bookmark(async_session, user, answer)

        await async_session.execute(delete(User).where(User.id == user.id))

        remaining = (
            await async_session.execute(
                select(MessageBookmark.id).where(MessageBookmark.id == kept.id)
            )
        ).scalar_one_or_none()
        assert remaining is None


class TestOneBookmarkPerMessage:
    async def test_the_same_message_cannot_be_kept_twice_by_one_account(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        conversation = await _conversation(async_session, user)
        answer = await _message(
            async_session, conversation, role="assistant", content="A", minutes=1
        )
        await _bookmark(async_session, user, answer)

        with pytest.raises(IntegrityError):
            await _bookmark(async_session, user, answer)
        await async_session.rollback()

    async def test_two_detached_bookmarks_coexist(self, async_session: AsyncSession) -> None:
        # The index is PARTIAL: a NULL message_id is nobody's identity.
        user = await _user(async_session)
        await _bookmark(async_session, user, None, content="one")
        await _bookmark(async_session, user, None, content="two")

        rows, total = await BookmarkRepository(async_session).list_page(user.id, BookmarkFilters())
        assert total == 2
        assert {row.content for row in rows} == {"one", "two"}


class TestTheReadsOverTheMessageTable:
    async def test_the_request_is_the_last_visible_user_message_before_the_answer(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        conversation = await _conversation(async_session, user)
        await _message(async_session, conversation, role="user", content="older", minutes=0)
        await _message(async_session, conversation, role="user", content="the one", minutes=1)
        # A hidden run's synthetic question, written between the two — never
        # the person's words.
        await _message(
            async_session, conversation, role="user", content="run", minutes=2, hidden=True
        )
        answer = await _message(
            async_session, conversation, role="assistant", content="A", minutes=3
        )
        await _message(async_session, conversation, role="user", content="later", minutes=4)

        repository = BookmarkRepository(async_session)
        found = await repository.owned_assistant_message(user.id, answer.id)
        assert found is not None and found.id == answer.id

        request = await repository.preceding_user_message(found)
        assert request is not None and request.content == "the one"

    async def test_a_hidden_or_foreign_or_user_message_is_never_found(
        self, async_session: AsyncSession
    ) -> None:
        user, other = await _user(async_session), await _user(async_session)
        conversation = await _conversation(async_session, user)
        hidden = await _message(
            async_session, conversation, role="assistant", content="H", minutes=1, hidden=True
        )
        question = await _message(async_session, conversation, role="user", content="Q", minutes=2)
        answer = await _message(
            async_session, conversation, role="assistant", content="A", minutes=3
        )

        repository = BookmarkRepository(async_session)
        assert await repository.owned_assistant_message(user.id, hidden.id) is None
        assert await repository.owned_assistant_message(user.id, question.id) is None
        assert await repository.owned_assistant_message(other.id, answer.id) is None


class TestTheListing:
    async def test_newest_answer_first_and_the_total_is_exact(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        for index in range(3):
            await _bookmark(
                async_session,
                user,
                None,
                content=f"answer {index}",
                answered_at=NOW + timedelta(minutes=index),
            )
        repository = BookmarkRepository(async_session)

        rows, total = await repository.list_page(user.id, BookmarkFilters(limit=2))

        assert total == 3
        assert [row.content for row in rows] == ["answer 2", "answer 1"]

    async def test_the_search_reads_the_request_too_and_escapes_its_needle(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        await _bookmark(async_session, user, None, content="x", request_content="salle_B")
        await _bookmark(async_session, user, None, content="y", request_content="salleXB")
        repository = BookmarkRepository(async_session)

        rows, total = await repository.list_page(user.id, BookmarkFilters(query="salle_B"))

        assert total == 1
        assert rows[0].request_content == "salle_B"

    async def test_the_state_maps_attached_messages_only(self, async_session: AsyncSession) -> None:
        user = await _user(async_session)
        conversation = await _conversation(async_session, user)
        answer = await _message(
            async_session, conversation, role="assistant", content="A", minutes=1
        )
        attached = await _bookmark(async_session, user, answer)
        await _bookmark(async_session, user, None)

        state = await BookmarkRepository(async_session).attached_message_ids(user.id)

        assert state == {answer.id: attached.id}

    async def test_delete_by_message_reports_what_went(self, async_session: AsyncSession) -> None:
        user = await _user(async_session)
        conversation = await _conversation(async_session, user)
        answer = await _message(
            async_session, conversation, role="assistant", content="A", minutes=1
        )
        await _bookmark(async_session, user, answer)
        repository = BookmarkRepository(async_session)

        assert await repository.delete_by_message(user.id, answer.id) is True
        assert await repository.delete_by_message(user.id, answer.id) is False
