"""Scheduled Actions domain models.

A routine runs on ONE of three clocks (ADR-322, ADR-386). A TIME routine stores
a ``RecurrenceSpec`` (``src/core/recurrence``) — which calendar days it serves,
and which moments inside them. A CONDITION routine stores no schedule: the
system checks its condition (``domains/scheduled_actions/trigger.py``). A
WEBHOOK routine stores an address and its secret: another system's signed call
is kept as a delivery and arms it. The scheduler polls for due rows on
``next_trigger_at`` (UTC), which is NULL when nothing follows.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, OUT_OF_TURN_EXECUTION_MODE_DEFAULT
from src.core.recurrence import RecurrenceSpec
from src.domains.shared.mcp_preapproval import MCPPreapproval, stored_server_keys
from src.infrastructure.database.models import BaseModel, UUIDMixin
from src.infrastructure.database.session import Base

if TYPE_CHECKING:
    from src.domains.users.models import User


class ScheduledActionStatus(str, Enum):
    """Status of a scheduled action."""

    ACTIVE = "active"  # Ready for execution
    EXECUTING = "executing"  # Currently running (locked by scheduler)
    ERROR = "error"  # Auto-disabled after max consecutive failures
    # A routine with no future left: its `SeriesEnd` date passed, its
    # `after_count` ran out, or its single occurrence was consumed (ADR-281,
    # lot 5). Distinct from ERROR on purpose — « it finished » and « it
    # failed » are different things to tell someone — and distinct from a
    # pause, which somebody chose.
    COMPLETED = "completed"


class TriggerKind(str, Enum):
    """Which clock a routine runs on (N-07, ADR-322) — one, never both.

    A TIME routine runs at every instant of its recurrence. A CONDITION
    routine has no recurrence: the system checks its condition on a per-type
    cadence (``trigger.py``, every ten minutes by default for the connector
    sources) and it runs only on a NEW fact
    (``condition_state``). N-07 phase 1 kept « cron as the clock for both
    kinds », so a condition was only read at the hours its schedule named — a
    mail watch answered eight to sixteen hours late. The push wake still brings
    a mail watch's check forward (ADR-281).
    """

    TIME = "time"  # Runs at every instant of its recurrence
    CONDITION = "condition"  # Checked by the system; runs on a new fact
    # ADR-386: another system calls the routine's address, signed with its
    # secret; the next pass serves what the calls brought.
    WEBHOOK = "webhook"


# Condition vocabulary (N-07 phase 1). The EVALUATORS live in
# infrastructure/scheduler/condition_evaluators.py — the infra layer already
# orchestrates cross-domain (briefing fetchers ↔ this domain), and importing
# briefing from here would close a domain↔domain cycle (fetchers.py already
# imports this domain for the For-you card). A boot-time completeness assert
# in that module keeps REGISTRY and this frozenset in lockstep (ADR-085).
CONDITION_TYPE_TASK_OVERDUE = "task_overdue"
CONDITION_TYPE_WEATHER_CHANGE = "weather_change"
CONDITION_TYPE_MAIL_MATCH = "mail_match"
CONDITION_TYPE_DOCUMENT_ADDED = "document_added"
CONDITION_TYPE_CALENDAR_EVENT = "calendar_event"
# ADR-387: a public page a person watches — read by the system, no model,
# and a run only for the lines that were not on it at the last reading.
CONDITION_TYPE_PAGE_CHANGE = "page_change"

CONDITION_TYPES: frozenset[str] = frozenset(
    {
        CONDITION_TYPE_TASK_OVERDUE,
        CONDITION_TYPE_WEATHER_CHANGE,
        CONDITION_TYPE_MAIL_MATCH,
        CONDITION_TYPE_DOCUMENT_ADDED,
        CONDITION_TYPE_CALENDAR_EVENT,
        CONDITION_TYPE_PAGE_CHANGE,
    }
)


class ScheduledAction(BaseModel):
    """A recurring action the agent pipeline runs on the owner's behalf.

    The schedule is a ``RecurrenceSpec`` in ``recurrence``: single occurrence,
    daily/weekly/monthly/yearly with an interval, one or several moments a day.
    ``next_trigger_at`` is derived from it after every tick and is NULL once
    the series is over.

    Unlike a reminder — a post-it deleted once notified — a routine persists
    and re-arms.
    """

    __tablename__ = "scheduled_actions"

    # Foreign key to user
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Content
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="User-facing title - 'Weather lookup'",
    )
    action_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Prompt sent to agent pipeline - 'look up today's weather'",
    )

    # Schedule — ONE authority (generic recurrence, `src/core/recurrence`).
    # The three cron columns this replaces could not describe a routine firing
    # twice a day, and keeping them beside the spec would let the row disagree
    # with itself. NULL for a condition routine, which has no schedule: the
    # table's CHECK holds the pairing (ADR-322). SQL `comment=` mirrors the
    # migration EXACTLY.
    recurrence: Mapped[dict | None] = mapped_column(
        # ``none_as_null``: a Python None is SQL NULL, never the JSON ``null``
        # the CHECK below would read as a schedule (measured on dev: the
        # first condition routine created through the service was refused).
        JSONB(none_as_null=True),
        nullable=True,
        comment="TIME kind only: RecurrenceSpec, which days and moments. NULL for a condition.",
    )
    user_timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DEFAULT_USER_DISPLAY_TIMEZONE,
        doc="IANA timezone for schedule evaluation",
    )

    # Computed trigger time (UTC) — recalculated after each execution.
    # NULLABLE since the recurrence rework: NULL means nothing follows (an
    # exhausted series, a consumed single occurrence). `NULL <= now()` is
    # UNKNOWN in SQL, so the scheduler's poll excludes such a row by
    # construction rather than by a filter someone must remember to write.
    next_trigger_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Next execution (UTC); NULL = nothing follows.",
    )

    # N-07, ADR-322: which clock the routine runs on. SQL `comment=` mirrors
    # the migration EXACTLY (the replay check compares them); richer context
    # lives in TriggerKind and ADR-322.
    trigger_kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TriggerKind.TIME.value,
        server_default=TriggerKind.TIME.value,
        comment=(
            "time = runs on its recurrence; condition = checked by the system (ADR-322); "
            "webhook = started by a signed call to its address (ADR-386)"
        ),
    )
    condition_config: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
        comment="CONDITION kind only: {type, params, until} — schema-validated.",
    )
    # Fact ledger — writes are full NEW-dict replacements (JSONB rule),
    # through ``condition_ledger.ConditionLedger`` alone.
    condition_state: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
        comment="Fact ledger: {seen, last_checked_at, last_check_error, last_fired_at}.",
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True = propose via notification (?intent= link) instead of executing.",
    )
    # ADR-265 amendment 2026-11-12 c: the run still happens and its answer still
    # lands in the chat; what this holds back is the NOTIFICATION, when the
    # answering model declares it found nothing new. SQL `comment=` mirrors the
    # migration EXACTLY.
    notify_only_when_new: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True = a run that found nothing new is answered in the chat and not notified.",
    )

    execution_mode: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=OUT_OF_TURN_EXECUTION_MODE_DEFAULT,
        server_default=OUT_OF_TURN_EXECUTION_MODE_DEFAULT,
        comment=(
            "pipeline | react — how this routine executes. The loop by default: "
            "nobody is there to steer a plan when it fires."
        ),
    )
    # Spec 2026-10-29 D9: the MCP servers whose confirmations a run may give
    # itself, ticked in the routine's form — the only writer (its REST route).
    # ``none_as_null``: no pre-approval is SQL NULL, never the JSON ``null``.
    mcp_preapproved_servers: Mapped[list[str] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
        comment="MCP server keys a run may confirm for itself (routine form only). NULL = none.",
    )

    # ADR-386: a webhook routine's address key and its HMAC secret, set exactly
    # when the routine runs on that clock (CHECK below). The secret is Fernet
    # ciphertext (``encrypt_data``): decrypted to check a signature, and shown to
    # its owner once, when it is drawn. SQL ``comment=`` mirrors the migration.
    webhook_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="WEBHOOK kind only: the key of its address. NULL otherwise.",
    )
    webhook_secret: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="WEBHOOK kind only: its HMAC secret, encrypted. NULL otherwise.",
    )

    # Status
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="User toggle - False = paused",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ScheduledActionStatus.ACTIVE.value,
        index=True,
        doc="active -> executing -> active (recurring cycle)",
    )

    # Execution tracking
    execution_token: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="Opaque reservation identity; a late manual job cannot consume a newer run.",
    )
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Last successful execution timestamp (UTC)",
    )
    execution_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Total successful executions",
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Consecutive failure count (reset on success)",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Last execution error message",
    )

    # Relationship
    user: Mapped[User] = relationship("User", back_populates="scheduled_actions", lazy="selectin")

    __table_args__ = (
        # Partial index for scheduler poll query (hot path)
        Index(
            "ix_scheduled_actions_due",
            "next_trigger_at",
            postgresql_where=(
                "is_enabled = true AND status = 'active' AND next_trigger_at IS NOT NULL"
            ),
        ),
        # One clock per routine (ADR-322, ADR-386): the rule
        # `schemas.trigger_mode_refusal` states to the API caller, held by the
        # table for every other writer.
        CheckConstraint(
            "(trigger_kind = 'time' AND recurrence IS NOT NULL AND condition_config IS NULL)"
            " OR (trigger_kind = 'condition' AND recurrence IS NULL"
            " AND condition_config IS NOT NULL)"
            " OR (trigger_kind = 'webhook' AND recurrence IS NULL"
            " AND condition_config IS NULL)",
            name="ck_scheduled_actions_one_clock",
        ),
        # A webhook routine has its address and its secret, and only it does.
        CheckConstraint(
            "(trigger_kind = 'webhook')"
            " = (webhook_key IS NOT NULL AND webhook_secret IS NOT NULL)",
            name="ck_scheduled_actions_webhook_address",
        ),
        UniqueConstraint("webhook_key", name="uq_scheduled_actions_webhook_key"),
    )

    @property
    def recurrence_spec(self) -> RecurrenceSpec | None:
        """The stored schedule, parsed; ``None`` for a condition routine.

        A property rather than a column type: the row keeps plain JSONB, so a
        migration or an admin query never depends on the Python model.

        Returns:
            The recurrence this routine follows, or ``None`` when the system's
            checks are its clock.
        """
        if self.recurrence is None:
            return None
        return RecurrenceSpec.model_validate(self.recurrence)

    @property
    def mcp_preapproval(self) -> MCPPreapproval | None:
        """What a run of this routine may confirm for itself (spec D9), or ``None``.

        Returns:
            The pre-approved servers with this routine as the approval's
            reference, or ``None`` when the form ticked none.
        """
        servers = frozenset(stored_server_keys(self.mcp_preapproved_servers))
        return MCPPreapproval(servers=servers, routine_id=str(self.id)) if servers else None

    def __repr__(self) -> str:
        return (
            f"<ScheduledAction(id={self.id}, title='{self.title}', "
            f"status={self.status}, next={self.next_trigger_at})>"
        )


class ScheduledRunOutcome(str, Enum):
    """How one tick of a routine ended (ADR-265).

    Each exit of the executor has a reason, so the weekly timeline can say
    WHY a cell is not green rather than leaving a silent blank: skips
    and the proposal happen BEFORE the pipeline runs and count no execution,
    and no skip counts toward the pause a series of failures ends in.

    ``skipped_condition`` has had NO producer since ADR-322: a condition
    routine is now checked by the system, every ten minutes by default, and a
    row per unmet check would have written 144 a day per routine at that
    default — the check is recorded on the routine's ledger instead
    (``last_checked_at``). The value stays so the rows written before stay
    readable until the retention purges them.
    """

    SUCCESS = "success"  # The pipeline answered.
    FAILURE = "failure"  # Every attempt failed (error kept on the row).
    SKIPPED_CONDITION = "skipped_condition"  # Legacy (pre ADR-322): an unmet check.
    PROPOSED = "proposed"  # Propose-first: notified, waiting for the user's click.
    SKIPPED_HITL = "skipped_hitl"  # A HITL interrupt was pending on the conversation.
    # Another graph occupied this account for the whole catch-up window of the
    # occurrence (or when the person started the run): a busy account is first
    # waited for, pass after pass, with no row.
    SKIPPED_BUSY = "skipped_busy"
    # The account's usage ceiling stood the tick aside (ADR-272): not a failure,
    # nothing counts toward the pause. A time routine's row only — a condition
    # routine says it on its ledger (``last_check_error``).
    SKIPPED_QUOTA = "skipped_quota"
    # The scheduler reached the occurrence past its catch-up window (an outage,
    # a stalled scheduler): it is not run late, the routine re-arms.
    SKIPPED_LATE = "skipped_late"


class ScheduledActionRun(Base, UUIDMixin):
    """One tick of a routine, written AT ITS RESULT (ADR-265).

    Intentionally without ``TimestampMixin``: a run row is never updated — it is
    inserted once, from the executor's explicit outcome, in the same
    transaction as ``mark_execution_success`` / ``mark_execution_failure``.
    A crash mid-run therefore leaves NO row, which is the truth: nothing was
    delivered. The weekly timeline colours a cell from the run whose
    ``slot_at`` EQUALS the week's instant for that day — a schedule change
    moves the instants, so old runs stop matching by construction.

    Retention is bounded (``scheduled_actions_runs_retention_days``), purged
    inside the executor's own tick. SQL ``comment=`` mirrors the migration
    EXACTLY (the replay check compares them).
    """

    __tablename__ = "scheduled_action_runs"

    scheduled_action_id: Mapped[UUID] = mapped_column(
        ForeignKey("scheduled_actions.id", ondelete="CASCADE"),
        nullable=False,
        comment="The routine. Dies with it.",
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Whose routine — denormalised for the week read and the export.",
    )
    slot_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "The instant this run served (UTC): a time routine's slot, a condition "
            "routine's check; NULL = a rehearsal."
        ),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the tick started (UTC).",
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the outcome was known (UTC).",
    )
    outcome: Mapped[ScheduledRunOutcome] = mapped_column(
        # A VARCHAR storing the VALUES with a real CHECK, never a native
        # enum type, so adding a value stays an ordinary migration. `create_constraint`
        # is explicit because SQLAlchemy 2 defaults it to False — measured on
        # the dev database 2026-09-05, the register tables carry no CHECK at
        # all despite saying so; this one is proven by an integration test.
        SAEnum(
            ScheduledRunOutcome,
            native_enum=False,
            length=20,
            create_constraint=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        comment=(
            "success | failure | skipped_condition | proposed | skipped_hitl | skipped_busy"
            " | skipped_quota | skipped_late"
        ),
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="Pipeline attempts made (retries included); 0 when it never ran.",
    )
    manual: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True = started by the user (Test now), not by a due slot.",
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message of a FAILURE, truncated.",
    )
    run_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="The turn this run executed (joins the registers); NULL when it never ran.",
    )

    __table_args__ = (
        # The week read: one routine, its instants.
        Index("ix_scheduled_action_runs_action_slot", "scheduled_action_id", "slot_at"),
        # The export and any per-account listing.
        Index("ix_scheduled_action_runs_user_started", "user_id", "started_at"),
        # The retention purge, which knows no account.
        Index("ix_scheduled_action_runs_started", "started_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduledActionRun(action={self.scheduled_action_id}, "
            f"slot={self.slot_at}, outcome={self.outcome})>"
        )


class RoutineWebhookDeliveryStatus(str, Enum):
    """Where one accepted call stands (ADR-386)."""

    PENDING = "pending"  # Accepted, waiting for a run.
    SERVED = "served"  # Read by a run that answered; its body is erased.


class RoutineWebhookDelivery(Base, UUIDMixin):
    """One call a webhook routine accepted, kept until a run serves it (ADR-386).

    Written BEFORE the call is answered, in the transaction that arms the
    routine. A run reads its routine's pending calls oldest first and marks the
    ones it read served from its explicit success, in the transaction of the
    routine's own settle: the body is erased then, and the row stays
    ``ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS`` so that a delivery sent again is
    recognised by its id. Never updated otherwise. SQL ``comment=`` mirrors the
    migration EXACTLY.
    """

    __tablename__ = "routine_webhook_deliveries"

    scheduled_action_id: Mapped[UUID] = mapped_column(
        ForeignKey("scheduled_actions.id", ondelete="CASCADE"),
        nullable=False,
        comment="The routine called. Dies with it.",
    )
    delivery_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="The sender's own id for this delivery, when it gives one.",
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the call was accepted (UTC).",
    )
    content_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="The media type the sender declared, when it declared one.",
    )
    body_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Size of the body as received, in bytes.",
    )
    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="The body read as text, encrypted; erased once served.",
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=RoutineWebhookDeliveryStatus.PENDING.value,
        server_default=RoutineWebhookDeliveryStatus.PENDING.value,
        comment="pending = waiting for a run; served = read by a run that answered.",
    )
    served_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When a run that answered served it (UTC).",
    )

    __table_args__ = (
        # A delivery the sender names once is stored once per routine.
        Index(
            "uq_routine_webhook_deliveries_delivery",
            "scheduled_action_id",
            "delivery_id",
            unique=True,
            postgresql_where=text("delivery_id IS NOT NULL"),
        ),
        # A run's read: one routine's waiting calls, oldest first.
        Index(
            "ix_routine_webhook_deliveries_pending",
            "scheduled_action_id",
            "received_at",
            postgresql_where=text("status = 'pending'"),
        ),
        # The retention purge, which knows no routine.
        Index(
            "ix_routine_webhook_deliveries_served",
            "served_at",
            postgresql_where=text("status = 'served'"),
        ),
        CheckConstraint(
            "status IN ('pending', 'served')", name="ck_routine_webhook_deliveries_status"
        ),
        # Served exactly when stamped, and a served call keeps no body.
        CheckConstraint(
            "(status = 'served') = (served_at IS NOT NULL)",
            name="ck_routine_webhook_deliveries_served_at",
        ),
        CheckConstraint(
            "status = 'pending' OR body IS NULL",
            name="ck_routine_webhook_deliveries_served_body",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RoutineWebhookDelivery(action={self.scheduled_action_id}, "
            f"status={self.status}, bytes={self.body_bytes})>"
        )
