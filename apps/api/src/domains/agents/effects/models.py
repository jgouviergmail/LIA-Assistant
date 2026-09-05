"""SQLAlchemy model of the effect ledger (ADR-263).

Design rules, each paid for by a measurement in the 2026-09-03 analysis:

- The row is CLAIMED before the effect and closed from an EXPLICIT result:
  absence of an exception is not proof of delivery (Systemic Rules).
- ``(thread_id, idempotency_key)`` is unique, so the same approval cannot be
  spent twice — the defect two simulations reproduced, where a confirmed draft
  sent its email again on the next turn.
- ``claim_token`` conditions every close: a stale worker cannot close a row it
  no longer owns (fencing).
- No JSONB: every column is a scalar, so nothing can be mutated in place — the
  recurring SQLAlchemy silent-skip defect cannot occur here by construction.
- ``result_payload`` and ``label`` are encrypted by the repository
  (``encrypt_data``, like every other PII at rest); the ledger stores what a
  resume needs and what a human register displays, never in clear.
- Retention: until the account is deleted (``ondelete="CASCADE"``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import AGENT_EFFECT_SCHEMA_VERSION
from src.infrastructure.database.models import UUIDMixin
from src.infrastructure.database.session import Base


class EffectStatus(str, Enum):
    """Lifecycle of one external effect.

    ``CLAIMED`` is the only state in which an effect may be performed;
    everything else is terminal. ``REFUSED`` records an effect that was NOT
    attempted because the authority was missing — a fact worth keeping, since
    it is what the answer will say and what the operator will count.
    """

    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABANDONED = "abandoned"
    REFUSED = "refused"


class EffectSource(str, Enum):
    """Who asked for the turn that produced the effect.

    Deliberately three values: the heartbeat runs no tool, and a peer never
    mutates on someone else's behalf — two values removed before they were born
    rather than left as dead vocabulary.
    """

    USER = "user"
    SCHEDULED = "scheduled"
    SUBAGENT = "subagent"


class AgentEffect(Base, UUIDMixin):
    """One external effect: claimed before it happens, closed from its result.

    Intentionally without ``TimestampMixin``: a ledger row is never updated
    after it closes, and its two timestamps are business facts
    (``claimed_at`` / ``closed_at``), not bookkeeping.
    """

    __tablename__ = "agent_effects"

    # --- Who and where -----------------------------------------------------
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Acting user; the ledger is deleted with the account.",
    )
    thread_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="LangGraph thread the effect belongs to."
    )
    run_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Billing/correlation id of the run."
    )
    source: Mapped[EffectSource] = mapped_column(
        # values_callable: store the VALUES ("user"), not the member NAMES
        # ("USER") — the project convention, and what the migration's CHECK
        # constraint declares. Without it the model and the migration disagree,
        # and the disagreement only shows in production: the test schema is
        # built from this metadata, so it would agree with itself and pass.
        SAEnum(
            EffectSource,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        comment="Who asked for the turn: user, scheduled action, sub-agent.",
    )
    execution_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="pipeline | react | subagent."
    )

    # --- What -------------------------------------------------------------
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    mutation_policy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="The policy that applied when the effect was claimed (ADR-263).",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="tool_call_id (react) | draft_id (draft) | run_id:step_id (pipeline).",
    )
    args_digest: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Keyed digest of tool name + arguments."
    )

    # --- Under which authority --------------------------------------------
    approval_kind: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="draft_critique | tool_confirmation | for_each | policy.",
    )
    approval_ref: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="message_id of the card, or draft_id."
    )
    draft_digest: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Digest of the draft_content the user was shown (ADR-092 binding).",
    )

    # --- Lifecycle ---------------------------------------------------------
    status: Mapped[EffectStatus] = mapped_column(
        SAEnum(
            EffectStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    claim_token: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        comment="Owner token: every close is conditioned on it (fencing).",
    )
    retry_of: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agent_effects.id", ondelete="SET NULL"),
        nullable=True,
        comment="The FAILED/ABANDONED row this claim retries.",
    )
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- What came back ----------------------------------------------------
    provider_ref: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Provider-side identifier (message id, event id) when the tool returns one.",
    )
    result_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Digest of the result, to verify the payload."
    )
    result_payload: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Encrypted (encrypt_data) tool result, kept so a resume can be served "
            "from the ledger instead of re-executing the effect."
        ),
    )
    result_truncated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="True when result_payload was cut at the configured cap.",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Stable code of a FAILED or REFUSED effect."
    )
    label: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Encrypted (encrypt_data) JSON {i18n_key, values} built at claim time; "
            "rendered in the reader's language at export, never a frozen sentence."
        ),
    )

    # --- Provenance --------------------------------------------------------
    catalogue_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Digest of the catalogue that offered the tool."
    )
    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=AGENT_EFFECT_SCHEMA_VERSION,
        server_default=str(AGENT_EFFECT_SCHEMA_VERSION),
        comment="Row shape, bumped on every additive column (ADR-263).",
    )

    # --- Notarisation (ADR-263 lot 5) --------------------------------------
    # Written by the NOTARY, never by the write path, and the only two columns
    # the chain does not digest — digesting them would make the act of
    # notarising invalidate the digest it just took.
    notarised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the CLAIM stage entered the chain. NULL = pending.",
    )
    settled_notarised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the OUTCOME stage entered the chain. NULL = pending.",
    )

    __table_args__ = (
        UniqueConstraint(
            "thread_id", "idempotency_key", name="uq_agent_effects_thread_idempotency"
        ),
        Index("ix_agent_effects_user_claimed", "user_id", "claimed_at"),
        Index("ix_agent_effects_run", "run_id"),
        # PARTIAL, and that is the whole point: the notary's tick costs
        # O(pending) rather than O(register). Measured on 50 000 rows: 0,64 ms
        # against 9,93 ms for a join over the chain.
        Index(
            "ix_agent_effects_pending_claim",
            "user_id",
            "claimed_at",
            "id",
            postgresql_where=text("notarised_at IS NULL"),
        ),
        # The outcome stage waits for a row to LEAVE `claimed`: a row still
        # open has nothing to notarise yet.
        Index(
            "ix_agent_effects_pending_settled",
            "user_id",
            "closed_at",
            "id",
            postgresql_where=text("settled_notarised_at IS NULL AND status <> 'claimed'"),
        ),
    )

    def __repr__(self) -> str:
        """Identify the row without leaking anything the ledger protects."""
        return (
            f"<AgentEffect(tool={self.tool_name}, status={self.status}, "
            f"policy={self.mutation_policy})>"
        )


class TreatmentOutcome(str, Enum):
    """What was observed of a consultation. Two values, deliberately.

    A treatment is not claimed, so it has no ``claimed`` state; it is not
    confirmed, so it has no ``refused``. It either answered or it did not —
    anything finer would be a copy of the effect vocabulary in a place where
    it means nothing.
    """

    OK = "ok"
    FAILED = "failed"


class AgentTreatment(Base, UUIDMixin):
    """One consultation: which capability was used, when, with which outcome.

    The register of ACTIONS answers *what did it do?*; this one answers *what
    did it consult to answer me?*. They are two tables rather than one table
    with a discriminator, for reasons that are structural rather than stylistic:

    - a consultation has **no idempotency key**, so it could not satisfy
      ``UNIQUE(thread_id, idempotency_key)``, and two reads of one capability
      in a turn would collide on a synthetic one;
    - ``status``, ``claim_token`` and ``approval_kind`` mean nothing here;
    - and a discriminator would force every existing query to filter — the
      first one that forgets makes a displayed total lie (ADR-185).

    **What it deliberately does NOT carry**: the arguments, and any label built
    from them. « Searched Marie's emails » reveals a search nobody asked to
    have recorded, where « sent an email to Marie » records an act the user
    requested. The wording shown to a reader is resolved at display time from
    the capability name, through the SAME ``execution.steps.*`` keys the ⚙
    trace already uses in six languages.

    Retention: until the account is deleted (``ondelete="CASCADE"``), like the
    actions. No purge job — the growth is instrumented instead
    (``lia_ledger_rows`` / ``lia_ledger_bytes``), so the day it must be built
    is a measured day (owner arbitration, 2026-09-04).
    """

    __tablename__ = "agent_treatments"

    # --- Who and where -----------------------------------------------------
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Acting user; the register is deleted with the account.",
    )
    thread_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="LangGraph thread the consultation belongs to."
    )
    run_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Run that consulted the capability."
    )
    source: Mapped[EffectSource] = mapped_column(
        # Same convention as the effects table: store the VALUES, never the
        # member names — a disagreement here only shows in production.
        SAEnum(
            EffectSource,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        comment="Who asked for the turn: user, scheduled action, sub-agent.",
    )
    execution_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="pipeline | react | subagent."
    )

    # --- What ---------------------------------------------------------------
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    mutation_policy: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Declared policy, or NULL for a capability that declares none.",
    )
    outcome: Mapped[TreatmentOutcome] = mapped_column(
        SAEnum(
            TreatmentOutcome,
            native_enum=False,
            length=10,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        comment="Whether the capability answered.",
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Wall-clock duration of the call."
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the call returned (UTC)."
    )

    # Written by the NOTARY (ADR-263 lot 5), never by the write path.
    notarised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this consultation entered the chain. NULL = pending.",
    )

    __table_args__ = (
        # The only two questions asked of this table: « this turn » and
        # « my journal ». No uniqueness: a consultation is not idempotent.
        Index("ix_agent_treatments_run", "run_id"),
        Index("ix_agent_treatments_user_occurred", "user_id", "occurred_at"),
        Index(
            "ix_agent_treatments_pending",
            "user_id",
            "occurred_at",
            "id",
            postgresql_where=text("notarised_at IS NULL"),
        ),
        {"comment": "What the assistant CONSULTED, as opposed to what it did (ADR-263)."},
    )

    def __repr__(self) -> str:
        """Identify the row; there is nothing here to protect, by construction."""
        return f"<AgentTreatment(tool={self.tool_name}, outcome={self.outcome})>"


class LedgerChainEntry(Base, UUIDMixin):
    """One link of an account's tamper-evident chain (ADR-263, lot 5).

    The chain NOTARISES the two registers; it never copies them. An entry holds
    a digest of the row it covers and the hash of its predecessor, so altering
    a register row CONTRADICTS the chain without being able to forge it, and
    deleting one leaves an entry pointing at nothing — equally visible.

    Three properties are enforced by this shape rather than by code that could
    forget them:

    - **one chain per account** — deleting an account removes a COMPLETE chain
      (FK CASCADE) and leaves no permanent hole in anyone else's. That is what
      dissolves the tension between inalterability and the right to erasure: a
      shared chain would have to choose between keeping a deleted account's
      digests and never verifying again;
    - **``UNIQUE (user_id, seq)``** — a forked chain is impossible even if two
      notaries run at once (simulated: one pass refused, sequence contiguous,
      no subject notarised twice, nothing left pending);
    - **no content column**, so the chain costs ~387 bytes an entry and
      duplicates nothing.

    ``digest_version`` is what makes the encoding evolvable: verification picks
    the rule the ENTRY declares, so a future change is a new version rather
    than a silent reinterpretation that would redden every past chain.
    """

    __tablename__ = "ledger_chain"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Whose chain. The chain is deleted with the account, entire.",
    )
    seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Position in THIS account's chain, from 1, contiguous.",
    )
    kind: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment="Stage covered: chain.genesis | effect.claimed | effect.settled | "
        "treatment.recorded. Written into the hash, so never renamed.",
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="Register row covered; NULL for the genesis entry, which covers none.",
    )
    payload_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Digest of the covered row's business columns (chain_digest).",
    )
    prev_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Hash of the previous entry; NULL only for the first of a chain.",
    )
    entry_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="sha256 over the canonical encoding of this entry, predecessor included.",
    )
    digest_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Encoding rule that produced the digests — read back at verification.",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When this entry was appended (UTC) — notarisation order, not "
        "necessarily the covered row's chronology.",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "seq", name="uq_ledger_chain_user_seq"),
        # The walk verification performs, and nothing else.
        Index("ix_ledger_chain_user_seq", "user_id", "seq"),
        # « Is this row covered, and by which stage » — asked per row, so it
        # must not scan.
        Index("ix_ledger_chain_subject", "subject_id", "kind"),
        {"comment": "Tamper-evident chain notarising the two registers (ADR-263)."},
    )

    def __repr__(self) -> str:
        """Identify the link; an entry holds nothing to protect."""
        return f"<LedgerChainEntry(seq={self.seq}, kind={self.kind})>"


class AgentIntegrityEvent(Base, UUIDMixin):
    """One observed gap in the record itself (ADR-263, lot 8).

    The three registers say what LIA did, read and decided. This one says when
    they could NOT — an effect performed with no row, a turn whose
    consultations nobody collected, a chain that stopped verifying, a sealing
    pass that was rolled back.

    They already have metrics and alerts. A counter cannot say WHICH accounts
    and WHICH turns are affected, and that is the question a user and a
    regulator actually ask; hence a row rather than a fifth counter.

    **It must read as empty in production.** A non-zero count is the signal, not
    the norm, which is also why the table carries no index beyond its two reads:
    it is not meant to grow.

    ``user_id`` and ``run_id`` are nullable because one of the detections
    happens precisely when no run context named a user — and that absence is
    itself the interesting part, not a value to invent.
    """

    __tablename__ = "agent_integrity_events"

    kind: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        comment="effect_unrecorded | treatments_uncollected | chain_broken | notary_failed",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        comment="Whose account, when the detection knew. NULL = no run context named one.",
    )
    run_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Which turn, when the detection knew."
    )
    detail: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="SHORT bounded classification (a reason code, a position) — never content.",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the gap was observed (UTC)."
    )

    __table_args__ = (
        # The two reads: one account's gaps, and the instance's recent ones.
        Index("ix_agent_integrity_user_occurred", "user_id", "occurred_at"),
        Index("ix_agent_integrity_occurred", "occurred_at"),
        {"comment": "Gaps in the transparency record itself (ADR-263, lot 8)."},
    )

    def __repr__(self) -> str:
        """Identify the gap; the row holds nothing to protect."""
        return f"<AgentIntegrityEvent(kind={self.kind}, run={self.run_id})>"


class DecisionOutcome(str, Enum):
    """How a turn ended.

    Three values, and the third is the one that matters: a turn that never
    reached an answer is a fact, not an absence. Without it the register would
    hold only the turns that went well — which is the shape of an account
    nobody should trust.
    """

    ANSWERED = "answered"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class AgentDecision(Base, UUIDMixin):
    """One TURN, and what was decided in it (ADR-263, lot 6).

    The spine the other two registers hang off. ``agent_effects`` says what was
    DONE and ``agent_treatments`` what was READ; both carry a ``run_id`` that,
    until now, pointed at nothing. This row is what that identifier means: who
    asked, through which route, in which mode, ending how — and, by POINTER,
    the message that asked and the message that answered.

    **It points, it never copies.** ``conversation_messages`` is already the
    user's own data, purged with the account, so duplicating a request here
    would be a second copy of the very words the register exists to make
    accountable — and a second place to leak them. The two foreign keys are
    ``SET NULL``: deleting a conversation leaves a dated TOMBSTONE (the turn
    happened, its text is gone), never a resurrection and never a lie.

    **One row per turn, and a HITL resumption is the SAME turn.** ``run_id`` is
    reused across an interrupt, so the write is an UPSERT and ``segments``
    counts how many times the turn ran. Overwriting in silence would make a
    turn stopped for a confirmation indistinguishable from one that ran
    straight through — which is precisely the fact an audit wants.

    **No content, like its two neighbours.** No prompt, no answer, no plan
    text: a route, a count, timings, and two pointers.
    """

    __tablename__ = "agent_decisions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Account the turn belongs to. Dies with it.",
    )
    thread_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Conversation the turn belongs to."
    )
    run_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="The turn. Unique: a HITL resumption reuses it and updates this row.",
    )
    source: Mapped[EffectSource] = mapped_column(
        # Same convention as its two neighbours: a CHECK-backed VARCHAR storing
        # the VALUES, never a native type and never the member names. A
        # disagreement here only shows in production, because the test schema
        # is built from this metadata and would agree with itself.
        SAEnum(
            EffectSource,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        comment="Under whose authority the turn ran (user | scheduled | subagent).",
    )
    execution_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="pipeline | react | subagent"
    )
    route: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="What the router decided (conversation | actionable | react); "
        "NULL when the turn ended before routing.",
    )
    plan_step_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Steps the planner produced; NULL when no plan was built.",
    )
    request_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="POINTER to what was asked — never a copy. SET NULL leaves a tombstone.",
    )
    response_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="POINTER to what was answered — never a copy. SET NULL leaves a tombstone.",
    )
    outcome: Mapped[DecisionOutcome] = mapped_column(
        SAEnum(
            DecisionOutcome,
            native_enum=False,
            length=12,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        comment="answered | failed | interrupted — a turn that never answered is a fact.",
    )
    stop_reason: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="Why the turn stopped short (max_iterations | compute_budget | ...); "
        "NULL when it ran to its natural end. ADR-263 lot 8.",
    )
    segments: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="How many times this turn ran. Above 1 = it was interrupted and resumed.",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the turn began (UTC) — the EARLIEST across its segments.",
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When it last ended (UTC) — the LATEST across its segments.",
    )
    duration_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Cumulative time the turn actually ran."
    )
    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text(str(AGENT_EFFECT_SCHEMA_VERSION)),
        comment="Shape of the row, so a reader never guesses which columns it was written with.",
    )

    __table_args__ = (
        UniqueConstraint("run_id", name="uq_agent_decisions_run"),
        # The journal read: one account's turns, newest first.
        Index("ix_agent_decisions_user_started", "user_id", "started_at"),
        # « Which turns touched this conversation », asked by the surfaces.
        Index("ix_agent_decisions_thread", "thread_id"),
        {"comment": "One row per turn: the spine the two registers hang off (ADR-263)."},
    )

    def __repr__(self) -> str:
        """Identify the turn; the row holds nothing to protect."""
        return f"<AgentDecision(run={self.run_id}, outcome={self.outcome})>"
