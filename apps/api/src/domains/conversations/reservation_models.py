"""Durable child work prevents a voice closing from releasing a running relay."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, false
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.core.conversation_execution import ReservationPurpose, ReservationWorkPhase
from src.infrastructure.database.models import BaseModel


class ConversationReservationWork(BaseModel):
    """An owner token identifies a worker; no elapsed time proves its completion."""

    __tablename__ = "conversation_reservation_work"

    activity_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversation_executions.id", ondelete="CASCADE"), nullable=False
    )
    worker_id: Mapped[UUID] = mapped_column(nullable=False)
    owner_token: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)
    purpose: Mapped[ReservationPurpose] = mapped_column(String(16), nullable=False)
    phase: Mapped[ReservationWorkPhase] = mapped_column(
        SAEnum(
            ReservationWorkPhase,
            name="conversation_reservation_work_phase",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [value.value for value in values],
            validate_strings=True,
        ),
        default=ReservationWorkPhase.RUNNING,
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    standby_relay_settled: Mapped[bool] = mapped_column(server_default=false(), nullable=False)
    standby_recap: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_conversation_reservation_work_activity_phase", "activity_id", "phase"),
        CheckConstraint(
            "purpose IN ('opening', 'request', 'closing', 'relay')",
            name="ck_conversation_reservation_work_purpose",
        ),
        CheckConstraint(
            "(phase = 'closed') = (closed_at IS NOT NULL)",
            name="ck_conversation_reservation_work_closed_at",
        ),
        CheckConstraint(
            "(NOT standby_relay_settled OR purpose = 'relay') "
            "AND (standby_recap IS NULL OR standby_relay_settled)",
            name="ck_conversation_reservation_work_standby_recap",
        ),
    )
