"""Snapshot → incident synchronisation (self-check side of the correlation).

Rules (spec 2026-08-27, pillar 3):

- CRITICAL opens (or touches) an incident. The correlation key is the check's
  declared ``alertname`` when it mirrors a core alert, else its ``check_id`` —
  so the Alertmanager webhook and the self-check converge on ONE incident.
- OK auto-resolves ONLY ``self_check``-sourced incidents: the alert's own
  resolved event owns alert-sourced ones (two authorities would race).
- DEGRADED and UNKNOWN neither open nor resolve: degraded is watched, and
  blindness must never invent or clear an outage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from src.domains.diagnostics.checks import CheckResult, CheckStatus, evidence_for
from src.domains.diagnostics.models import INCIDENT_SOURCE_SELF_CHECK

if TYPE_CHECKING:
    from src.domains.diagnostics.repository import DiagnosticsRepository

logger = structlog.get_logger(__name__)


@dataclass
class IncidentSyncOutcome:
    """What one synchronisation pass did (for logs, metrics, notifications)."""

    opened_ids: list[UUID] = field(default_factory=list)
    opened_keys: list[str] = field(default_factory=list)
    touched: int = 0
    resolved: int = 0


async def sync_incidents_from_results(
    repo: DiagnosticsRepository,
    results: list[CheckResult],
) -> IncidentSyncOutcome:
    """Open/touch/resolve incidents from one snapshot's check results.

    Args:
        repo: Diagnostics repository bound to the caller's session (the caller
            owns the transaction and the commit).
        results: Per-check results of the snapshot.

    Returns:
        The synchronisation outcome (newly opened incidents carry their ids so
        the caller can notify admins for THOSE only, never for touches).
    """
    outcome = IncidentSyncOutcome()
    for result in results:
        correlation_key = result.alertname or result.check_id
        if result.status is CheckStatus.CRITICAL:
            incident_id, created, _notified_at = await repo.open_or_touch_incident(
                correlation_key=correlation_key,
                source=INCIDENT_SOURCE_SELF_CHECK,
                severity="critical",
                title=f"Self-check critical: {result.check_id}",
                alertname=result.alertname,
                evidence=evidence_for(result),
            )
            if created:
                outcome.opened_ids.append(incident_id)
                outcome.opened_keys.append(correlation_key)
            else:
                outcome.touched += 1
        elif result.status is CheckStatus.OK:
            outcome.resolved += await repo.resolve_incident(
                correlation_key, source=INCIDENT_SOURCE_SELF_CHECK
            )
    if outcome.opened_ids or outcome.resolved:
        logger.info(
            "diagnostics_incident_sync",
            opened=len(outcome.opened_ids),
            touched=outcome.touched,
            resolved=outcome.resolved,
        )
    return outcome
