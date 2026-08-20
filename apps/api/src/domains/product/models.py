"""SQLAlchemy models for the product analytics domain (ADR-178).

``product_outcomes`` is the durable product truth: at most ONE principal
outcome per run (unique ``run_id``), with mutable state/evidence — an E2
requires the full validation window without correction/reversion, which is
why the North Star is never computed from Prometheus counters.

``product_events`` is the bounded lifecycle log (decision #2: included in v1).

Both tables carry ``user_id`` and are registered in the GDPR purge map
(``users/user_data_map.py``) and in the account deletion service.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class ProductOutcome(BaseModel):
    """One principal product outcome per run (spec §4, ADR-178).

    Attributes:
        user_id: Owner (plain UUID, purge handled by the deletion service).
        run_id: Chat run identifier — unique (one principal outcome per run),
            joins to ``message_token_summary.run_id`` for EUR cost backfill.
        workflow_id: Optional orchestration lineage identifier.
        result_type: Bounded ``RESULT_TYPES`` value.
        domain: Bounded ``DOMAIN_REGISTRY`` domain, or ``unknown`` (v1 seam
            does not resolve domains yet — documented approximation).
        execution_mode: ``pipeline`` | ``react`` (ADR-070 user preference).
        channel: Bounded ``CHANNELS`` value (derived, decision #3/#4).
        device_class: Bounded ``DEVICE_CLASSES`` value (derived from the
            request user-agent through ``core.client_metadata`` — ADR-144).
        locale: Backend-canonical language (``normalize_language`` chokepoint).
        state: ``produced`` | ``validated`` | ``rejected``.
        evidence_level: ``E1`` | ``E2`` | ``E3`` (E3 until validated).
        produced_at: When the result was presented to the user (UTC).
        validated_at: When E1/E2 validation happened (UTC), if any.
        first_pass: False when the result needed retries/corrections first.
        corrected: Explicit negative signal within the validation window.
        reverted: The materialized action was undone (v1: never set — needs
            per-connector reversal detection, later lot).
        latency_ms: Request-to-presentation latency in milliseconds.
        turn_count: User turns consumed to reach the result, when known.
        cost_eur: Total EUR cost for the run (backfilled from
            ``message_token_summary`` by the rollup job — LLM + Google API +
            image generation).
        app_version: Backend version string, when known.
    """

    __tablename__ = "product_outcomes"

    user_id: Mapped[UUID] = mapped_column(index=True)
    run_id: Mapped[str] = mapped_column(String(255))
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    result_type: Mapped[str] = mapped_column(String(32))
    domain: Mapped[str] = mapped_column(String(64), default="unknown")
    execution_mode: Mapped[str] = mapped_column(String(16), default="pipeline")
    channel: Mapped[str] = mapped_column(String(16), default="unknown")
    device_class: Mapped[str] = mapped_column(String(16), default="unknown")
    locale: Mapped[str] = mapped_column(String(10), default="fr")

    state: Mapped[str] = mapped_column(String(16), default="produced", index=True)
    evidence_level: Mapped[str] = mapped_column(String(2), default="E3")

    produced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    first_pass: Mapped[bool] = mapped_column(default=True)
    corrected: Mapped[bool] = mapped_column(default=False)
    reverted: Mapped[bool] = mapped_column(default=False)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    turn_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", name="product_outcomes_run_id_key"),
        Index("ix_product_outcomes_user_produced", "user_id", "produced_at"),
        Index("ix_product_outcomes_evidence_validated", "evidence_level", "validated_at"),
        Index("ix_product_outcomes_state_produced", "state", "produced_at"),
    )


class ProductEvent(BaseModel):
    """Bounded product lifecycle event (``ProductEventType`` vocabulary).

    Attributes:
        user_id: Owner (purged with the account).
        run_id: Related run, when the event is run-scoped.
        event_type: Bounded ``ProductEventType`` value.
        channel: Bounded ``CHANNELS`` value.
        occurred_at: Event time (UTC).
        payload: Small bounded JSONB payload (verdict, evidence…) — never
            free text, never message content (PII rule).
    """

    __tablename__ = "product_events"

    # Nullable: anonymous pre-signup funnel events (Phase 4, arbitration a) —
    # counts only, no identifier of any kind stored.
    user_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # 64 (not 32): per-mission showroom values reach 39 chars — the historical
    # String(32) made those INSERTs fail and silently lost the funnel rows.
    # Guarded (derived) by test_product_constants.TestVocabularyFitsPersistedColumns.
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="unknown")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_product_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_product_events_type_occurred", "event_type", "occurred_at"),
    )
