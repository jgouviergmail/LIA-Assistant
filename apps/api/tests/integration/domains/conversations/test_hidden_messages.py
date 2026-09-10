"""A run's rows are kept in full and left out of the chat (ADR-276).

The whole design rests on one asymmetry that only a server can prove: the rows
are THERE, and the chat read does not return them. A unit test over a compiled
statement says the SQL asks for it; this says the database answers it.

Why the rows exist at all rather than never being written: archive-first
(ADR-117) persists the question before the graph runs so a crash cannot lose
the turn, and the decision register (ADR-263, lot 6) points at the request and
the answer with ``SET NULL`` tombstones — a run that archived nothing would
leave a register row indistinguishable from a deleted conversation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.repository import ConversationRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
async def thread(async_session: AsyncSession) -> Conversation:
    """One conversation holding two visible turns and one hidden run."""
    from src.domains.users.models import User

    user = User(
        email="hidden_rows@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    async_session.add(user)
    await async_session.commit()

    conversation = Conversation(
        id=user.id, user_id=user.id, title="H", message_count=0, total_tokens=0
    )
    async_session.add(conversation)
    await async_session.commit()

    async_session.add_all(
        [
            ConversationMessage(
                conversation_id=conversation.id,
                role="user",
                content="Bonjour",
                created_at=NOW - timedelta(minutes=5),
            ),
            ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="Bonjour !",
                created_at=NOW - timedelta(minutes=4),
            ),
            ConversationMessage(
                conversation_id=conversation.id,
                role="user",
                content="Organise the party",
                hidden=True,
                message_metadata={"workboard": {"ticket_id": "t-1", "run_id": "r-1"}},
                created_at=NOW - timedelta(minutes=3),
            ),
            ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="The venue is booked.",
                hidden=True,
                message_metadata={"workboard": {"ticket_id": "t-1", "run_id": "r-1"}},
                created_at=NOW - timedelta(minutes=2),
            ),
        ]
    )
    await async_session.commit()
    return conversation


class TestTheChatDoesNotShowThem:
    async def test_the_history_returns_only_the_visible_turns(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        messages = await ConversationRepository(async_session).get_messages_for_conversation(
            thread.id, limit=50
        )
        assert sorted(message.content for message in messages) == ["Bonjour", "Bonjour !"]

    async def test_the_paginated_read_returns_only_the_visible_turns(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        rows = await ConversationRepository(async_session).get_messages_with_token_summaries(
            thread.id, limit=50
        )
        assert sorted(message.content for message, _tokens in rows) == [
            "Bonjour",
            "Bonjour !",
        ]

    async def test_the_last_user_message_skips_the_runs_question(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        """The run's synthetic question is the MOST RECENT user row; reading it
        as « what they last asked » would answer the ticket, not the person."""
        message = await ConversationRepository(async_session).get_last_user_message(thread.id)
        assert message is not None
        assert message.content == "Bonjour"

    async def test_the_eager_load_drops_them_too(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        conversation = await ConversationRepository(async_session).get_conversation_with_messages(
            thread.id, message_limit=50
        )
        assert conversation is not None
        assert sorted(message.content for message in conversation.messages) == [
            "Bonjour",
            "Bonjour !",
        ]


class TestTheRecordIsWhole:
    async def test_the_rows_are_really_there(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        """The point of the whole design: they were written, not skipped."""
        total = (
            await async_session.execute(
                select(func.count())
                .select_from(ConversationMessage)
                .where(ConversationMessage.conversation_id == thread.id)
            )
        ).scalar()
        assert total == 4

    async def test_a_reader_that_asks_for_everything_gets_everything(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        """What the export and the three registers do."""
        messages = await ConversationRepository(async_session).get_messages_for_conversation(
            thread.id, limit=50, include_hidden=True
        )
        assert len(messages) == 4

    async def test_they_carry_the_ticket_that_produced_them(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        """This is what lets a run's transcript be found from its ticket."""
        messages = await ConversationRepository(async_session).get_messages_for_conversation(
            thread.id, limit=50, include_hidden=True
        )
        hidden = [message for message in messages if message.hidden]
        assert len(hidden) == 2
        assert all(
            message.message_metadata["workboard"]["ticket_id"] == "t-1" for message in hidden
        )

    async def test_a_reset_removes_them_with_everything_else(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        """« Forget this conversation » must not leave a hidden remainder."""
        removed = await ConversationRepository(async_session).delete_messages_for_conversation(
            thread.id
        )
        await async_session.commit()
        assert removed == 4
        left = (
            await async_session.execute(
                select(func.count())
                .select_from(ConversationMessage)
                .where(ConversationMessage.conversation_id == thread.id)
            )
        ).scalar()
        assert left == 0


class TestTheColumnComesFromTheStamp:
    """The half that was missing, and that no read test could ever show.

    Measured 2026-09-09 on the dev instance: a real run archived both its rows
    with the workboard stamp in their metadata and ``hidden = false`` in the
    column, so the person's chat showed the synthetic brief and a duplicate
    answer — while the whole suite was green. The reads were right; nothing
    wrote the column, and the tests above INSERT ``hidden=True`` themselves, so
    they proved the filter and never the write.

    These two go through the write path the application actually uses.
    """

    async def test_a_stamped_run_writes_a_hidden_row(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        from src.domains.agents.api.run_origin import (
            RunOrigin,
            out_of_turn_origin_ctx,
            with_hidden_stamp,
        )

        token = out_of_turn_origin_ctx.set(
            RunOrigin(kind="workboard", ticket_id="t-9", run_id="r-9")
        )
        try:
            metadata = with_hidden_stamp({"run_id": "r-9"})
        finally:
            out_of_turn_origin_ctx.reset(token)

        repository = ConversationRepository(async_session)
        message = await repository.create_message(
            conversation_id=thread.id,
            role="assistant",
            content="The room is booked.",
            metadata=metadata,
        )
        await async_session.commit()

        assert message.hidden is True
        visible = await repository.get_messages_for_conversation(thread.id, limit=50)
        assert all(row.content != "The room is booked." for row in visible)

    async def test_an_ordinary_turn_writes_a_visible_row(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        """The other half of the same oracle: without it the test above would
        also pass on a repository that hides everything."""
        repository = ConversationRepository(async_session)
        message = await repository.create_message(
            conversation_id=thread.id,
            role="user",
            content="Et demain ?",
            metadata={"run_id": "r-10"},
        )
        await async_session.commit()

        assert message.hidden is False
        visible = await repository.get_messages_for_conversation(thread.id, limit=50)
        assert any(row.content == "Et demain ?" for row in visible)


class TestTheDefaultIsVisible:
    async def test_an_ordinary_message_is_not_hidden(
        self, async_session: AsyncSession, thread: Conversation
    ) -> None:
        """The server default decides for every row written by code that
        predates this column — including every row already in production."""
        message = ConversationMessage(
            conversation_id=thread.id, role="user", content="Encore une question"
        )
        async_session.add(message)
        await async_session.commit()
        # The id is read BEFORE expire_all(): expiring invalidates every loaded
        # object, and reading an attribute back would attempt IO outside the
        # greenlet the async session runs in.
        message_id = message.id
        async_session.expire_all()

        stored = await async_session.get(ConversationMessage, message_id)
        assert stored is not None
        assert stored.hidden is False
