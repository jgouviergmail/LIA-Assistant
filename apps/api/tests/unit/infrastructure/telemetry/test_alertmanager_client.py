"""AlertmanagerClient — active alerts listing that never raises."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
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


def _transport_recording(seen: list[dict[str, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, content=json.dumps(_ALERTS_PAYLOAD).encode())

    return httpx.MockTransport(handler)


@pytest.mark.unit
class TestWhichAlertsAreAskedFor:
    """« What is notifying? » and « is this still firing? » are two questions."""

    async def test_by_default_suppressed_alerts_are_left_out(self) -> None:
        seen: list[dict[str, str]] = []
        client = AlertmanagerClient(
            base_url="http://alertmanager:9093",
            timeout_seconds=2.0,
            transport=_transport_recording(seen),
        )
        await client.active_alerts()
        assert seen == [{"active": "true", "silenced": "false", "inhibited": "false"}]

    async def test_a_silenced_or_inhibited_alert_is_still_firing(self) -> None:
        seen: list[dict[str, str]] = []
        client = AlertmanagerClient(
            base_url="http://alertmanager:9093",
            timeout_seconds=2.0,
            transport=_transport_recording(seen),
        )
        result = await client.active_alerts(include_suppressed=True)
        assert seen == [{"active": "true"}]
        assert result.status == "ok"


#: The v2 status payload, trimmed — the real one also carries the whole
#: configuration (SMTP credentials included), which the client never reads.
_STATUS_PAYLOAD = {
    "cluster": {"name": "01J", "peers": [], "status": "ready"},
    "config": {"original": "global:\n  smtp_from: alerts@example.org\n"},
    "uptime": "2026-10-18T06:00:01.123456789Z",
    "versionInfo": {"version": "0.27.0"},
}


@pytest.mark.unit
class TestWhenTheRunningAlertmanagerStarted:
    """Its alerts live in memory: whoever reads an absence must date the listing."""

    async def test_the_uptime_is_the_instant_the_instance_started(self) -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, content=json.dumps(_STATUS_PAYLOAD).encode())

        client = AlertmanagerClient(
            base_url="http://alertmanager:9093",
            timeout_seconds=2.0,
            transport=httpx.MockTransport(handler),
        )

        result = await client.status()

        assert paths == ["/api/v2/status"]
        assert result.status == "ok"
        assert result.started_at == datetime(2026, 10, 18, 6, 0, 1, 123456, tzinfo=UTC)

    @pytest.mark.parametrize(
        "payload",
        [
            {"cluster": {}},
            {"uptime": "not a date"},
            {"uptime": "2026-10-18T06:00:01"},
            ["not", "an", "object"],
        ],
    )
    async def test_an_undatable_payload_is_unavailable(self, payload: object) -> None:
        client = AlertmanagerClient(
            base_url="http://alertmanager:9093",
            timeout_seconds=2.0,
            transport=transport_returning(payload),
        )

        result = await client.status()

        assert result.status == "unavailable"
        assert result.error == "unexpected_shape"
        assert result.started_at is None

    async def test_a_backend_down_or_disabled_is_unavailable(self) -> None:
        down = AlertmanagerClient(
            base_url="http://alertmanager:9093",
            timeout_seconds=2.0,
            transport=transport_raising(httpx.ConnectError("down")),
        )
        disabled = AlertmanagerClient(base_url="", timeout_seconds=2.0)

        assert (await down.status()).status == "unavailable"
        assert (await disabled.status()).error == "disabled"
