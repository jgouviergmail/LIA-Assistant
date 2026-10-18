"""Snapshot → incident synchronisation (self-check side of the correlation).

Rules (spec 2026-08-27, pillar 3):

- CRITICAL opens (or touches) an incident. The correlation key is the check's
  declared ``alertname`` when it mirrors a core alert, else its ``check_id`` —
  so the Alertmanager webhook and the self-check converge on ONE incident.
- OK auto-resolves ONLY ``self_check``-sourced incidents: the alert's own
  resolved event owns alert-sourced ones (two authorities would race).
- DEGRADED and UNKNOWN neither open nor resolve: degraded is watched, and
  blindness must never invent or clear an outage.
- An alert-sourced incident whose « resolved » delivery was lost is closed by
  reading the SAME authority, never a second one: Alertmanager no longer holds
  its alert as firing, and the webhook has not re-delivered it for longer than
  a firing alert ever stays silent (``reconcile_alert_incidents``). Alertmanager
  unreadable, or restarted too recently to have been told what is firing,
  closes nothing — doubt never resolves an incident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

import structlog

from src.core.constants import ALERTMANAGER_WARMUP_SECONDS
from src.domains.diagnostics.checks import CheckResult, CheckStatus, evidence_for
from src.domains.diagnostics.models import INCIDENT_SOURCE_SELF_CHECK

if TYPE_CHECKING:
    from src.infrastructure.telemetry.models import AlertsResult

logger = structlog.get_logger(__name__)


class IncidentRecorder(Protocol):
    """What the snapshot synchronisation needs from the incident repository."""

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
    ) -> tuple[UUID, bool, datetime | None]: ...

    async def resolve_incident(self, correlation_key: str, *, source: str | None = None) -> int: ...


class SilentIncidentResolver(Protocol):
    """What the reconciliation of lost resolutions needs from the incident repository."""

    async def resolve_silent_alert_incidents(
        self, *, firing_alertnames: set[str], silent_since: datetime, now: datetime
    ) -> list[str]: ...


@dataclass
class IncidentSyncOutcome:
    """What one synchronisation pass did (for logs, metrics, notifications)."""

    opened_ids: list[UUID] = field(default_factory=list)
    opened_keys: list[str] = field(default_factory=list)
    touched: int = 0
    resolved: int = 0


async def sync_incidents_from_results(
    repo: IncidentRecorder,
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


async def reconcile_alert_incidents(
    repo: SilentIncidentResolver,
    firing: AlertsResult,
    *,
    alertmanager_started_at: datetime | None,
    now: datetime,
    silence_close_seconds: int,
) -> list[str]:
    """Close the alert incidents whose alert stopped firing without a word.

    Args:
        repo: Repository bound to the caller's session.
        firing: What Alertmanager holds as firing, suppressed alerts included,
            read BEFORE the caller opened its transaction.
        alertmanager_started_at: When the instance that answered started, read
            after the listing; None when its status could not be read.
        now: The current instant.
        silence_close_seconds: How long an incident must have gone without a
            webhook delivery before its absence from Alertmanager counts.

    Returns:
        The correlation keys resolved; none when Alertmanager was unreadable,
        its start unknown, or its start too recent for its listing to be whole.
    """
    if firing.status != "ok" or alertmanager_started_at is None:
        return []
    up_seconds = (now - alertmanager_started_at).total_seconds()
    if up_seconds < ALERTMANAGER_WARMUP_SECONDS:
        logger.info(
            "diagnostics_alert_reconciliation_deferred",
            reason="alertmanager_warming_up",
            alertmanager_up_seconds=round(up_seconds),
        )
        return []
    resolved = await repo.resolve_silent_alert_incidents(
        firing_alertnames={alert.name for alert in firing.alerts if alert.name},
        silent_since=now - timedelta(seconds=silence_close_seconds),
        now=now,
    )
    if resolved:
        logger.info(
            "diagnostics_alert_incidents_reconciled",
            resolved=len(resolved),
            correlation_keys=sorted(resolved),
        )
    return resolved
