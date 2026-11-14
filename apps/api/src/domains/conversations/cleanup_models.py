"""Durable, content-free cleanup debt that outlives the source it removes."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.conversation_target import ConversationKind
from src.domains.conversations.cleanup_contracts import (
    CleanupPhase,
    CleanupState,
    ConversationAction,
)
from src.infrastructure.database.models import BaseModel


class ConversationOperation(BaseModel):
    """A logical transition and its exact unfinished physical targets.

    No foreign key may erase this debt on account or discussion removal. There
    is no message, title, filename, credential or model content in the receipt.
    Completed receipts alone are eligible for bounded retention.
    """

    __tablename__ = "conversation_operations"

    user_id: Mapped[UUID] = mapped_column(nullable=False)
    request_id: Mapped[UUID] = mapped_column(nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[ConversationAction] = mapped_column(
        SAEnum(
            ConversationAction,
            name="conversation_operation_action",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [v.value for v in values],
            validate_strings=True,
        )
    )
    conversation_kind: Mapped[ConversationKind] = mapped_column(
        SAEnum(
            ConversationKind,
            name="conversation_operation_kind",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [v.value for v in values],
            validate_strings=True,
        )
    )
    old_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    runtime_id: Mapped[UUID] = mapped_column(nullable=False)
    new_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attachment_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False)
    previous_message_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    state: Mapped[CleanupState] = mapped_column(
        SAEnum(
            CleanupState,
            name="conversation_cleanup_state",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [v.value for v in values],
            validate_strings=True,
        ),
        default=CleanupState.PENDING,
    )
    phase: Mapped[CleanupPhase] = mapped_column(
        SAEnum(
            CleanupPhase,
            name="conversation_cleanup_phase",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [v.value for v in values],
            validate_strings=True,
        ),
        default=CleanupPhase.CHECKPOINT,
    )
    owner_token: Mapped[UUID | None] = mapped_column(nullable=True)
    fence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_conversation_operation_request"),
        Index("ix_conversation_operations_pending", "state", "next_attempt_at", "id"),
        CheckConstraint(
            "old_revision >= 0 AND fence >= 0 AND attempts >= 0", name="ck_operation_counts"
        ),
        CheckConstraint(
            "(action = 'reset' AND new_revision IS NOT NULL AND new_revision = old_revision + 1) OR "
            "(action = 'delete' AND new_revision IS NULL)",
            name="ck_operation_revision",
        ),
        CheckConstraint(
            "(state = 'succeeded') = (completed_at IS NOT NULL) AND "
            "(state = 'succeeded') = (phase = 'complete')",
            name="ck_operation_complete",
        ),
        CheckConstraint(
            "(state = 'running' AND owner_token IS NOT NULL AND claim_until IS NOT NULL) OR "
            "(state <> 'running' AND owner_token IS NULL AND claim_until IS NULL)",
            name="ck_operation_claim",
        ),
    )
