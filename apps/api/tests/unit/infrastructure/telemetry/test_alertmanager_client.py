"""AlertmanagerClient — active alerts listing that never raises."""

from __future__ import annotations

import pytest

from src.infrastructure.telemetry.alertmanager import AlertmanagerClient
from tests.unit.infrastructure.telemetry.conftest import (
    transport_raising,
    transport_returning,
    transport_returning_text,
)

_ALERTS_PAYLOAD = [
    {
        "fingerprint": "abc123",
        "labels": {
            "alertname": "RedisDown",
            "severity": "critical",
            "component": "redis",
        },
        "annotations": {
            "summary": "Redis is down",
            "description": "redis-exporter unreachable",
            "runbook": "docs/runbooks/alerts/RedisDown.md",
        },
        "startsAt": "2026-08-27T10:00:00.000Z",
        "status": {"state": "active"},
    },
    {
        # Degenerate alert: no annotations at all — parse must not fail.
        "fingerprint": "def456",
        "labels": {"alertname": "HighCPUUsage"},
        "annotations": {},
        "startsAt": "2026-08-27T11:00:00.000Z",
        "status": {"state": "active"},
    },
]


@pytest.mark.unit
class TestAlertmanagerClient:
    async def test_nominal_parse(self) -> None:
        client = AlertmanagerClient(
            base_url="http://alertmanager:9093",
            timeout_seconds=2.0,
            transport=transport_returning(_ALERTS_PAYLOAD),
        )
        result = await client.active_alerts()
        assert result.status == "ok"
        assert len(result.alerts) == 2
        alert = result.alerts[0]
        assert alert.fingerprint == "abc123"
        assert alert.name == "RedisDown"
        assert alert.severity == "critical"
        assert alert.component == "redis"
        assert alert.runbook == "docs/runbooks/alerts/RedisDown.md"
        degenerate = result.alerts[1]
        assert degenerate.severity == ""
        assert degenerate.summary == ""

    async def test_backend_down_is_unavailable(self) -> None:
        import httpx

        client = AlertmanagerClient(
            base_url="http://alertmanager:9093",
            timeout_seconds=2.0,
            transport=transport_raising(httpx.ConnectError("down")),
        )
        result = await client.active_alerts()
        assert result.status == "unavailable"
        assert result.alerts == []

    async def test_malformed_body_is_unavailable(self) -> None:
        client = AlertmanagerClient(
            base_url="http://alertmanager:9093",
            timeout_seconds=2.0,
            transport=transport_returning_text("nope"),
        )
        result = await client.active_alerts()
        assert result.status == "unavailable"

    async def test_empty_base_url_means_disabled_source(self) -> None:
        client = AlertmanagerClient(base_url="", timeout_seconds=2.0)
        result = await client.active_alerts()
        assert result.status == "unavailable"
        assert result.error == "disabled"
