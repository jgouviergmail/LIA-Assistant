"""Owner-scoped context, semantic evidence links and content-free forgetting markers."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class ContextStateRecord(BaseModel):
    """One account's context state: generation, last purge, pending rebuild, caches.

    ``generation`` moves with every change of the derived context; ``forgotten_at``
    is the last whole purge; ``refresh_requested`` a rebuild the person asked for;
    ``coverage``, ``rule_cache`` and ``ready_context`` cache what a run may reuse.
    """

    __tablename__ = "discussion_context_states"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    forgotten_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    coverage: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    rule_cache: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    ready_context: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    __table_args__ = (CheckConstraint("generation >= 0", name="ck_discussion_context_generation"),)


class ContextObservationRecord(BaseModel):
    """The interpretation checkpoint of one piece of evidence: version and proof, no body."""

    __tablename__ = "discussion_context_observations"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    root: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(256), nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "root", name="uq_discussion_observation_root"),
        Index("ix_discussion_observations_expiry", "expires_at"),
        Index("ix_discussion_observations_source", "user_id", "source"),
    )


class ContextItemRecord(BaseModel):
    """One derived context item (observation, episode or pattern) and the roots it rests on."""

    __tablename__ = "discussion_context_items"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    root_keys: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_discussion_context_item_owner"),
        CheckConstraint(
            "kind IN ('observation', 'episode', 'pattern')", name="ck_discussion_context_item_kind"
        ),
        CheckConstraint(
            "revision > 0 AND generation > 0", name="ck_discussion_context_item_versions"
        ),
        Index("ix_discussion_context_items_owner", "user_id", "updated_at"),
        Index("ix_discussion_context_items_expiry", "expires_at"),
        Index("ix_discussion_context_items_roots", "root_keys", postgresql_using="gin"),
    )


class ContextSupportRecord(BaseModel):
    """Link a derived item to an observation it rests on; deleting either side unlinks."""

    __tablename__ = "discussion_context_supports"
    user_id: Mapped[UUID] = mapped_column(nullable=False)
    item_id: Mapped[UUID] = mapped_column(nullable=False)
    root: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "item_id"],
            ["discussion_context_items.user_id", "discussion_context_items.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["user_id", "root"],
            ["discussion_context_observations.user_id", "discussion_context_observations.root"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("user_id", "item_id", "root", name="uq_discussion_context_support"),
        Index("ix_discussion_supports_root", "user_id", "root"),
    )


class ContextExclusionRecord(BaseModel):
    """A "not usable" choice on an item and its roots; it survives purges and rebuilds."""

    __tablename__ = "discussion_context_exclusions"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # No FK to a content row: purge deliberately preserves these explicit choices.
    item_id: Mapped[UUID] = mapped_column(nullable=False)
    root: Mapped[str] = mapped_column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", "root", name="uq_discussion_context_exclusion"),
    )


class ContextResumeRecord(BaseModel):
    """A content-free marker of a forgotten fact's version, so a purge is not undone.

    Rereading an unchanged source finds the marker and does not rebuild the fact.
    """

    __tablename__ = "discussion_context_resume_markers"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    root: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(256), nullable=False)
    __table_args__ = (
        UniqueConstraint("user_id", "root", name="uq_discussion_context_resume_root"),
    )
