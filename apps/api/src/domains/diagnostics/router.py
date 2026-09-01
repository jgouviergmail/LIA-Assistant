"""Admin diagnostics REST (superuser-only, read-only).

Briefing-style split endpoints: the fast overview (Redis-cached), the paged
incident memory (exact totals), and the snapshot timeline. Included in
``routes.py`` only when DIAGNOSTICS_ENABLED is true.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_not_found_or_unauthorized
from src.core.security.authorization import require_superuser
from src.core.session_dependencies import get_current_active_session
from src.domains.diagnostics.diagnosis import diagnosis_for_language
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.domains.diagnostics.schemas import (
    IncidentDetailOut,
    IncidentListOut,
    IncidentSummaryOut,
    SnapshotOut,
)
from src.domains.diagnostics.service import build_overview_cached
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/diagnostics", tags=["admin-diagnostics"])

#: Alias kept at module level so tests can monkeypatch the composition seam.
build_overview = build_overview_cached


@router.get(
    "/overview",
    summary="Platform health overview",
    description="Latest self-check snapshot, firing alerts, open incidents, degradations.",
)
async def get_overview(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Compose the admin overview (superuser only)."""
    require_superuser(current_user, "read platform diagnostics")
    return await build_overview(db)


@router.get(
    "/incidents",
    response_model=IncidentListOut,
    summary="List incidents",
    description="Paged incident memory, newest first, with an exact total.",
)
async def list_incidents(
    status_filter: str | None = Query(
        default="open", alias="status", description="open, resolved, or all"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> IncidentListOut:
    """Page the incident memory (superuser only)."""
    require_superuser(current_user, "read platform incidents")
    status = None if status_filter in (None, "all") else status_filter
    rows, total = await DiagnosticsRepository(db).list_incidents(
        status=status, page=page, page_size=page_size
    )
    items = [
        IncidentSummaryOut(
            id=row.id,
            correlation_key=row.correlation_key,
            source=row.source,
            severity=row.severity,
            status=row.status,
            title=row.title,
            opened_at=row.opened_at,
            last_seen_at=row.last_seen_at,
            resolved_at=row.resolved_at,
            has_diagnosis=row.diagnosis is not None,
        )
        for row in rows
    ]
    return IncidentListOut(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentDetailOut,
    summary="Incident detail",
    description="One incident with its evidence, stored diagnosis and action audit.",
)
async def get_incident(
    incident_id: UUID,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> IncidentDetailOut:
    """Fetch one incident (superuser only)."""
    require_superuser(current_user, "read platform incidents")
    incident = await DiagnosticsRepository(db).get_incident(incident_id)
    if incident is None:
        raise_not_found_or_unauthorized(resource_type="incident", resource_id=incident_id)
    return IncidentDetailOut(
        id=incident.id,
        correlation_key=incident.correlation_key,
        source=incident.source,
        severity=incident.severity,
        status=incident.status,
        title=incident.title,
        opened_at=incident.opened_at,
        last_seen_at=incident.last_seen_at,
        resolved_at=incident.resolved_at,
        has_diagnosis=incident.diagnosis is not None,
        evidence=incident.evidence or {},
        # Resolved for THIS reader: the tick wrote one variant per admin
        # language, and an admin must not have to read someone else's.
        diagnosis=diagnosis_for_language(incident.diagnosis, current_user.language),
        action_log=incident.action_log or [],
    )


@router.get(
    "/snapshots",
    response_model=list[SnapshotOut],
    summary="Health snapshot timeline",
    description="Snapshots of the look-back window, oldest first.",
)
async def list_snapshots(
    hours: int = Query(default=24, ge=1, le=168),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[SnapshotOut]:
    """Snapshot timeline for the health graph (superuser only)."""
    require_superuser(current_user, "read platform diagnostics")
    since = datetime.now(UTC) - timedelta(hours=hours)
    snapshots = await DiagnosticsRepository(db).snapshots_since(since)
    return [SnapshotOut.model_validate(snapshot) for snapshot in snapshots]
