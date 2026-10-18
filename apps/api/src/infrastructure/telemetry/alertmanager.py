"""Alertmanager read client (active alerts and the running instance's start, never raises)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.infrastructure.telemetry._base import TelemetryHTTPBase
from src.infrastructure.telemetry.models import ActiveAlert, AlertsResult, TelemetryStatus


class AlertmanagerStatusResult(BaseModel):
    """When the running Alertmanager started, as its own status endpoint says."""

    status: TelemetryStatus = Field(description="'ok' or 'unavailable' (source never raises).")
    started_at: datetime | None = Field(
        default=None, description="Start of the running instance (aware), when readable."
    )
    error: str | None = Field(default=None, description="Failure reason when unavailable.")


class AlertmanagerClient(TelemetryHTTPBase):
    """Bounded read access to the Alertmanager v2 API."""

    source_name = "alertmanager"

    async def active_alerts(self, *, include_suppressed: bool = False) -> AlertsResult:
        """List currently-firing alerts.

        Args:
            include_suppressed: Also list the firing alerts a silence or an
                inhibition keeps from notifying. A suppressed alert is still
                FIRING: whoever asks « is this still happening? » needs them,
                whoever asks « what is notifying? » does not.

        Returns:
            AlertsResult with status 'ok' and alerts, or 'unavailable'.
        """
        params = {"active": "true"}
        if not include_suppressed:
            params.update({"silenced": "false", "inhibited": "false"})
        reason, payload = await self._guarded_get_json("/api/v2/alerts", params=params)
        if reason is not None:
            return AlertsResult(status="unavailable", error=reason)
        try:
            return AlertsResult(status="ok", alerts=_parse_alerts(payload))
        except KeyError, TypeError, ValueError, AttributeError:
            return AlertsResult(status="unavailable", error="unexpected_shape")

    async def status(self) -> AlertmanagerStatusResult:
        """When the running instance started (``/api/v2/status`` → ``uptime``).

        Alertmanager keeps its alerts in memory: a fresh instance lists nothing
        until Prometheus re-sends what is firing, so whoever reads an ABSENCE
        from the listing must know how long the instance has been up. Only
        ``uptime`` is read; the configuration the same payload carries
        (credentials included) is neither logged nor kept.

        Returns:
            The start instant with status 'ok', or 'unavailable'.
        """
        reason, payload = await self._guarded_get_json("/api/v2/status")
        if reason is not None:
            return AlertmanagerStatusResult(status="unavailable", error=reason)
        started_at = _parse_uptime(payload)
        if started_at is None:
            return AlertmanagerStatusResult(status="unavailable", error="unexpected_shape")
        return AlertmanagerStatusResult(status="ok", started_at=started_at)


def _parse_uptime(payload: Any) -> datetime | None:
    """The aware start instant of a v2 status payload, or None for any other shape.

    Args:
        payload: Decoded JSON body of /api/v2/status (an object).

    Returns:
        The instant ``uptime`` names; None when it is absent, unreadable or
        carries no offset (a naive instant cannot be compared with now).
    """
    try:
        started_at = datetime.fromisoformat(str(payload["uptime"]))
    except KeyError, TypeError, ValueError:
        return None
    return started_at if started_at.tzinfo is not None else None


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
