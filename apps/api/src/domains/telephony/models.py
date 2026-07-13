"""PhoneCall ORM model — one row per placed call (created at draft execution)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class PhoneCallStatus(str, enum.Enum):
    """Lifecycle of an outbound call (distinct from the pre-call PHONE_CALL draft)."""

    DIALING = "dialing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PhoneCallOutcome(str, enum.Enum):
    """Semantic outcome of a completed call, set by the return synthesis."""

    OBJECTIVE_MET = "objective_met"
    PARTIAL = "partial"
    DECLINED = "declined"
    UNREACHABLE = "unreachable"


# Predicate for the "active call" partial unique index (F12).
# NOTE: SQLAlchemy Enum(native_enum=False) stores the member NAME ('DIALING'),
# not the value ('dialing') — matching the whole codebase (connector_type stores
# 'GOOGLE_GMAIL', status stores 'ACTIVE'). The raw-SQL predicate MUST use the
# uppercase member names, else it matches no rows and the guard silently no-ops.
# The telephony integration test locks this name/value trap.
_ACTIVE_STATUSES_SQL = "status IN ('DIALING', 'IN_PROGRESS')"


class PhoneCall(BaseModel):
    """A single outbound call. PII (``callee_phone``) is encrypted by the service.

    Vendor call costs are the user's own (D-9) — ``call_seconds`` is factual
    metadata, never converted to money. The raw transcript is never stored (D-8):
    only ``summary`` + minimal ``structured_data`` survive, purged after
    ``expires_at`` by the retention reaper.
    """

    __tablename__ = "phone_calls"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    callee_display: Mapped[str] = mapped_column(Text, nullable=False)
    callee_phone: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted by the service
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    objective_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    objective_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[PhoneCallStatus] = mapped_column(
        Enum(PhoneCallStatus, native_enum=False, length=20),
        nullable=False,
        default=PhoneCallStatus.DIALING,
        index=True,
    )
    elevenlabs_conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    outcome: Mapped[PhoneCallOutcome | None] = mapped_column(
        Enum(PhoneCallOutcome, native_enum=False, length=20), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # F12: at most one active (dialing/in_progress) call per user, enforced
        # atomically at the DB level (never SELECT-then-check).
        Index(
            "uq_phone_calls_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text(_ACTIVE_STATUSES_SQL),
        ),
        # Reconciliation fallback key; NULL until initiated, unique among non-null.
        Index(
            "uq_phone_calls_el_conversation",
            "elevenlabs_conversation_id",
            unique=True,
            postgresql_where=text("elevenlabs_conversation_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<PhoneCall(id={self.id}, user_id={self.user_id}, status={self.status})>"
