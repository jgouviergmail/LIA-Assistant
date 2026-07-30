"""Relations domain models — the personal CRM's persisted layer.

The CRM overview itself is a pure aggregation (open loops + calls + memories,
recomputed per request); the ONLY persisted state is the user's favorites:
a starred relationship must survive its live signals expiring, so the star
stores the display name it was given and the normalized identity key used to
match it back to the aggregation.
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class RelationFavorite(BaseModel):
    """One starred relationship of one user.

    ``name_key`` is the accent/case-folded identity (``fold_name``) that the
    aggregation buckets are keyed on; ``display_name`` is the spelling the
    user starred, rendered when no live signal carries a better one.
    """

    __tablename__ = "relation_favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of the star.",
    )
    name_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Accent/case-folded relationship identity (fold_name).",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Spelling the user starred (fallback rendering).",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name_key", name="uq_relation_favorites_user_name"),
    )

    def __repr__(self) -> str:
        return f"<RelationFavorite(user={self.user_id}, key={self.name_key!r})>"
