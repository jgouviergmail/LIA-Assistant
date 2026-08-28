"""Alertmanager read client (active alerts, never raises)."""

from __future__ import annotations

from typing import Any

from src.infrastructure.telemetry._base import TelemetryHTTPBase
from src.infrastructure.telemetry.models import ActiveAlert, AlertsResult


class AlertmanagerClient(TelemetryHTTPBase):
    """Bounded read access to the Alertmanager v2 API."""

    source_name = "alertmanager"

    async def active_alerts(self) -> AlertsResult:
        """List currently-firing alerts.

        Returns:
            AlertsResult with status 'ok' and alerts, or 'unavailable'.
        """
        reason, payload = await self._guarded_get_json(
            "/api/v2/alerts",
            params={"active": "true", "silenced": "false", "inhibited": "false"},
        )
        if reason is not None:
            return AlertsResult(status="unavailable", error=reason)
        try:
            return AlertsResult(status="ok", alerts=_parse_alerts(payload))
        except KeyError, TypeError, ValueError, AttributeError:
            return AlertsResult(status="unavailable", error="unexpected_shape")


def _parse_alerts(payload: Any) -> list[ActiveAlert]:
    """Parse the v2 alerts listing.

    Args:
        payload: Decoded JSON body of /api/v2/alerts (a list).

    Returns:
        Typed active alerts; absent labels/annotations become empty strings.

    Raises:
        KeyError, TypeError, ValueError, AttributeError: On unexpected shapes
            — the caller converts these into an 'unavailable' result.
    """
    alerts: list[ActiveAlert] = []
    for entry in payload:
        labels = entry.get("labels", {})
        annotations = entry.get("annotations", {})
        alerts.append(
            ActiveAlert(
                fingerprint=str(entry["fingerprint"]),
                name=str(labels.get("alertname", "")),
                severity=str(labels.get("severity", "")),
                component=str(labels.get("component", "")),
                starts_at=str(entry.get("startsAt", "")),
                summary=str(annotations.get("summary", "")),
                description=str(annotations.get("description", "")),
                runbook=str(annotations.get("runbook", "")),
            )
        )
    return alerts
