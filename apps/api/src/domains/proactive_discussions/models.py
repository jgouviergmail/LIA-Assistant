"""Dedicated preferences and durable claim records; no new columns on User."""

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
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class DiscussionPreference(BaseModel):
    """One account's proactive-discussion settings, revision counters and run lease.

    ``revision`` moves with every policy change, ``context_epoch`` with every
    context rebuild or purge, ``run_fence`` with every claim and every cancelled claim;
    ``active_run_id`` and ``lease_until`` are set together while a run holds the
    account.
    """

    __tablename__ = "discussion_preferences"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    start_hour: Mapped[int] = mapped_column(
        Integer, default=9, server_default=text("9"), nullable=False
    )
    end_hour: Mapped[int] = mapped_column(
        Integer, default=20, server_default=text("20"), nullable=False
    )
    daily_max: Mapped[int | None] = mapped_column(
        Integer, default=2, server_default=text("2"), nullable=True
    )
    sources: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    sensitive_topics: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    forbidden_topics: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )
    context_epoch: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )
    run_fence: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )
    active_run_id: Mapped[UUID | None] = mapped_column(nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_discussion_preferences_owner"),
        CheckConstraint("daily_max IS NULL OR daily_max > 0", name="ck_discussion_max"),
        CheckConstraint(
            "start_hour BETWEEN 0 AND 23 AND end_hour BETWEEN 0 AND 23 AND start_hour <> end_hour",
            name="ck_discussion_hours",
        ),
        CheckConstraint(
            "revision >= 0 AND run_fence >= 0 AND context_epoch >= 0",
            name="ck_discussion_revisions",
        ),
        CheckConstraint(
            "(active_run_id IS NULL) = (lease_until IS NULL)", name="ck_discussion_lease_pair"
        ),
        Index("ix_discussion_candidates", "enabled", "paused_until", "user_id"),
    )


class DiscussionRun(BaseModel):
    """One claimed producer run: an opening attempt, or a rebuild the person asked for.

    It records the policy revision and the context epoch it was claimed under,
    its outcome once settled, and when a deferred run may be retried.
    """

    __tablename__ = "discussion_runs"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    fence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    policy_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    context_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A context rebuild the person asked for, never an opening (its cost is shown as such).
    context_only: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    # Why the run ended as it did (``RunReason``) and what it read and interpreted:
    # counts only, never content. NULL until settled.
    reason: Mapped[str | None] = mapped_column(String(48), nullable=True)
    stats: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("user_id", "fence", name="uq_discussion_run_fence"),
        UniqueConstraint("user_id", "id", name="uq_discussion_run_owner_id"),
        CheckConstraint(
            "state IN ('claimed', 'completed', 'skipped', 'failed', 'abandoned')",
            name="ck_discussion_run_state",
        ),
        Index("ix_discussion_runs_owner_date", "user_id", "claimed_at"),
        Index(
            "ix_discussion_runs_owner_rebuilds",
            "user_id",
            "claimed_at",
            postgresql_where=text("context_only"),
        ),
    )


class DiscussionOpeningRecord(BaseModel):
    """One opening LIA published: its archived message, topic, supports and state.

    The fingerprint is unique per account, so the same opening is never published
    twice, and at most one opening per account is pending at a time;
    ``sensitive_context`` makes its delivery private.
    """

    __tablename__ = "discussion_openings"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(nullable=False, unique=True)
    message_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str] = mapped_column(String(256), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    references: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    context_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sensitive_context: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "run_id"],
            ["discussion_runs.user_id", "discussion_runs.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("user_id", "id", name="uq_discussion_opening_owner_id"),
        UniqueConstraint("user_id", "fingerprint", name="uq_discussion_opening_fingerprint"),
        CheckConstraint(
            "state IN ('pending', 'engaged', 'dismissed', 'expired')",
            name="ck_discussion_opening_state",
        ),
        Index("ix_discussion_openings_owner_date", "user_id", "created_at"),
        Index(
            "uq_discussion_pending_owner",
            "user_id",
            unique=True,
            postgresql_where=text("state = 'pending'"),
        ),
    )


class DiscussionOutbox(BaseModel):
    """The delivery of one published opening, settled from what each transport accepted."""

    __tablename__ = "discussion_outbox"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opening_id: Mapped[UUID] = mapped_column(nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempt_token: Mapped[UUID | None] = mapped_column(nullable=True)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "opening_id"],
            ["discussion_openings.user_id", "discussion_openings.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "state IN ('pending', 'dispatching', 'delivered', 'failed', 'uncertain', 'cancelled')",
            name="ck_discussion_outbox_state",
        ),
        Index("ix_discussion_outbox_pending", "state", "created_at"),
    )
