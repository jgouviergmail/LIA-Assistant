"""The discussion generation an act was begun in, kept on the act's own row.

ADR-378 amendment 2026-11-14: the return of an act a person began in a
discussion — a call, an imported meeting, a message to a peer — comes back to
that discussion while the generation that began it lives (not deleted, not
reset since), and to Main otherwise. The act's row keeps the pair; the
publication (``conversations.publication_repository``) decides at the moment
of the return. No ``CHECK`` binds the two columns: the foreign-key action
nulls the id alone, and a constraint spanning both would refuse it (ADR-276).
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from src.core.conversation_target import ConversationOrigin

#: The SQL comments, mirrored word for word by the migration (replay check).
ORIGIN_ID_COMMENT = (
    "The discussion the act was begun in; its return comes back there while the "
    "generation lives (ADR-378). NULL: begun outside any discussion, or before 2026-11-14."
)
ORIGIN_REVISION_COMMENT = "The generation of that discussion when the act was begun."


class ConversationOriginMixin:
    """Two nullable columns naming where an act began, and their reading."""

    @declared_attr
    def origin_conversation_id(cls) -> Mapped[uuid.UUID | None]:
        """The discussion the act was begun in (``SET NULL`` when it is purged).

        Indexed: a purged discussion nulls its references through this column
        on each act table (migration ``7fb09b785088``).
        """
        return mapped_column(
            ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
            comment=ORIGIN_ID_COMMENT,
        )

    @declared_attr
    def origin_conversation_revision(cls) -> Mapped[int | None]:
        """The generation of that discussion when the act was begun."""
        return mapped_column(BigInteger, nullable=True, comment=ORIGIN_REVISION_COMMENT)

    @property
    def origin(self) -> ConversationOrigin | None:
        """The act's origin, or None when it began nowhere (or before it was kept)."""
        if self.origin_conversation_id is None or self.origin_conversation_revision is None:
            return None
        return ConversationOrigin(self.origin_conversation_id, self.origin_conversation_revision)

    def keep_origin(self, origin: ConversationOrigin | None) -> None:
        """Record where the act began (None: nowhere — its return goes to Main)."""
        self.origin_conversation_id = origin.conversation_id if origin else None
        self.origin_conversation_revision = origin.revision if origin else None


def origin_columns(origin: ConversationOrigin | None) -> dict[str, uuid.UUID | int | None]:
    """The two column values of an origin, for a row built from a mapping.

    Args:
        origin: Where the act began, or None for nowhere.

    Returns:
        ``origin_conversation_id`` and ``origin_conversation_revision``.
    """
    return {
        "origin_conversation_id": origin.conversation_id if origin else None,
        "origin_conversation_revision": origin.revision if origin else None,
    }
