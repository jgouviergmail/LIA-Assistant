"""
Usage limits domain models.

Defines the UserUsageLimit model for per-user usage quota management.
Each user can have at most one limit record (1:1 relationship with User).
Null limit values mean 'unlimited' — no enforcement for that dimension.

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.constants import USAGE_LIMIT_BLOCKED_REASON_MAX_LENGTH
from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.users.models import User


class UserUsageLimit(BaseModel):
    """Per-user usage limits configuration.

    One row per user. Null limit values mean 'unlimited'.
    Usage data (current counters) comes from UserStatistics (JOIN at query time).

    Attributes:
        user_id: FK to users table (unique, 1:1 relationship).
        token_limit_per_cycle: Max tokens (prompt+completion) per billing cycle.
        message_limit_per_cycle: Max user messages per billing cycle.
        cost_limit_per_cycle: Max cost (EUR) per billing cycle.
        token_limit_absolute: Max tokens (prompt+completion) lifetime.
        message_limit_absolute: Max user messages lifetime.
        cost_limit_absolute: Max cost (EUR) lifetime.
        is_usage_blocked: Admin manual kill switch.
        blocked_reason: Human-readable reason for manual block.
        blocked_at: Timestamp when user was manually blocked.
        blocked_by: Admin user_id who set the block.
    """

    __tablename__ = "user_usage_limits"

    # --- User reference (1:1) ---
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
        comment="User this limit configuration applies to.",
    )

    # --- Per-cycle limits (monthly rolling, aligned with user.created_at) ---
    token_limit_per_cycle: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
        comment="Max combined tokens (prompt+completion) per billing cycle. NULL = unlimited.",
    )
    message_limit_per_cycle: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
        comment="Max user messages per billing cycle. NULL = unlimited.",
    )
    cost_limit_per_cycle: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
        default=None,
        comment="Max cost (EUR) per billing cycle. NULL = unlimited.",
    )

    # --- Absolute/lifetime limits ---
    token_limit_absolute: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
        comment="Max combined tokens (prompt+completion) lifetime. NULL = unlimited.",
    )
    message_limit_absolute: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
        comment="Max user messages lifetime. NULL = unlimited.",
    )
    cost_limit_absolute: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6),
        nullable=True,
        default=None,
        comment="Max cost (EUR) lifetime. NULL = unlimited.",
    )

    # --- Manual block ---
    is_usage_blocked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default="false",
        comment="Admin manual kill switch. Blocks user even if limits not reached.",
    )
    blocked_reason: Mapped[str | None] = mapped_column(
        String(USAGE_LIMIT_BLOCKED_REASON_MAX_LENGTH),
        nullable=True,
        default=None,
        comment="Human-readable reason for manual block.",
    )
    blocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp when user was manually blocked.",
    )
    blocked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        default=None,
        comment="Admin user_id who set the block.",
    )

    # --- Relationships ---
    user: Mapped[User] = relationship(back_populates="usage_limit")

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<UserUsageLimit(user_id={self.user_id}, "
            f"blocked={self.is_usage_blocked}, "
            f"tokens_cycle={self.token_limit_per_cycle})>"
        )


class InstanceDailyBudget(BaseModel):
    """Instance-wide daily spend ledger (live-demonstrator programme).

    ONE row per UTC day for the WHOLE instance — the only bound that holds
    when every visitor gets their own account (per-user limits cannot cap
    what N accounts spend together). Written exclusively through the atomic
    UPSERT in ``InstanceBudgetService.record_spend``.

    Attributes:
        utc_day: The UTC calendar day; unique, and the ledger's identity.
        spent_cost_eur: Sum of every billable family (LLM, Google API,
            image generation) recorded for that day.
        run_count: How many runs contributed, for operator context only.
        signup_count: Visitor slots reserved that day (demo mode).
    """

    __tablename__ = "instance_daily_budget"

    utc_day: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        unique=True,
        index=True,
        doc="UTC calendar day this ledger row aggregates.",
    )
    spent_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        server_default="0",
        doc="Total euros billed on that day, every cost family included.",
    )
    run_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
        doc="Number of runs that contributed (operator context only).",
    )
    signup_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default="0",
        # `doc=` is Python-level only; the SQL comment is part of the schema
        # contract (see infrastructure/database/schema_drift.py — only
        # `modify_default` is cosmetic), so the migration's comment must be
        # mirrored here or a from-scratch replay reports drift.
        comment="Visitor slots reserved on that UTC day (demo mode).",
        doc=(
            "Visitor slots reserved on that day, in demo mode. Lives on the "
            "same row as the money because it is the same question — what did "
            "this instance do today — and because the row already carries the "
            "unique UTC-day key an atomic reservation needs. Moved by a "
            "conditional UPSERT only: counting rows and then inserting let a "
            "simultaneous burst through (37 accounts against a ceiling of 5, "
            "measured 2026-08-07)."
        ),
    )
