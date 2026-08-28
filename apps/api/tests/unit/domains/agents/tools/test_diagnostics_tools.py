"""Diagnostics chat tools — admin-gated, bounded, honest about truncation.

Every tool: non-admin gets the devops-style FORBIDDEN failure; inputs the
builders reject become INVALID_INPUT (never exceptions); shown counts are
exact and a hit cap is stated, never applied in silence.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.domains.agents.tools import diagnostics_tools
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.telemetry.models import (
    ActiveAlert,
    AlertsResult,
    LokiLine,
    LokiResult,
    PromResult,
    PromSample,
)


def _runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.config = {
        "configurable": {
            "user_id": "8a7b6c5d-0000-0000-0000-0000000000aa",
            "thread_id": "thread-1",
        }
    }
    runtime.store = MagicMock()
    return runtime


class _FakeRepo:
    """Repository stub configured through class attributes."""

    latest: Any = None
    incidents: tuple[list[Any], int] = ([], 0)
    incident_detail: Any = None

    def __init__(self, db: Any) -> None:
        self.db = db

    async def latest_snapshot(self) -> Any:
        return type(self).latest

    async def list_incidents(self, **_: Any) -> tuple[list[Any], int]:
        return type(self).incidents

    async def get_incident(self, incident_id: Any) -> Any:
        return type(self).incident_detail


@pytest.fixture
def admin_wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Admin user + fake persistence + fake telemetry clients."""

    async def is_admin(user_id: str) -> bool:
        return True

    @asynccontextmanager
    async def fake_db() -> Any:
        yield MagicMock()

    state: dict[str, Any] = {}
    monkeypatch.setattr(diagnostics_tools, "user_is_superuser", is_admin)
    monkeypatch.setattr(diagnostics_tools, "get_db_context", fake_db)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsRepository", _FakeRepo)
    _FakeRepo.latest = None
    _FakeRepo.incidents = ([], 0)
    _FakeRepo.incident_detail = None
    return state


@pytest.mark.unit
class TestAdminGateOnEveryTool:
    @pytest.mark.parametrize(
        "invoke",
        [
            lambda rt: diagnostics_tools.platform_health_tool.coroutine(runtime=rt),
            lambda rt: diagnostics_tools.platform_metrics_tool.coroutine(
                query_key="api_error_rate", runtime=rt
            ),
            lambda rt: diagnostics_tools.platform_logs_tool.coroutine(service="api", runtime=rt),
            lambda rt: diagnostics_tools.platform_incidents_tool.coroutine(runtime=rt),
        ],
    )
    async def test_non_admin_is_forbidden(
        self, monkeypatch: pytest.MonkeyPatch, invoke: Any
    ) -> None:
        async def not_admin(user_id: str) -> bool:
            return False

        monkeypatch.setattr(diagnostics_tools, "user_is_superuser", not_admin)
        result = await invoke(_runtime())
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "FORBIDDEN"


@pytest.mark.unit
class TestPlatformHealthTool:
    async def test_nominal_health_payload(
        self, admin_wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tool delegates to service.build_overview (one implementation)."""
        from src.domains.diagnostics import service as service_module

        snapshot = MagicMock()
        snapshot.taken_at = datetime.now(UTC)
        snapshot.overall = "degraded"
        snapshot.results = [{"check_id": "redis", "status": "critical"}]
        _FakeRepo.latest = snapshot
        _FakeRepo.incidents = ([], 2)

        class _FakeAlerts:
            def __init__(self, **_: Any) -> None: ...

            async def active_alerts(self) -> AlertsResult:
                return AlertsResult(
                    status="ok",
                    alerts=[ActiveAlert(fingerprint="f1", name="RedisDown", severity="critical")],
                )

        async def no_degradations() -> list[Any]:
            return []

        monkeypatch.setattr(service_module, "DiagnosticsRepository", _FakeRepo)
        monkeypatch.setattr(service_module, "AlertmanagerClient", _FakeAlerts)
        monkeypatch.setattr(service_module, "get_active_degradations", no_degradations)
        result = await diagnostics_tools.platform_health_tool.coroutine(runtime=_runtime())
        assert result.success is True
        data = result.structured_data
        assert data["overall"] == "degraded"
        assert data["open_incidents"] == 2
        assert data["active_alerts"][0]["name"] == "RedisDown"

    async def test_no_snapshot_yet_is_honest(
        self, admin_wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.diagnostics import service as service_module

        class _DownAlerts:
            def __init__(self, **_: Any) -> None: ...

            async def active_alerts(self) -> AlertsResult:
                return AlertsResult(status="unavailable", error="disabled")

        async def no_degradations() -> list[Any]:
            return []

        monkeypatch.setattr(service_module, "DiagnosticsRepository", _FakeRepo)
        monkeypatch.setattr(service_module, "AlertmanagerClient", _DownAlerts)
        monkeypatch.setattr(service_module, "get_active_degradations", no_degradations)
        result = await diagnostics_tools.platform_health_tool.coroutine(runtime=_runtime())
        assert result.success is True
        assert result.structured_data["snapshot_available"] is False
        assert result.structured_data["alertmanager"] == "unavailable"


@pytest.mark.unit
class TestPlatformMetricsTool:
    async def test_unknown_key_is_invalid_input_and_counted(
        self, admin_wired: dict[str, Any]
    ) -> None:
        from src.infrastructure.observability.metrics_diagnostics import (
            diagnostics_catalogue_miss_total,
        )

        before = diagnostics_catalogue_miss_total.labels(surface="chat_tool")._value.get()
        result = await diagnostics_tools.platform_metrics_tool.coroutine(
            query_key="nope", runtime=_runtime()
        )
        assert result.success is False
        assert result.error_code == "INVALID_INPUT"
        assert "api_error_rate" in result.message  # available keys are published
        after = diagnostics_catalogue_miss_total.labels(surface="chat_tool")._value.get()
        assert after == before + 1

    async def test_nominal_query(
        self, admin_wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _FakeProm:
            def __init__(self, **_: Any) -> None: ...

            async def instant_query(self, promql: str) -> PromResult:
                return PromResult(
                    status="ok",
                    samples=[PromSample(metric={"le": "x"}, value=1.5, ts=datetime.now(UTC))],
                )

        monkeypatch.setattr(diagnostics_tools, "PrometheusClient", _FakeProm)
        result = await diagnostics_tools.platform_metrics_tool.coroutine(
            query_key="api_error_rate", window_minutes=30, runtime=_runtime()
        )
        assert result.success is True
        assert result.structured_data["samples"][0]["value"] == 1.5
        assert result.structured_data["unit"] == "percent"

    async def test_source_unavailable_is_failure_not_exception(
        self, admin_wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _DownProm:
            def __init__(self, **_: Any) -> None: ...

            async def instant_query(self, promql: str) -> PromResult:
                return PromResult(status="unavailable", error="circuit_open")

        monkeypatch.setattr(diagnostics_tools, "PrometheusClient", _DownProm)
        result = await diagnostics_tools.platform_metrics_tool.coroutine(
            query_key="api_error_rate", runtime=_runtime()
        )
        assert result.success is False
        assert result.error_code == "UNAVAILABLE"


@pytest.mark.unit
class TestPlatformLogsTool:
    async def test_invalid_event_is_invalid_input(self, admin_wired: dict[str, Any]) -> None:
        result = await diagnostics_tools.platform_logs_tool.coroutine(
            service="api", event='x"} |= "boom', runtime=_runtime()
        )
        assert result.success is False
        assert result.error_code == "INVALID_INPUT"

    async def test_unknown_service_is_invalid_input(self, admin_wired: dict[str, Any]) -> None:
        result = await diagnostics_tools.platform_logs_tool.coroutine(
            service="mainframe", runtime=_runtime()
        )
        assert result.success is False
        assert result.error_code == "INVALID_INPUT"

    async def test_nominal_lines_with_exact_counts(
        self, admin_wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _FakeLoki:
            def __init__(self, **_: Any) -> None: ...

            async def query_range(self, logql: str, **_: Any) -> LokiResult:
                return LokiResult(
                    status="ok",
                    lines=[
                        LokiLine(
                            ts=datetime.now(UTC),
                            container="lia-api-prod",
                            level="error",
                            payload={"event": "boom", "logger": "src.x"},
                            raw="{}",
                        )
                    ],
                )

        monkeypatch.setattr(diagnostics_tools, "LokiClient", _FakeLoki)
        result = await diagnostics_tools.platform_logs_tool.coroutine(
            service="api", level="error", minutes=30, limit=50, runtime=_runtime()
        )
        assert result.success is True
        data = result.structured_data
        assert data["count"] == 1
        assert data["truncated"] is False
        assert data["lines"][0]["event"] == "boom"


@pytest.mark.unit
class TestPlatformIncidentsTool:
    async def test_list_mode_reports_exact_total(self, admin_wired: dict[str, Any]) -> None:
        incident = MagicMock()
        incident.id = "00000000-0000-0000-0000-000000000001"
        incident.correlation_key = "RedisDown"
        incident.severity = "critical"
        incident.status = "open"
        incident.title = "Redis is down"
        incident.opened_at = datetime.now(UTC)
        incident.last_seen_at = datetime.now(UTC)
        incident.diagnosis = None
        _FakeRepo.incidents = ([incident], 7)
        result = await diagnostics_tools.platform_incidents_tool.coroutine(runtime=_runtime())
        assert result.success is True
        assert result.structured_data["total"] == 7
        assert result.structured_data["incidents"][0]["correlation_key"] == "RedisDown"

    async def test_detail_mode_unknown_id_is_not_found(self, admin_wired: dict[str, Any]) -> None:
        result = await diagnostics_tools.platform_incidents_tool.coroutine(
            incident_id="00000000-0000-0000-0000-00000000dead", runtime=_runtime()
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    async def test_detail_mode_bad_uuid_is_invalid_input(self, admin_wired: dict[str, Any]) -> None:
        result = await diagnostics_tools.platform_incidents_tool.coroutine(
            incident_id="not-a-uuid", runtime=_runtime()
        )
        assert result.success is False
        assert result.error_code == "INVALID_INPUT"
