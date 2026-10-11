"""Durable command identity; encrypted payloads never become permission facts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domains.agents.application.outcomes import ApplicationPhase
from src.infrastructure.database.models import BaseModel


class ApplicationCommand(BaseModel):
    __tablename__ = "application_commands"
    actor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    draft_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    operation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    content_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[ApplicationPhase] = mapped_column(
        Enum(
            ApplicationPhase,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ApplicationPhase.PENDING,
    )
    claim_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_binding_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_application_commands_actor_phase", "actor_id", "phase"),)
