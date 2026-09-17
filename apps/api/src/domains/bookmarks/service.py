"""Keeping an answer, listing what was kept, letting it go (ADR-282).

A bookmark is a COPY taken at the click — the answer, the request that
produced it, the answer's date — so it survives the conversation. The service
owns the four refusals (not the caller's, nothing to keep, the cap, unknown
id) and the one idempotence the bubble's toggle relies on.

Since the 2026-09-16 design (part A) a kept answer is also PROJECTED into the
person's « Kept answers » knowledge space: the projection is scheduled after
the commit that created the row, and discarded inside the transaction that
removes it (``bookmarks/indexing.py``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import PROACTIVE_MESSAGE_TYPE_PREFIX
from src.domains.bookmarks.errors import (
    raise_bookmark_limit_reached,
    raise_bookmark_not_found,
    raise_bookmark_nothing_to_keep,
)
from src.domains.bookmarks.indexing import discard_index, index_bookmark, unlink_quietly
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.queries import BookmarkFilters
from src.domains.bookmarks.repository import BookmarkRepository
from src.domains.conversations.models import ConversationMessage
from src.infrastructure.async_utils import safe_fire_and_forget

if TYPE_CHECKING:
    from src.domains.rag_spaces.models import RAGDocument

logger = structlog.get_logger(__name__)


def _answers_no_request(message: ConversationMessage) -> bool:
    """Whether the message is a notification LIA sent on its own initiative.

    The person's last words before a notification did not produce it, so a
    bookmark of it keeps no request rather than a wrong one.

    Args:
        message: The assistant message being kept.

    Returns:
        True for a ``proactive_*`` archived type.
    """
    kind = (message.message_metadata or {}).get("type", "")
    return isinstance(kind, str) and kind.startswith(PROACTIVE_MESSAGE_TYPE_PREFIX)


class BookmarkService:
    """Service for the answers a person keeps.

    Args:
        db: Async session; the service commits its own writes.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = BookmarkRepository(db)

    async def keep(
        self, user_id: UUID, message_id: UUID, *, language: str = "en"
    ) -> tuple[MessageBookmark, bool]:
        """Keep one assistant answer.

        Idempotent: the toggle asks for a STATE, so a message already kept
        returns its bookmark — even at the cap, which bounds new rows only.

        Args:
            user_id: The caller.
            message_id: The archived assistant message the bubble carries.
            language: The caller's language, for the translated refusals.

        Returns:
            The bookmark, and whether this call created it.

        Raises:
            ResourceNotFoundError: The message is not the caller's, not the
                assistant's, or hidden — one answer for all three.
            ValidationError: The answer carries no text.
            BookmarkLimitReachedError: The account keeps as many as it may.
        """
        existing = await self.repository.get_by_message(user_id, message_id)
        if existing is not None:
            return existing, False

        message = await self.repository.owned_assistant_message(user_id, message_id)
        if message is None:
            raise_bookmark_not_found(message_id)
        if not (message.content or "").strip():
            raise_bookmark_nothing_to_keep(language)

        cap = settings.bookmarks_max_per_user
        if await self.repository.count_for_user(user_id) >= cap:
            raise_bookmark_limit_reached(cap, language)

        request = (
            None
            if _answers_no_request(message)
            else (await self.repository.preceding_user_message(message))
        )
        try:
            bookmark = await self.repository.add(
                MessageBookmark(
                    user_id=user_id,
                    message_id=message.id,
                    conversation_id=message.conversation_id,
                    content=message.content,
                    request_content=request.content if request is not None else None,
                    answered_at=message.created_at,
                )
            )
            await self.db.commit()
        except IntegrityError:
            # Two clicks in flight for one message: the partial unique index
            # let exactly one row through, and the toggle asked for a state —
            # the row the other click wrote IS that state.
            await self.db.rollback()
            existing = await self.repository.get_by_message(user_id, message_id)
            if existing is None:
                raise
            return existing, False
        logger.info(
            "bookmark_kept",
            user_id=str(user_id),
            bookmark_id=str(bookmark.id),
            message_id=str(message.id),
            has_request=request is not None,
        )
        # The projection rides the commit that created the row — a bookmark
        # that already existed was projected when it was kept.
        safe_fire_and_forget(index_bookmark(bookmark.id), name=f"bookmark_index_{bookmark.id}")
        return bookmark, True

    async def list_page(
        self, user_id: UUID, filters: BookmarkFilters
    ) -> tuple[Sequence[MessageBookmark], int]:
        """One page of the account's bookmarks and the exact total behind it.

        Args:
            user_id: Whose bookmarks.
            filters: What they are narrowed to.

        Returns:
            The rows and the count over the whole filtered set.
        """
        return await self.repository.list_page(user_id, filters)

    async def documents_of(self, bookmarks: Sequence[MessageBookmark]) -> dict[UUID, RAGDocument]:
        """The projection rows of a page — ONE query, keyed by document id.

        Args:
            bookmarks: The rows a response describes.

        Returns:
            ``document_id → rag_documents row`` for the links that resolve.
        """
        return await self.repository.documents_of(bookmarks)

    async def attached_message_ids(self, user_id: UUID) -> dict[UUID, UUID]:
        """What every bubble needs to draw its toggle: ``message_id → bookmark_id``.

        Args:
            user_id: The account.

        Returns:
            The map, for bookmarks still attached to a message.
        """
        return await self.repository.attached_message_ids(user_id)

    async def remove(self, user_id: UUID, bookmark_id: UUID) -> None:
        """Delete one bookmark the account owns.

        Args:
            user_id: The caller.
            bookmark_id: The bookmark.

        Raises:
            ResourceNotFoundError: Unknown, or somebody else's.
        """
        bookmark = await self.repository.get_for_user(user_id, bookmark_id)
        if bookmark is None:
            raise_bookmark_not_found(bookmark_id)
        await self._delete_with_projection(bookmark)
        logger.info("bookmark_removed", user_id=str(user_id), bookmark_id=str(bookmark_id))

    async def remove_by_message(self, user_id: UUID, message_id: UUID) -> bool:
        """The bubble's second click: drop the bookmark taken from one message.

        Args:
            user_id: The caller.
            message_id: The archived message.

        Returns:
            True when a bookmark went, False when none was attached — the
            caller reports what happened rather than assuming.
        """
        bookmark = await self.repository.get_by_message(user_id, message_id)
        if bookmark is None:
            return False
        await self._delete_with_projection(bookmark)
        logger.info("bookmark_removed_by_message", user_id=str(user_id), message_id=str(message_id))
        return True

    async def _delete_with_projection(self, bookmark: MessageBookmark) -> None:
        """Delete the projection and the row in ONE commit, then the stored file.

        The chunks and the document row go in the same transaction as the
        bookmark; the file goes after the commit, best effort — a stale file is
        harmless and the storage tree goes with the account.

        Args:
            bookmark: The row to remove.
        """
        path = await discard_index(self.db, bookmark)
        await self.repository.delete(bookmark)
        await self.db.commit()
        await asyncio.to_thread(unlink_quietly, path)
