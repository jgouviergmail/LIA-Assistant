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
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.queries import BookmarkFilters
from src.domains.bookmarks.repository import BookmarkRepository
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentSourceType,
    RAGDocumentStatus,
    RAGSpace,
)
from src.domains.rag_spaces.repository import RAGSpaceRepository
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


async def _space(db: AsyncSession, user: User) -> RAGSpace:
    space = RAGSpace(user_id=user.id, name=f"kept-{uuid.uuid4().hex[:6]}", kind="bookmarks")
    db.add(space)
    await db.flush()
    return space


async def _document(db: AsyncSession, user: User, space: RAGSpace, status: str) -> RAGDocument:
    document = RAGDocument(
        space_id=space.id,
        user_id=user.id,
        filename=f"{uuid.uuid4().hex}.md",
        original_filename="Kept answer 2026-09-12.md",
        file_size=12,
        content_type="text/markdown",
        status=status,
        source_type=RAGDocumentSourceType.BOOKMARK,
        embedding_tokens=42,
        embedding_cost_eur=0.00001,
        embedding_model="gemini-embedding-001",
    )
    db.add(document)
    await db.flush()
    return document


class TestTheKnowledgeSpaceProjection:
    """The projection columns and the sweep's reads (2026-09-16 design, part A)."""

    async def test_losing_the_document_never_loses_the_bookmark(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        space = await _space(async_session, user)
        document = await _document(async_session, user, space, RAGDocumentStatus.READY)
        kept = await _bookmark(async_session, user, None)
        repository = BookmarkRepository(async_session)
        await repository.set_index_state(
            kept.id, state="indexed", rag_document_id=document.id, indexed_at=NOW
        )

        await async_session.execute(delete(RAGDocument).where(RAGDocument.id == document.id))
        await async_session.refresh(kept)

        assert kept.rag_document_id is None
        assert kept.content == "**Réservé**"
        # And the sweep re-projects it rather than trusting a stale « indexed ».
        assert kept.id in await repository.unprojected_ids(limit=10, grace_seconds=60)

    async def test_the_claim_is_taken_once_and_a_dead_claim_is_taken_over(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        kept = await _bookmark(async_session, user, None)
        repository = BookmarkRepository(async_session)

        assert await repository.claim_for_projection(kept.id, grace_seconds=3600) is True
        assert await repository.claim_for_projection(kept.id, grace_seconds=3600) is False
        # A claim older than the grace is a crashed one: taken over.
        assert await repository.claim_for_projection(kept.id, grace_seconds=0) is True

    async def test_a_projected_bookmark_cannot_be_claimed_again(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        space = await _space(async_session, user)
        document = await _document(async_session, user, space, RAGDocumentStatus.PENDING)
        kept = await _bookmark(async_session, user, None)
        repository = BookmarkRepository(async_session)
        await repository.set_index_state(
            kept.id, state="pending", rag_document_id=document.id, indexed_at=None
        )

        assert await repository.claim_for_projection(kept.id, grace_seconds=0) is False
        assert kept.id not in await repository.unprojected_ids(limit=10, grace_seconds=0)

    async def test_the_sweep_retries_deferred_and_disabled_but_never_error(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        repository = BookmarkRepository(async_session)
        rows = {
            state: await _bookmark(
                async_session, user, None, answered_at=NOW + timedelta(minutes=i)
            )
            for i, state in enumerate(("deferred", "disabled", "error", "pending"))
        }
        for state, row in rows.items():
            await repository.set_index_state(row.id, state=state)
        never = await _bookmark(async_session, user, None)

        ids = await repository.unprojected_ids(limit=10, grace_seconds=3600)

        assert rows["deferred"].id in ids and rows["disabled"].id in ids and never.id in ids
        assert rows["error"].id not in ids
        # A fresh pending claim is somebody else's work.
        assert rows["pending"].id not in ids

    async def test_a_name_clash_with_a_hand_made_space_still_projects(
        self,
        async_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """The person named a space exactly like the managed one; the projection suffixes.

        Real PostgreSQL only: the clash is a unique-index violation, and the
        rollback it forces EXPIRES every row loaded in that session — a stub
        session never does, so a unit test cannot see the bookmark being
        re-read after the rollback.
        """
        from collections.abc import AsyncIterator
        from contextlib import asynccontextmanager

        from src.core.i18n_bookmarks import get_space_name
        from src.domains.bookmarks import indexing
        from src.domains.rag_spaces import document_access, drive_ingest

        # The name's uniqueness is a PARTIAL index the migrations own and
        # ``create_all`` does not build: declared here, exactly as in production,
        # inside the test's transaction (DDL is transactional on PostgreSQL).
        await async_session.execute(
            text(
                "CREATE UNIQUE INDEX uq_rag_spaces_user_name ON rag_spaces (user_id, name) "
                "WHERE user_id IS NOT NULL"
            )
        )
        user = await _user(async_session)
        hand_made = RAGSpace(user_id=user.id, name=get_space_name(user.language), kind=None)
        async_session.add(hand_made)
        await async_session.flush()
        kept = await _bookmark(async_session, user, None)

        @asynccontextmanager
        async def _ctx() -> AsyncIterator[AsyncSession]:
            yield async_session

        async def _allowed(*_: object) -> bool:
            return True

        async def _not_blocked(*_: object) -> bool:
            return False

        monkeypatch.setattr(indexing, "get_db_context", _ctx)
        monkeypatch.setattr(indexing, "is_capability_enabled", _allowed)
        monkeypatch.setattr(indexing, "spend_blocked", _not_blocked)
        monkeypatch.setattr(drive_ingest.settings, "rag_spaces_storage_path", str(tmp_path))
        monkeypatch.setattr(document_access.settings, "rag_spaces_storage_path", str(tmp_path))

        # Plain values: the rollback the clash forces expires the rows above too.
        user_id, hand_made_id, hand_made_name = user.id, hand_made.id, hand_made.name

        kwargs = await indexing._prepare(kept.id)

        assert kwargs is not None
        await async_session.refresh(kept)
        managed = await RAGSpaceRepository(async_session).get_by_kind_for_user(user_id, "bookmarks")
        assert managed is not None and managed.id != hand_made_id
        assert managed.name == f"{hand_made_name} (2)"
        assert kept.index_state == "pending" and kept.rag_document_id == kwargs["document_id"]
        document = await async_session.get(RAGDocument, kwargs["document_id"])
        assert document is not None and document.space_id == managed.id

    async def test_the_link_says_whether_the_bookmark_still_exists(
        self, async_session: AsyncSession
    ) -> None:
        """``rowcount`` on real PostgreSQL: 1 for a live row, 0 for a vanished one."""
        user = await _user(async_session)
        kept = await _bookmark(async_session, user, None)
        repository = BookmarkRepository(async_session)

        assert await repository.set_index_state(kept.id, state="pending") == 1
        assert await repository.set_index_state(uuid.uuid4(), state="pending") == 0

    async def test_the_sweep_serves_the_least_recently_attempted_row_first(
        self, async_session: AsyncSession
    ) -> None:
        """A refused attempt goes to the BACK of the queue.

        Ordered by creation, the oldest rows of one account under quota would
        fill every batch for as long as the quota held, and a younger bookmark
        of another account would never be reached — measured shape: batch 25,
        one account with 30 deferred rows, everybody else starved.
        """
        user = await _user(async_session)
        older = await _bookmark(async_session, user, None, answered_at=NOW)
        younger = await _bookmark(async_session, user, None, answered_at=NOW + timedelta(hours=1))
        repository = BookmarkRepository(async_session)
        # The older row was just attempted and refused (its updated_at is now).
        await repository.set_index_state(older.id, state="deferred")

        assert await repository.unprojected_ids(limit=1, grace_seconds=60) == [younger.id]
        assert await repository.unprojected_ids(limit=2, grace_seconds=60) == [
            younger.id,
            older.id,
        ]

    async def test_a_page_reads_its_documents_in_one_query(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        space = await _space(async_session, user)
        document = await _document(async_session, user, space, RAGDocumentStatus.READY)
        projected = await _bookmark(async_session, user, None)
        bare = await _bookmark(async_session, user, None)
        repository = BookmarkRepository(async_session)
        await repository.set_index_state(
            projected.id, state="indexed", rag_document_id=document.id, indexed_at=NOW
        )
        await async_session.refresh(projected)

        documents = await repository.documents_of([projected, bare])

        assert set(documents) == {document.id}
        assert documents[document.id].embedding_tokens == 42
