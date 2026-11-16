"""The discussion an out-of-turn return runs in: the act's own while it lives, else Main.

A notification is published through ``OriginPublication``; a TURN run out of
turn (the relay of an owner call, a request delegated during a Live call)
needs a selection for its admission and a discussion for its rows. Both are
read here, once, from the act's origin: an ANNEX whose generation still lives
is selected by id and revision; anything else — no origin, Main, an annex
since reset or deleted — returns to Main, addressed by omission so that a
reset of Main between the act and its return refuses nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationOrigin
from src.domains.conversations.publication_repository import ConversationPublicationRepository
from src.domains.conversations.service import ConversationService
from src.infrastructure.database.conversation_origin import origin_columns


@dataclass(frozen=True, slots=True)
class ReturnTarget:
    """Where a return runs.

    Attributes:
        conversation_id: The annex, or Main.
        revision: The annex's generation; None for Main (selected by omission).
    """

    conversation_id: UUID
    revision: int | None

    @property
    def selection(self) -> ConversationSelection:
        """The admission's selection: the annex by its generation, Main by omission."""
        if self.revision is None:
            return ConversationSelection()
        return ConversationSelection(
            conversation_id=self.conversation_id, conversation_revision=self.revision
        )


async def return_target(
    db: AsyncSession, owner_id: UUID, origin: ConversationOrigin | None, *, language: str | None
) -> ReturnTarget:
    """Resolve where the return of an act runs, on the caller's short session.

    Args:
        db: A short session of the caller's (no wait is held on it).
        owner_id: The account the act belongs to.
        origin: Where the act began, or None.
        language: The account's language, should Main have to be created.

    Returns:
        The annex while its generation lives, else Main.
    """
    if origin is not None:
        annex = await ConversationPublicationRepository(db).secondary_origin(owner_id, origin)
        if annex is not None:
            return ReturnTarget(annex, origin.revision)
    main = await ConversationService().get_or_create_conversation(owner_id, db, language=language)
    return ReturnTarget(main.id, None)


async def origin_target(
    db: AsyncSession, owner_id: UUID, origin: ConversationOrigin | None, *, language: str | None
) -> ReturnTarget | None:
    """Where a run begun in a discussion answers; None for a run begun nowhere.

    A scheduled tick has no origin: it runs in Main by omission, and nothing
    is read for it.

    Args:
        db: A short session of the caller's (no wait is held on it).
        owner_id: The account the run belongs to.
        origin: Where the run was asked, or None.
        language: The account's language, should Main have to be created.

    Returns:
        The annex while its generation lives, Main otherwise, None without origin.
    """
    if origin is None:
        return None
    return await return_target(db, owner_id, origin, language=language)


def selection_of(target: ReturnTarget | None) -> ConversationSelection:
    """The selection a turn runs under: its target's, or Main by omission."""
    return target.selection if target is not None else ConversationSelection()


def annex_of(target: ReturnTarget | None) -> UUID | None:
    """The annex a return runs in, which its push opens; None for Main."""
    if target is None or target.revision is None:
        return None
    return target.conversation_id


async def annex_origin(
    db: AsyncSession, owner_id: UUID, conversation_id: UUID | None
) -> ConversationOrigin | None:
    """The origin an act begun from the browser records: the annex on screen, now.

    The act begins now, so the annex's CURRENT generation is the one it
    belongs to. Main, an unknown, deleted or foreign discussion never refuses
    the act: it has no origin, and its return goes to Main.

    Args:
        db: The caller's short session.
        owner_id: The account beginning the act.
        conversation_id: The discussion the browser showed, or None.

    Returns:
        The annex's origin, or None.
    """
    if conversation_id is None:
        return None
    revision = await ConversationPublicationRepository(db).live_annex_revision(
        owner_id, conversation_id
    )
    return ConversationOrigin(conversation_id, revision) if revision is not None else None


async def annex_origin_columns(
    db: AsyncSession, owner_id: UUID, conversation_id: UUID | None
) -> dict[str, UUID | int | None]:
    """The origin columns of an act begun from the browser: the annex it showed, or none.

    Args:
        db: The caller's short session.
        owner_id: The account beginning the act.
        conversation_id: The discussion the browser showed, or None.

    Returns:
        ``origin_conversation_id`` and ``origin_conversation_revision``.
    """
    return origin_columns(await annex_origin(db, owner_id, conversation_id))


__all__ = [
    "ReturnTarget",
    "annex_of",
    "annex_origin",
    "annex_origin_columns",
    "origin_target",
    "return_target",
    "selection_of",
]
