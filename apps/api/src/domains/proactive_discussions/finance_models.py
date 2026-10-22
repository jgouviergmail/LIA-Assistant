"""Discretionary reservations are separate from the native provider billing ledger."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class DiscussionBudgetBucket(BaseModel):
    """One UTC day's held and spent discretionary allowance for one scope.

    The scope is ``instance`` for the deployment or ``owner:<id>`` for one account.
    A reservation holds an amount here before a run spends, and the settlement
    moves what was really spent from held to spent.
    """

    __tablename__ = "discussion_budget_buckets"
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    held_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal(0), server_default="0"
    )
    spent_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal(0), server_default="0"
    )
    __table_args__ = (
        UniqueConstraint("scope_key", "day", name="uq_discussion_budget_scope_day"),
        CheckConstraint(
            "held_usd >= 0 AND spent_usd >= 0", name="ck_discussion_budget_nonnegative"
        ),
        Index("ix_discussion_budget_day", "day"),
    )


class DiscussionSpendReservation(BaseModel):
    """The allowance one run reserved before calling any model, and what it spent.

    ``estimate_usd`` is the amount held, ``issued_usd`` what the permit has
    released to calls so far, ``actual_usd`` the settled spend. ``state`` moves
    from held to settled, or to uncertain when a call's outcome was not confirmed.
    """

    __tablename__ = "discussion_spend_reservations"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(nullable=False, unique=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    estimate_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    actual_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal(0), server_default="0"
    )
    issued_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal(0), server_default="0"
    )
    state: Mapped[str] = mapped_column(
        String(12), nullable=False, default="held", server_default="held"
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "run_id"],
            ["discussion_runs.user_id", "discussion_runs.id"],
            ondelete="CASCADE",
            name="fk_discussion_spend_owned_run",
        ),
        CheckConstraint(
            "estimate_usd > 0 AND actual_usd >= 0 AND issued_usd >= 0 AND issued_usd <= estimate_usd",
            name="ck_discussion_spend_nonnegative",
        ),
        CheckConstraint(
            "state IN ('held','settled','uncertain')", name="ck_discussion_spend_state"
        ),
        Index("ix_discussion_spend_owner_day", "user_id", "day"),
    )
