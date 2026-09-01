"""Diagnostics repository: snapshots and the atomic incident lifecycle.

The open-or-touch upsert follows the ChatRepository doctrine: one server-side
``INSERT ... ON CONFLICT DO UPDATE`` targeting the partial unique index, never
SELECT → mutate → flush (lost updates under webhook-vs-leader concurrency).
The statement builder is a pure function so its SQL shape is unit-testable
without a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import Boolean, delete, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql.dml import ReturningInsert
from sqlalchemy.sql.elements import Label

from src.core.repository import BaseRepository
from src.domains.diagnostics.models import (
    INCIDENT_STATUS_OPEN,
    INCIDENT_STATUS_RESOLVED,
    HealthSnapshot,
    Incident,
)
from src.domains.users.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def build_open_or_touch_stmt(
    *,
    correlation_key: str,
    source: str,
    severity: str,
    title: str,
    alertname: str | None,
    fingerprint: str | None,
    evidence: dict[str, object],
    now: datetime,
) -> ReturningInsert[tuple[UUID, datetime | None, bool]]:
    """Build the atomic open-or-touch INSERT for one incident observation.

    Insert opens a new incident; conflict on the partial unique index (an
    incident is already open for this key) only refreshes recency and severity
    — history (opened_at, source, evidence) belongs to the first observer.

    Args:
        correlation_key: Deduplication identity (alertname or check_id).
        source: 'alert' or 'self_check'.
        severity: 'critical' or 'warning'.
        title: Short human title.
        alertname: Alertmanager alertname, when known.
        fingerprint: Alertmanager fingerprint, when alert-sourced.
        evidence: Evidence pack of the FIRST observation (exact values).
        now: Observation time (aware UTC).

    Returns:
        The compiled-ready statement, RETURNING the row + created flag.
    """
    stmt = pg_insert(Incident).values(
        correlation_key=correlation_key,
        source=source,
        severity=severity,
        title=title,
        alertname=alertname,
        fingerprint=fingerprint,
        evidence=evidence,
        action_log=[],
        status=INCIDENT_STATUS_OPEN,
        opened_at=now,
        last_seen_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Incident.correlation_key],
        index_where=Incident.status == INCIDENT_STATUS_OPEN,
        set_={
            "last_seen_at": now,
            "severity": severity,
        },
    )
    # xmax = 0 marks a freshly inserted row (PostgreSQL system column), which
    # is how callers learn "created vs touched" from the single round trip.
    return stmt.returning(Incident.id, Incident.notified_at, _created_expr())


def _created_expr() -> Label[bool]:
    """The 'was this row inserted' expression (xmax = 0), labelled ``created``."""
    return literal_column("(xmax = 0)", type_=Boolean).label("created")


class DiagnosticsRepository(BaseRepository[HealthSnapshot]):
    """Persistence for health snapshots and incidents."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a session.

        Args:
            db: Async session owned by the caller.
        """
        super().__init__(db, HealthSnapshot)

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------
    async def save_snapshot(
        self, *, taken_at: datetime, overall: str, results: list[dict[str, object]]
    ) -> HealthSnapshot:
        """Persist one self-check snapshot.

        Args:
            taken_at: When the self-check ran.
            overall: Worst verdict across checks.
            results: Per-check result dicts.

        Returns:
            The persisted snapshot.
        """
        snapshot = HealthSnapshot(taken_at=taken_at, overall=overall, results=results)
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    async def latest_snapshot(self) -> HealthSnapshot | None:
        """Return the most recent snapshot, or None on a fresh install."""
        result = await self.db.execute(
            select(HealthSnapshot).order_by(HealthSnapshot.taken_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def snapshots_since(self, since: datetime, limit: int = 500) -> list[HealthSnapshot]:
        """Snapshots taken after ``since``, oldest first (timeline order).

        Args:
            since: Lower bound (exclusive).
            limit: Row cap (the caller states it when hit).

        Returns:
            Snapshots ordered by taken_at ascending.
        """
        result = await self.db.execute(
            select(HealthSnapshot)
            .where(HealthSnapshot.taken_at > since)
            .order_by(HealthSnapshot.taken_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def prune_snapshots(self, retention_days: int) -> int:
        """Delete snapshots older than the retention window.

        Args:
            retention_days: Age threshold in days.

        Returns:
            Number of rows deleted (exact).
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self.db.execute(
            delete(HealthSnapshot).where(HealthSnapshot.taken_at < cutoff)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------
    async def open_or_touch_incident(
        self,
        *,
        correlation_key: str,
        source: str,
        severity: str,
        title: str,
        alertname: str | None = None,
        fingerprint: str | None = None,
        evidence: dict[str, object] | None = None,
    ) -> tuple[UUID, bool, datetime | None]:
        """Atomically open a new incident or refresh the open one.

        Args:
            correlation_key: Deduplication identity.
            source: 'alert' or 'self_check'.
            severity: 'critical' or 'warning'.
            title: Short human title.
            alertname: Alertmanager alertname, when known.
            fingerprint: Alertmanager fingerprint, when alert-sourced.
            evidence: Evidence pack (kept only when the incident is created).

        Returns:
            (incident_id, created, notified_at) — ``created`` is True when
            this call opened the incident; ``notified_at`` is the current
            notification stamp (None if never notified), used for cooldowns.
        """
        stmt = build_open_or_touch_stmt(
            correlation_key=correlation_key,
            source=source,
            severity=severity,
            title=title,
            alertname=alertname,
            fingerprint=fingerprint,
            evidence=evidence or {},
            now=datetime.now(UTC),
        )
        row = (await self.db.execute(stmt)).one()
        return row.id, bool(row.created), row.notified_at

    async def resolve_incident(self, correlation_key: str, *, source: str | None = None) -> int:
        """Resolve the open incident for a correlation key, if any.

        Args:
            correlation_key: Deduplication identity.
            source: Restrict to incidents opened by this source ('self_check'
                auto-resolve must not close alert-sourced incidents — the
                alert's own resolved event owns those).

        Returns:
            Number of incidents resolved (0 or 1 by schema construction).
        """
        stmt = (
            update(Incident)
            .where(
                Incident.correlation_key == correlation_key,
                Incident.status == INCIDENT_STATUS_OPEN,
            )
            .values(status=INCIDENT_STATUS_RESOLVED, resolved_at=datetime.now(UTC))
        )
        if source is not None:
            stmt = stmt.where(Incident.source == source)
        result = await self.db.execute(stmt)
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def list_incidents(
        self, *, status: str | None = None, page: int = 1, page_size: int = 25
    ) -> tuple[list[Incident], int]:
        """Page incidents newest-first with an EXACT total.

        Args:
            status: Optional status filter ('open'/'resolved').
            page: 1-based page number.
            page_size: Rows per page.

        Returns:
            (rows, exact_total) — the total is a COUNT(*) over the filtered
            set, never the length of a capped page (counting doctrine).
        """
        filters = [] if status is None else [Incident.status == status]
        total = (
            await self.db.execute(select(func.count()).select_from(Incident).where(*filters))
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(Incident)
                .where(*filters)
                .order_by(Incident.opened_at.desc())
                .offset((max(page, 1) - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
        return list(rows.all()), int(total)

    async def get_incident(self, incident_id: UUID) -> Incident | None:
        """Fetch one incident by id.

        Args:
            incident_id: Incident UUID.

        Returns:
            The incident, or None.
        """
        return await self.db.get(Incident, incident_id)

    async def incidents_needing_diagnosis(self, limit: int) -> list[Incident]:
        """Open incidents with no diagnosis yet, oldest first (pump input).

        Args:
            limit: Batch cap for one pump tick.

        Returns:
            Incidents awaiting the budgeted LLM diagnosis step.
        """
        result = await self.db.execute(
            select(Incident)
            .where(Incident.status == INCIDENT_STATUS_OPEN, Incident.diagnosis.is_(None))
            .order_by(Incident.opened_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_notified(self, incident_id: UUID) -> None:
        """Stamp the notification time (cooldown anchor).

        Args:
            incident_id: Incident UUID.
        """
        await self.db.execute(
            update(Incident).where(Incident.id == incident_id).values(notified_at=datetime.now(UTC))
        )

    async def distinct_admin_languages(self) -> list[str]:
        """Languages the administrators of this instance read.

        Used to decide which languages a diagnosis is written in, because the
        scheduler tick that writes it has no reader to ask.

        Returns:
            Distinct non-empty language codes of active superusers.
        """
        result = await self.db.execute(
            select(User.language)
            .where(User.is_superuser.is_(True), User.is_active.is_(True))
            .distinct()
        )
        return [row[0] for row in result.all() if row[0]]

    async def store_diagnosis(self, incident_id: UUID, diagnosis: dict[str, object]) -> None:
        """Attach the diagnosis produced by the budgeted LLM step.

        Args:
            incident_id: Incident UUID.
            diagnosis: New diagnosis dict (whole-column write — JSONB rule).
        """
        await self.db.execute(
            update(Incident).where(Incident.id == incident_id).values(diagnosis=diagnosis)
        )

    async def append_action(self, incident_id: UUID, entry: dict[str, object]) -> None:
        """Append one audit entry to the incident's action log.

        Uses a server-side JSONB concatenation so concurrent appends cannot
        lose each other (never read-modify-write a JSONB column).

        Args:
            incident_id: Incident UUID.
            entry: Audit entry (action, actor, ts, outcome).
        """
        await self.db.execute(
            update(Incident)
            .where(Incident.id == incident_id)
            .values(action_log=Incident.action_log.op("||")(func.to_jsonb([entry])))
        )
