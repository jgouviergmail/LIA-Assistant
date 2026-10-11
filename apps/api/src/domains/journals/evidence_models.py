"""Independent, idempotent outcomes attached to the rule version exposed."""

from datetime import UTC, datetime
from uuid import UUID as PythonUUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class JournalEvidenceEvent(BaseModel):
    """One source event can qualify a rule version only once."""

    __tablename__ = "journal_evidence_events"

    user_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    journal_entry_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False
    )
    rule_revision: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    source_conversation_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_journal_evidence_rule_event",
            "journal_entry_id",
            "rule_revision",
            "event_key",
            unique=True,
        ),
        Index("ix_journal_evidence_user", "user_id"),
        CheckConstraint(
            "outcome IN ('evidence', 'contradiction')", name="ck_journal_evidence_outcome"
        ),
        CheckConstraint("rule_revision > 0", name="ck_journal_evidence_revision"),
    )
