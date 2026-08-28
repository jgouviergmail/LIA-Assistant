"""Alertmanager → incident webhook (internal, shared-secret gated).

Security contract (spec 2026-08-27, §6): the endpoint DOES NOT EXIST (404)
while the feature flag is off or the secret is unset — the webhook can never
run unauthenticated; a wrong secret is a 403 after a constant-time compare.
No LLM work happens here (the diagnosis pump is pull-based, on the leader
job): the handler only opens/resolves incidents and fans out the admin
notification, each guarded so a broken side effect never fails the delivery.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Header

from src.core.config import settings
from src.core.exceptions import raise_not_found_or_unauthorized, raise_permission_denied
from src.domains.diagnostics.notifications import notify_admins_of_incident
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.domains.diagnostics.schemas import (
    AlertmanagerWebhookPayload,
    WebhookAlert,
    WebhookOutcome,
)
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/internal/diagnostics", tags=["diagnostics-internal"])

#: The secret travels as ``Authorization: Bearer <secret>`` — Alertmanager's
#: ``http_config.authorization`` emits exactly that, and (unlike custom
#: headers) it is supported by every Alertmanager version we ship.
_BEARER_PREFIX = "Bearer "


@router.post("/alert-webhook", response_model=WebhookOutcome)
async def alert_webhook(
    payload: AlertmanagerWebhookPayload,
    authorization: str | None = Header(default=None),
) -> WebhookOutcome:
    """Ingest one Alertmanager webhook delivery into the incident memory.

    Firing alerts open (or touch) incidents keyed by alertname; resolved
    alerts resolve them regardless of which source opened them (the outage
    ended). Alerts without an alertname are skipped — a nameless alert has no
    correlation identity and inventing one would corrupt deduplication.

    Args:
        payload: Alertmanager v4 webhook body.
        authorization: ``Bearer <shared secret>`` header.

    Returns:
        Exact counts of incidents opened and resolved by this delivery.
    """
    configured_secret = settings.diagnostics_webhook_secret
    if not getattr(settings, "diagnostics_enabled", False) or not configured_secret:
        raise_not_found_or_unauthorized(resource_type="route")
    presented = ""
    if authorization and authorization.startswith(_BEARER_PREFIX):
        presented = authorization[len(_BEARER_PREFIX) :]
    if not presented or not secrets.compare_digest(presented, configured_secret):
        raise_permission_denied(action="deliver", resource_type="diagnostics_webhook")

    opened = 0
    resolved = 0
    async with get_db_context() as db:
        repo = DiagnosticsRepository(db)
        for alert in payload.alerts:
            alertname = alert.labels.get("alertname", "")
            if not alertname:
                logger.debug("diagnostics_webhook_nameless_alert_skipped")
                continue
            if alert.status == "resolved":
                resolved += await repo.resolve_incident(alertname)
            else:
                opened += await _ingest_firing_alert(repo, db, alert, alertname)
        await db.commit()

    logger.info("diagnostics_webhook_processed", opened=opened, resolved=resolved)
    return WebhookOutcome(opened=opened, resolved=resolved)


async def _ingest_firing_alert(
    repo: DiagnosticsRepository,
    db: AsyncSession,
    alert: WebhookAlert,
    alertname: str,
) -> int:
    """Open (or touch) the incident for one firing alert; notify on creation.

    Args:
        repo: Repository bound to the webhook's session.
        db: The session (passed through to the notification fan-out).
        alert: The firing alert entry.
        alertname: Its non-empty alertname (the correlation key).

    Returns:
        1 when a new incident was opened, 0 on a touch.
    """
    annotations = alert.annotations
    severity = alert.labels.get("severity", "critical")
    title = annotations.get("summary", alertname)[:255]
    incident_id, created, _ = await repo.open_or_touch_incident(
        correlation_key=alertname,
        source="alert",
        severity=severity,
        title=title,
        alertname=alertname,
        fingerprint=alert.fingerprint or None,
        evidence={
            "summary": annotations.get("summary", ""),
            "description": annotations.get("description", ""),
            "runbook": annotations.get("runbook", ""),
            "component": alert.labels.get("component", ""),
        },
    )
    if not created:
        return 0
    from src.infrastructure.observability.metrics_diagnostics import (
        diagnostics_incidents_total,
    )

    diagnostics_incidents_total.labels(source="alert", severity=severity).inc()
    if severity == "critical":
        try:
            await notify_admins_of_incident(
                incident_id=incident_id,
                correlation_key=alertname,
                severity="critical",
                title=title,
                db=db,
            )
        except Exception:
            # Notification is best-effort: a broken push channel must never
            # fail the alert delivery itself.
            logger.exception("diagnostics_webhook_notify_failed", alertname=alertname)
    return 1
