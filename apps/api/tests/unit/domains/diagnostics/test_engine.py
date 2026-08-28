"""Self-check engine — verdicts on synthetic inputs, blindness handling.

The engine must keep working when Prometheus is down (in-process probes still
evaluated, prometheus-backed checks 'unknown') — that exact scenario was live
in dev while this subsystem was designed.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from src.domains.diagnostics import engine as engine_module
from src.domains.diagnostics.checks import PROM_CHECKS, CheckStatus
from src.domains.diagnostics.engine import run_self_check
from src.infrastructure.telemetry.models import PromResult, PromSample


class _FakePromClient:
    """Instant-query stub returning one configured value for every query."""

    def __init__(self, value: float | None = None, unavailable: bool = False) -> None:
        self._value = value
        self._unavailable = unavailable

    async def instant_query(self, promql: str) -> PromResult:
        if self._unavailable:
            return PromResult(status="unavailable", error="transport:ConnectError")
        if self._value is None:
            return PromResult(status="ok", samples=[])
        return PromResult(
            status="ok",
            samples=[PromSample(metric={}, value=self._value, ts=datetime.now(UTC))],
        )


@pytest.fixture
def healthy_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    """All in-process probes report healthy."""

    async def ok_probe() -> tuple[CheckStatus, float | None, str]:
        return CheckStatus.OK, None, ""

    for probe_name in (
        "_probe_database",
        "_probe_redis",
        "_probe_circuit_breakers",
        "_probe_scheduler_tick",
    ):
        monkeypatch.setattr(engine_module, probe_name, ok_probe)


@pytest.mark.unit
class TestEngineWithPrometheus:
    async def test_value_below_warn_is_ok(self, healthy_probes: None) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=0.0))
        prom_results = {r.check_id: r for r in snapshot.results}
        assert prom_results["api_error_rate"].status is CheckStatus.OK
        assert snapshot.overall is CheckStatus.OK

    async def test_value_between_warn_and_crit_is_degraded(self, healthy_probes: None) -> None:
        from src.core.config import settings

        check = next(c for c in PROM_CHECKS if c.check_id == "api_error_rate")
        warn = getattr(settings, check.warn_setting)
        crit = getattr(settings, check.crit_setting)
        between = (warn + crit) / 2
        snapshot = await run_self_check(prom_client=_FakePromClient(value=between))
        result = next(r for r in snapshot.results if r.check_id == "api_error_rate")
        assert result.status is CheckStatus.DEGRADED
        assert result.value == pytest.approx(between)

    async def test_value_at_crit_is_critical_and_overall_follows(
        self, healthy_probes: None
    ) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=10_000.0))
        result = next(r for r in snapshot.results if r.check_id == "api_error_rate")
        assert result.status is CheckStatus.CRITICAL
        assert snapshot.overall is CheckStatus.CRITICAL

    async def test_no_samples_is_unknown_no_data(self, healthy_probes: None) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=None))
        result = next(r for r in snapshot.results if r.check_id == "api_error_rate")
        assert result.status is CheckStatus.UNKNOWN
        assert result.detail == "no_data"

    async def test_nan_sample_is_unknown(self, healthy_probes: None) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=math.nan))
        result = next(r for r in snapshot.results if r.check_id == "api_error_rate")
        assert result.status is CheckStatus.UNKNOWN


@pytest.mark.unit
class TestEngineBlind:
    async def test_prometheus_down_keeps_in_process_probes_alive(
        self, healthy_probes: None
    ) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(unavailable=True))
        by_id = {r.check_id: r for r in snapshot.results}
        for check in PROM_CHECKS:
            assert by_id[check.check_id].status is CheckStatus.UNKNOWN
        assert by_id["database"].status is CheckStatus.OK
        # Blindness alone caps the overall verdict at degraded.
        assert snapshot.overall is CheckStatus.DEGRADED


@pytest.mark.unit
class TestEngineProbeFailures:
    async def test_database_probe_exception_is_critical_without_leaking_message(
        self, monkeypatch: pytest.MonkeyPatch, healthy_probes: None
    ) -> None:
        async def broken_probe() -> tuple[CheckStatus, float | None, str]:
            raise ConnectionError("postgres://user:secret@host says no")

        monkeypatch.setattr(engine_module, "_probe_database", broken_probe)
        snapshot = await run_self_check(prom_client=_FakePromClient(value=0.0))
        result = next(r for r in snapshot.results if r.check_id == "database")
        assert result.status is CheckStatus.CRITICAL
        # Exception class name only: messages can carry hosts or credentials.
        assert result.detail == "ConnectionError"
        assert "secret" not in str(snapshot.to_results_jsonb())


@pytest.mark.unit
class TestSnapshotDTO:
    async def test_results_jsonb_shape_is_plain_and_exact(self, healthy_probes: None) -> None:
        snapshot = await run_self_check(prom_client=_FakePromClient(value=0.0))
        rows = snapshot.to_results_jsonb()
        assert len(rows) == len(snapshot.results)
        for row in rows:
            assert set(row) == {"check_id", "status", "value", "detail", "alertname"}
            assert isinstance(row["status"], str)
