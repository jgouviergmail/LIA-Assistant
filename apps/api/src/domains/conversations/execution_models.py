"""Durable occupancy survives Redis expiry and an unacknowledged worker stop."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import CONVERSATION_RUN_ID_MAX_LENGTH
from src.core.conversation_execution import ExecutionKind, ExecutionPhase, RunEnd
from src.core.conversation_target import ConversationKind
from src.infrastructure.database.models import BaseModel

# Shared by the active-slot index and its operational reader so PostgreSQL
# can use the partial index even after choosing a generic prepared plan.
ACTIVE_EXECUTION_PREDICATE = text("phase <> 'closed'")


class ConversationExecution(BaseModel):
    """One reservation, closed only after its actual owned producer has joined.

    Conversation identity has no foreign key: an operational recovery record
    must not disappear if the discussion is subsequently removed. It contains
    no message, prompt, title or provider credential.
    """

    __tablename__ = "conversation_executions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[UUID] = mapped_column(nullable=False)
    conversation_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    runtime_id: Mapped[UUID] = mapped_column(nullable=False)
    conversation_kind: Mapped[ConversationKind] = mapped_column(
        SAEnum(
            ConversationKind,
            name="execution_conversation_kind",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [value.value for value in values],
            validate_strings=True,
        )
    )
    kind: Mapped[ExecutionKind] = mapped_column(
        SAEnum(
            ExecutionKind,
            name="conversation_execution_kind",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [value.value for value in values],
            validate_strings=True,
        )
    )
    phase: Mapped[ExecutionPhase] = mapped_column(
        SAEnum(
            ExecutionPhase,
            name="conversation_execution_phase",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [value.value for value in values],
            validate_strings=True,
        ),
        default=ExecutionPhase.RUNNING,
    )
    fence: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    owner_token: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)
    worker_id: Mapped[UUID] = mapped_column(nullable=False)
    run_id: Mapped[str] = mapped_column(String(CONVERSATION_RUN_ID_MAX_LENGTH), nullable=False)
    stream_id: Mapped[str] = mapped_column(String(CONVERSATION_RUN_ID_MAX_LENGTH), nullable=False)
    relayed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancellable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_state: Mapped[RunEnd | None] = mapped_column(
        SAEnum(
            RunEnd,
            name="conversation_execution_end",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [value.value for value in values],
            validate_strings=True,
        ),
        nullable=True,
        comment="How the run ended, declared by its driver; NULL until closed or if undeclared.",
    )
    accepts_notes: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
        comment=(
            "The answer being written takes the person's notes now: a ReAct loop a person "
            "waits for, between its first model call and its exit (ADR-385)."
        ),
    )

    __table_args__ = (
        # Independent kinds: one voice session and one graph may coexist.
        Index(
            "uq_conversation_execution_active_owner_kind",
            "user_id",
            "kind",
            unique=True,
            postgresql_where=ACTIVE_EXECUTION_PREDICATE,
        ),
        Index("ix_conversation_executions_runtime_phase", "runtime_id", "phase"),
        Index("uq_conversation_execution_owner_stream", "user_id", "stream_id", unique=True),
        CheckConstraint("conversation_revision >= 0", name="ck_execution_revision"),
        CheckConstraint("fence > 0", name="ck_execution_fence"),
        CheckConstraint(
            "(phase = 'closed') = (closed_at IS NOT NULL)", name="ck_execution_closed_at"
        ),
        CheckConstraint("end_state IS NULL OR phase = 'closed'", name="ck_execution_end_state"),
        # Only a running invocation can still call its model (ADR-385).
        CheckConstraint(
            "NOT accepts_notes OR phase = 'running'", name="ck_execution_notes_running"
        ),
    )
