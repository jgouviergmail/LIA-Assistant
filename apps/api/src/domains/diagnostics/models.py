"""Diagnostics persistence models: health snapshots and incident memory.

Invariants carried by the SCHEMA, not by application discipline:

- at most ONE open incident per correlation key — a partial unique index on
  ``(correlation_key) WHERE status = 'open'`` makes the open-or-touch upsert
  atomic under concurrency (webhook worker vs self-check leader);
- every datetime is timezone-aware UTC;
- JSONB columns are only ever written by new-dict reassignment (repo rule).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel

#: Name of the partial unique index guaranteeing a single OPEN incident per
#: correlation key (referenced by the upsert's conflict target).
INCIDENT_OPEN_PARTIAL_INDEX_NAME = "uq_incidents_open_correlation"

#: Closed vocabulary of incident sources (String column, app-enforced).
INCIDENT_SOURCE_ALERT = "alert"
INCIDENT_SOURCE_SELF_CHECK = "self_check"

#: Closed vocabulary of incident statuses (String column, app-enforced).
INCIDENT_STATUS_OPEN = "open"
INCIDENT_STATUS_RESOLVED = "resolved"


class HealthSnapshot(BaseModel):
    """One self-check run: overall verdict plus per-check results.

    Attributes:
        taken_at: When the self-check ran (aware UTC).
        overall: Worst verdict across checks (ok/degraded/critical/unknown).
        results: JSONB list of per-check result dicts (exact measured values).
    """

    __tablename__ = "health_snapshots"

    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
    )
    overall: Mapped[str] = mapped_column(String(16), nullable=False)
    results: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)

    def __repr__(self) -> str:
        return f"<HealthSnapshot(taken_at={self.taken_at}, overall={self.overall})>"


class Incident(BaseModel):
    """One platform incident: opened by an alert or a critical self-check.

    The correlation key is the deduplication identity: the alert's
    ``alertname`` when one exists, otherwise the self-check's ``check_id`` —
    a check DECLARING the alertname it mirrors converges on the alert's key,
    so one outage yields one incident whichever source saw it first.

    Attributes:
        correlation_key: Deduplication identity (see above).
        source: 'alert' or 'self_check' — who opened it first.
        alertname: Alertmanager alertname when alert-sourced (or mirrored).
        fingerprint: Alertmanager fingerprint when alert-sourced.
        severity: 'critical' or 'warning' (alert label / check verdict).
        status: 'open' or 'resolved'.
        title: Short human title (summary annotation or check title).
        evidence: JSONB evidence pack (exact values; no PII, no secrets).
        diagnosis: JSONB diagnosis produced by the budgeted LLM step, or None.
        action_log: JSONB append-only list of actions taken/proposed.
        opened_at: First observation (aware UTC).
        last_seen_at: Most recent observation (touch on re-fire).
        resolved_at: When resolved, else None.
        notified_at: Last admin notification for this incident, else None.
    """

    __tablename__ = "incidents"

    correlation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    alertname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="critical")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=INCIDENT_STATUS_OPEN, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    diagnosis: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    action_log: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            INCIDENT_OPEN_PARTIAL_INDEX_NAME,
            "correlation_key",
            unique=True,
            postgresql_where=text(f"status = '{INCIDENT_STATUS_OPEN}'"),
        ),
        Index("ix_incidents_opened_at", "opened_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Incident(key={self.correlation_key}, status={self.status}, "
            f"severity={self.severity})>"
        )
