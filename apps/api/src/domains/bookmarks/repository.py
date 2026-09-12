"""Persistence of the answers a person kept (ADR-282).

Every read filters on the owner. The two reads over the MESSAGE table are
declared in ``conversations/message_readers.py`` as ``VISIBLE_ONLY``: a run's
rows are never shown, so they are never kept, and the request « before » an
answer is the person's last visible words, never a run's synthetic question.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.queries import BookmarkFilters, build_bookmarks_statement
from src.domains.conversations.message_reads import visible_only
from src.domains.conversations.models import Conversation, ConversationMessage


class BookmarkRepository(BaseRepository[MessageBookmark]):
    """Repository for :class:`MessageBookmark`.

    Args:
        db: Async session shared with the calling transaction.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, MessageBookmark)

    # ------------------------------------------------------------------
    # Reads over the message table (declared VISIBLE_ONLY)
    # ------------------------------------------------------------------

    async def owned_assistant_message(
        self, user_id: UUID, message_id: UUID
    ) -> ConversationMessage | None:
        """The visible assistant message the account owns, or ``None``.

        Args:
            user_id: The caller.
            message_id: The archived message the bubble carries.

        Returns:
            The row, or ``None`` when it is not the caller's, not the
            assistant's, or hidden — one answer for all three.
        """
        statement = visible_only(
            select(ConversationMessage)
            .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
            .where(
                ConversationMessage.id == message_id,
                ConversationMessage.role == "assistant",
                Conversation.user_id == user_id,
            ),
            include_hidden=False,
        )
        return (await self.db.execute(statement)).scalar_one_or_none()

    async def preceding_user_message(
        self, message: ConversationMessage
    ) -> ConversationMessage | None:
        """The last visible user message written before ``message``.

        Args:
            message: The assistant message being kept.

        Returns:
            The person's words that produced it, or ``None`` when nothing
            visible precedes it.
        """
        statement = (
            visible_only(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == message.conversation_id,
                    ConversationMessage.role == "user",
                    ConversationMessage.created_at <= message.created_at,
                    ConversationMessage.id != message.id,
                ),
                include_hidden=False,
            )
            .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
            .limit(1)
        )
        return (await self.db.execute(statement)).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Bookmarks
    # ------------------------------------------------------------------

    async def add(self, bookmark: MessageBookmark) -> MessageBookmark:
        """Stage one bookmark and give it its identity.

        Args:
            bookmark: The row to persist.

        Returns:
            The same row, flushed.
        """
        self.db.add(bookmark)
        await self.db.flush()
        return bookmark

    async def get_for_user(self, user_id: UUID, bookmark_id: UUID) -> MessageBookmark | None:
        """One bookmark, if the account owns it.

        Args:
            user_id: The caller.
            bookmark_id: The bookmark.

        Returns:
            The row, or ``None``.
        """
        statement = select(MessageBookmark).where(
            MessageBookmark.id == bookmark_id, MessageBookmark.user_id == user_id
        )
        return (await self.db.execute(statement)).scalar_one_or_none()

    async def get_by_message(self, user_id: UUID, message_id: UUID) -> MessageBookmark | None:
        """The bookmark taken from one message, if any.

        Args:
            user_id: The caller.
            message_id: The archived message.

        Returns:
            The row, or ``None``.
        """
        statement = select(MessageBookmark).where(
            MessageBookmark.user_id == user_id, MessageBookmark.message_id == message_id
        )
        return (await self.db.execute(statement)).scalar_one_or_none()

    async def count_for_user(self, user_id: UUID) -> int:
        """How many bookmarks the account keeps — the figure the cap reads.

        Args:
            user_id: The account.

        Returns:
            The exact count.
        """
        statement = build_bookmarks_statement(user_id, BookmarkFilters(), count=True)
        return int((await self.db.execute(statement)).scalar_one())

    async def list_page(
        self, user_id: UUID, filters: BookmarkFilters
    ) -> tuple[Sequence[MessageBookmark], int]:
        """One page and the EXACT total behind it (ADR-185).

        Args:
            user_id: Whose bookmarks.
            filters: What they are narrowed to.

        Returns:
            The rows of the page and the count over the whole filtered set —
            the same ``WHERE``, by construction.
        """
        rows = (await self.db.execute(build_bookmarks_statement(user_id, filters))).scalars().all()
        total = (
            await self.db.execute(build_bookmarks_statement(user_id, filters, count=True))
        ).scalar_one()
        return rows, int(total)

    async def attached_message_ids(self, user_id: UUID) -> dict[UUID, UUID]:
        """Every bookmark still attached to a message: ``message_id → bookmark_id``.

        Bounded by the cap, so one small payload tells every bubble its state.

        Args:
            user_id: The account.

        Returns:
            The map.
        """
        statement = select(MessageBookmark.message_id, MessageBookmark.id).where(
            MessageBookmark.user_id == user_id, MessageBookmark.message_id.is_not(None)
        )
        rows = (await self.db.execute(statement)).all()
        # The WHERE excludes NULL; the narrowing is spelled for the type checker.
        return {
            message_id: bookmark_id for message_id, bookmark_id in rows if message_id is not None
        }

    async def delete_by_message(self, user_id: UUID, message_id: UUID) -> bool:
        """Remove the bookmark taken from one message.

        Args:
            user_id: The caller.
            message_id: The archived message.

        Returns:
            True when a row went, False when there was none — the bubble's
            second click reports what actually happened.
        """
        statement = delete(MessageBookmark).where(
            MessageBookmark.user_id == user_id, MessageBookmark.message_id == message_id
        )
        result = await self.db.execute(statement)
        return bool(getattr(result, "rowcount", 0))
