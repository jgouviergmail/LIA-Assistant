"""Relations domain models — the personal CRM's persisted layer.

The CRM overview itself is a pure aggregation (open loops + calls + memories,
recomputed per request); the ONLY persisted state is the user's favorites:
a starred relationship must survive its live signals expiring, so the star
stores the display name it was given and the normalized identity key used to
match it back to the aggregation.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
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


class RelationAlias(BaseModel):
    """One relationship the user declared to be the SAME person as another.

    ``fold_name`` decides who is *literally* the same person — accents, case,
    spacing. It cannot know that "0612345678" and "alice vernier" are one
    relationship, or that "Papa" and "Jean Dupont" are. Only the user knows,
    so only the user may say it: merges are manual, never proposed.

    The table is kept FLAT: ``alias_key`` always points at the FINAL canonical
    key, never at another alias. Merging B into C therefore rewrites every row
    that pointed at B — path compression, done once at write time so every
    read stays a single lookup with no chain to walk and no cycle to detect.

    Reversible by construction: a merge is one row, and undoing it is deleting
    that row. Nothing is rewritten in the sources, which keep their own
    spellings — the CRM is a VIEW over them.
    """

    __tablename__ = "relation_aliases"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of the merge.",
    )
    alias_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Folded identity that was merged AWAY (fold_name).",
    )
    canonical_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Folded identity it now belongs to (fold_name). Never an alias itself.",
    )
    alias_display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Spelling the merged-away side was shown as, so the undo can name it.",
    )

    __table_args__ = (
        # One canonical per alias: merging a relationship twice is a
        # correction, not a second identity.
        UniqueConstraint("user_id", "alias_key", name="uq_relation_aliases_user_alias"),
        # Declared here as well as in the migration: an index that exists only
        # in the migration is one the next `--autogenerate` proposes to DROP,
        # and this one serves the read the overview performs on every request
        # (which spellings did this identity absorb?).
        Index("ix_relation_aliases_user_canonical", "user_id", "canonical_key"),
    )

    def __repr__(self) -> str:
        return f"<RelationAlias(user={self.user_id}, {self.alias_key!r}->{self.canonical_key!r})>"
