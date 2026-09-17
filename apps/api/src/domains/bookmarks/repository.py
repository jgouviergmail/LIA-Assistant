"""Persistence of the answers a person kept (ADR-282).

Every read filters on the owner. The two reads over the MESSAGE table are
declared in ``conversations/message_readers.py`` as ``VISIBLE_ONLY``: a run's
rows are never shown, so they are never kept, and the request « before » an
answer is the person's last visible words, never a run's synthetic question.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.bookmarks.models import BookmarkIndexState, MessageBookmark
from src.domains.bookmarks.queries import BookmarkFilters, build_bookmarks_statement
from src.domains.conversations.message_reads import visible_only
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.rag_spaces.models import RAGDocument


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

    # ------------------------------------------------------------------
    # Knowledge-space projection (2026-09-16 design, part A)
    # ------------------------------------------------------------------

    @staticmethod
    def _stale_pending_before(grace_seconds: int) -> datetime:
        """The instant before which a ``pending`` claim is a dead one."""
        return datetime.now(UTC) - timedelta(seconds=grace_seconds)

    async def claim_for_projection(self, bookmark_id: UUID, *, grace_seconds: int) -> bool:
        """Take the right to project one bookmark — ONE conditional UPDATE.

        A click schedules a projection and the sweep may select the same row
        before the click's projection created its document; without a claim
        both would, and one document would be orphaned. The claim succeeds
        when the bookmark has no document AND is not being projected by a
        LIVE holder: a ``pending`` older than ``grace_seconds`` is a crashed
        claim and may be taken over.

        Args:
            bookmark_id: The bookmark.
            grace_seconds: How long a ``pending`` claim is trusted.

        Returns:
            True when this caller now holds the projection.
        """
        statement = (
            update(MessageBookmark)
            .where(
                MessageBookmark.id == bookmark_id,
                MessageBookmark.rag_document_id.is_(None),
                or_(
                    MessageBookmark.index_state.is_(None),
                    MessageBookmark.index_state != BookmarkIndexState.PENDING.value,
                    MessageBookmark.updated_at < self._stale_pending_before(grace_seconds),
                ),
            )
            .values(index_state=BookmarkIndexState.PENDING.value, updated_at=datetime.now(UTC))
        )
        result = await self.db.execute(statement)
        return bool(getattr(result, "rowcount", 0))

    async def set_index_state(
        self,
        bookmark_id: UUID,
        *,
        state: str,
        rag_document_id: UUID | None = None,
        indexed_at: datetime | None = None,
    ) -> int:
        """Write the projection's state (and, when given, its document link).

        ``rag_document_id`` is written only when passed: the settle after
        processing must not clear the link the projection wrote.

        Args:
            bookmark_id: The bookmark.
            state: A ``BookmarkIndexState`` value.
            rag_document_id: The document, when the projection created one.
            indexed_at: When READY was reached, on success.

        Returns:
            The rows written — 0 when the bookmark no longer exists, which the
            projection reads as « take the document back ».
        """
        values: dict[str, object] = {
            "index_state": state,
            "indexed_at": indexed_at,
            "updated_at": datetime.now(UTC),
        }
        if rag_document_id is not None:
            values["rag_document_id"] = rag_document_id
        result = await self.db.execute(
            update(MessageBookmark).where(MessageBookmark.id == bookmark_id).values(**values)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def unprojected_ids(self, *, limit: int, grace_seconds: int) -> list[UUID]:
        """Bookmarks with no projection the sweep may (re)attempt, least recently attempted first.

        Never attempted, ``deferred``, ``disabled``, ``indexed`` with the
        document gone (a ``SET NULL`` nobody foresaw is re-projected rather
        than trusted), or a ``pending`` older than ``grace_seconds`` (a crashed
        claim). ``error`` is NOT retried: the pipeline dead-lettered it and the
        state is shown honestly; keeping the answer again re-projects it.

        Args:
            limit: Batch bound.
            grace_seconds: How long a ``pending`` claim is trusted.

        The order is ``updated_at`` — every write of a state stamps it — so a
        refused attempt goes to the BACK of the queue and a row never
        attempted is served before any row is retried: ordered by creation,
        one account under quota would fill every batch with its oldest
        ``deferred`` rows for as long as the quota held.

        Returns:
            The ids, least recently attempted first.
        """
        retriable = (
            BookmarkIndexState.DEFERRED.value,
            BookmarkIndexState.DISABLED.value,
            BookmarkIndexState.INDEXED.value,
        )
        statement = (
            select(MessageBookmark.id)
            .where(
                MessageBookmark.rag_document_id.is_(None),
                or_(
                    MessageBookmark.index_state.is_(None),
                    MessageBookmark.index_state.in_(retriable),
                    (MessageBookmark.index_state == BookmarkIndexState.PENDING.value)
                    & (MessageBookmark.updated_at < self._stale_pending_before(grace_seconds)),
                ),
            )
            .order_by(MessageBookmark.updated_at.asc(), MessageBookmark.id.asc())
            .limit(limit)
        )
        return list((await self.db.execute(statement)).scalars().all())

    async def documents_of(self, bookmarks: Iterable[MessageBookmark]) -> dict[UUID, RAGDocument]:
        """The projection rows of a page, in ONE query — ``document_id → row``.

        Args:
            bookmarks: The page.

        Returns:
            The documents still linked, keyed by their id.
        """
        ids = [row.rag_document_id for row in bookmarks if row.rag_document_id is not None]
        if not ids:
            return {}
        rows = (await self.db.execute(select(RAGDocument).where(RAGDocument.id.in_(ids)))).scalars()
        return {document.id: document for document in rows}
