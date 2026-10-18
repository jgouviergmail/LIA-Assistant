"""Diagnostics self-check job — leader tick: snapshot, prune, tick stamp.

The job must be inert when the flag is off, resilient when persistence fails
(error counted, never raised into APScheduler), and must stamp the liveness
tick ONLY after a successful run — a failing loop must trip the staleness
check, never hide behind a partial pass (product_rollup doctrine). No network
wait of the tick — Alertmanager, the evidence pack, the model — runs inside its
session (ADR-304).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from src.core.constants import ALERTMANAGER_WARMUP_SECONDS
from src.domains.diagnostics.checks import CheckResult, CheckStatus
from src.domains.diagnostics.engine import HealthSnapshotDTO
from src.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry
from src.infrastructure.scheduler import diagnostics_self_check as job_module
from src.infrastructure.telemetry.alertmanager import (
    AlertmanagerClient,
    AlertmanagerStatusResult,
)
from src.infrastructure.telemetry.models import AlertsResult


class _FakeRepo:
    """Records repository calls made by the job."""

    def __init__(self, db: object) -> None:
        self.db = db
        _FAKE_REPO_CALLS.append(self)
        self.saved: list[dict[str, object]] = []
        self.pruned_days: int | None = None
        self.diagnosis_limit: int | None = None

    async def save_snapshot(
        self, *, taken_at: datetime, overall: str, results: list[dict[str, object]]
    ) -> object:
        self.saved.append({"taken_at": taken_at, "overall": overall, "results": results})
        return object()

    async def prune_snapshots(self, retention_days: int) -> int:
        self.pruned_days = retention_days
        return 3

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
    ) -> tuple[UUID, bool, datetime | None]:
        return UUID(int=1), True, None

    async def resolve_incident(self, correlation_key: str, *, source: str | None = None) -> int:
        return 0

    async def incidents_needing_diagnosis(self, limit: int) -> list[str]:
        self.diagnosis_limit = limit
        return ["pending-incident"]

    async def resolve_silent_alert_incidents(
        self, *, firing_alertnames: set[str], silent_since: datetime, now: datetime
    ) -> list[str]:
        self.reconciled: tuple[set[str], datetime, datetime] = (
            firing_alertnames,
            silent_since,
            now,
        )
        return ["ContainerMemoryNearLimit"]


_FAKE_REPO_CALLS: list[_FakeRepo] = []


def _dto(status: CheckStatus = CheckStatus.OK) -> HealthSnapshotDTO:
    return HealthSnapshotDTO(
        taken_at=datetime.now(UTC),
        results=[
            CheckResult(check_id="database", status=status, value=None, detail="", alertname=None)
        ],
    )


@pytest.fixture
def wired_job(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Wire the job onto fakes; returns the recording surfaces."""
    _FAKE_REPO_CALLS.clear()
    state: dict[str, Any] = {"engine_calls": 0, "redis": AsyncMock(), "events": []}

    async def fake_run_self_check(prom_client: object = None) -> HealthSnapshotDTO:
        state["engine_calls"] += 1
        return _dto()

    @asynccontextmanager
    async def fake_db_context() -> AsyncIterator[AsyncMock]:
        state["events"].append("session_opened")
        session = AsyncMock()
        # A SAVEPOINT is a sync call returning an async context manager.
        session.begin_nested = MagicMock(side_effect=nullcontext)
        try:
            yield session
        finally:
            state["events"].append("session_closed")

    async def fake_get_redis() -> AsyncMock:
        redis: AsyncMock = state["redis"]
        return redis

    class FakeAlertmanager:
        def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
            state["am_base_url"] = base_url

        async def active_alerts(self, *, include_suppressed: bool = False) -> AlertsResult:
            state["events"].append("alertmanager_read")
            state["include_suppressed"] = include_suppressed
            firing: AlertsResult = state.get("firing", AlertsResult(status="ok", alerts=[]))
            return firing

        async def status(self) -> AlertmanagerStatusResult:
            state["events"].append("alertmanager_status")
            started_at = state.get("am_started_at", datetime.now(UTC) - timedelta(days=1))
            return AlertmanagerStatusResult(status="ok", started_at=started_at)

    async def fake_diagnose(incidents: list[str], *, system_prompt: str) -> int:
        state["events"].append("pump")
        state["diagnosed"] = list(incidents)
        state["diagnosis_prompt"] = system_prompt
        return len(incidents)

    # The pump is doubled, and that is the point rather than a convenience.
    # Left real it built its own `DiagnosticsRepository` over this test's
    # AsyncMock session, queried it, and had the failure swallowed by the job's
    # own `except Exception` — so the test passed while asserting nothing about
    # the pump, and leaked an un-awaited coroutine for the F028 guard to find.
    # Doubled, the JOB's contract becomes assertable: it hands the pending
    # incidents over with an unresolved `{language}`.
    monkeypatch.setattr(job_module, "diagnose_incidents", fake_diagnose)
    monkeypatch.setattr(job_module, "run_self_check", fake_run_self_check)
    monkeypatch.setattr(job_module, "get_db_context", fake_db_context)
    monkeypatch.setattr(job_module, "get_redis_cache", fake_get_redis)
    monkeypatch.setattr(job_module, "DiagnosticsRepository", _FakeRepo)
    monkeypatch.setattr(job_module, "AlertmanagerClient", FakeAlertmanager)
    return state


@pytest.mark.unit
class TestSelfCheckJob:
    async def test_flag_off_is_inert(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", False)
        await job_module.run_diagnostics_self_check()
        assert wired_job["engine_calls"] == 0
        assert _FAKE_REPO_CALLS == []

    async def test_nominal_tick_persists_prunes_and_stamps(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)
        await job_module.run_diagnostics_self_check()
        assert wired_job["engine_calls"] == 1
        repo = _FAKE_REPO_CALLS[0]
        assert repo.saved and repo.saved[0]["overall"] == CheckStatus.OK.value
        assert repo.pruned_days == job_module.settings.diagnostics_snapshot_retention_days
        # Liveness tick stamped with a TTL after the successful run.
        wired_job["redis"].set.assert_awaited_once()
        _, kwargs = wired_job["redis"].set.await_args
        assert kwargs.get("ex") is not None

        # The pump received the pending incidents, with `{language}` still
        # unresolved: the job resolves `{max_actions}` and leaves the language
        # to the batch, which writes one variant per administrator language.
        assert wired_job["diagnosed"] == ["pending-incident"]
        prompt = wired_job["diagnosis_prompt"]
        assert "{language}" in prompt
        assert "{max_actions}" not in prompt

    async def test_critical_result_opens_incident_and_notifies(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)

        async def critical_check(prom_client: object = None) -> HealthSnapshotDTO:
            return HealthSnapshotDTO(
                taken_at=datetime.now(UTC),
                results=[
                    CheckResult(
                        check_id="redis",
                        status=CheckStatus.CRITICAL,
                        value=None,
                        detail="ConnectionError",
                        alertname="RedisDown",
                    )
                ],
            )

        monkeypatch.setattr(job_module, "run_self_check", critical_check)
        opened_id = UUID("11111111-1111-1111-1111-111111111111")
        notified: list[dict[str, object]] = []

        from src.domains.diagnostics.incident_sync import IncidentSyncOutcome

        async def fake_sync(repo: object, results: list[CheckResult]) -> IncidentSyncOutcome:
            outcome = IncidentSyncOutcome()
            outcome.opened_ids.append(opened_id)
            outcome.opened_keys.append("RedisDown")
            return outcome

        async def fake_notify(
            *, incident_id: UUID, correlation_key: str, severity: str, title: str, db: object
        ) -> int:
            notified.append({"incident_id": incident_id, "correlation_key": correlation_key})
            return 1

        monkeypatch.setattr(job_module, "sync_incidents_from_results", fake_sync)
        monkeypatch.setattr(job_module, "notify_admins_of_incident", fake_notify)
        await job_module.run_diagnostics_self_check()
        assert notified and notified[0]["correlation_key"] == "RedisDown"
        assert notified[0]["incident_id"] == opened_id

    async def test_diagnosis_pump_runs_on_the_tick(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)
        pumped: list[list[str]] = []

        async def fake_pump(incidents: list[str], *, system_prompt: str) -> int:
            assert system_prompt  # the job loads and injects the versioned prompt
            pumped.append(incidents)
            return len(incidents)

        monkeypatch.setattr(job_module, "diagnose_incidents", fake_pump)
        await job_module.run_diagnostics_self_check()
        assert pumped == [["pending-incident"]]
        repo = _FAKE_REPO_CALLS[0]
        assert repo.diagnosis_limit == job_module.settings.diagnostics_diagnosis_batch_size

    async def test_pump_failure_does_not_break_the_tick(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)

        async def broken_pump(incidents: list[str], *, system_prompt: str) -> int:
            raise RuntimeError("llm down")

        monkeypatch.setattr(job_module, "diagnose_incidents", broken_pump)
        await job_module.run_diagnostics_self_check()  # must not raise
        # The tick still stamps liveness: diagnosis is best-effort by design.
        wired_job["redis"].set.assert_awaited()

    async def test_persistence_failure_is_counted_never_raised(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)

        async def broken_save(**_: object) -> object:
            raise RuntimeError("db down")

        monkeypatch.setattr(_FakeRepo, "save_snapshot", staticmethod(broken_save))
        await job_module.run_diagnostics_self_check()  # must not raise
        # A failed run must NOT stamp the liveness tick.
        wired_job["redis"].set.assert_not_awaited()


@pytest.mark.unit
class TestNoNetworkWaitHoldsTheTicksSession:
    """ADR-304: the pending-incidents read used to open a transaction that the
    pump then held across Prometheus, Loki and every model call of the batch."""

    async def test_the_pump_runs_after_the_session_closed(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)

        await job_module.run_diagnostics_self_check()

        assert wired_job["events"] == [
            "alertmanager_read",
            "alertmanager_status",
            "session_opened",
            "session_closed",
            "pump",
        ]

    async def test_no_pending_incident_calls_no_pump(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)

        async def nothing_pending(self: _FakeRepo, limit: int) -> list[str]:
            return []

        monkeypatch.setattr(_FakeRepo, "incidents_needing_diagnosis", nothing_pending)
        await job_module.run_diagnostics_self_check()

        assert "pump" not in wired_job["events"]
        wired_job["redis"].set.assert_awaited_once()


@pytest.fixture
def clean_breakers() -> Iterator[None]:
    """The real Alertmanager client goes through a process-wide circuit breaker."""
    CircuitBreakerRegistry.clear()
    yield
    CircuitBreakerRegistry.clear()


@pytest.mark.unit
class TestTheTickClosesIncidentsWhoseResolutionWasLost:
    async def test_alertmanager_is_read_before_the_transaction_opens(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A network wait never holds a session (ADR-304)."""
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)
        await job_module.run_diagnostics_self_check()
        events = wired_job["events"]
        assert events.index("alertmanager_read") < events.index("alertmanager_status")
        assert events.index("alertmanager_status") < events.index("session_opened")
        assert wired_job["include_suppressed"] is True, "a silenced alert is still firing"
        assert wired_job["am_base_url"] == job_module.settings.diagnostics_alertmanager_url

    async def test_the_reconciliation_runs_with_the_configured_silence(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)
        await job_module.run_diagnostics_self_check()
        firing_alertnames, silent_since, now = _FAKE_REPO_CALLS[0].reconciled
        assert (now - silent_since).total_seconds() == (
            job_module.settings.diagnostics_incident_silence_close_seconds
        )
        assert firing_alertnames == set()

    async def test_an_unreadable_alertmanager_closes_nothing(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)
        wired_job["firing"] = AlertsResult(status="unavailable", error="ConnectError")
        await job_module.run_diagnostics_self_check()
        assert not hasattr(_FAKE_REPO_CALLS[0], "reconciled")
        assert "alertmanager_status" not in wired_job["events"]
        # The tick itself still succeeds: liveness stamped.
        wired_job["redis"].set.assert_awaited_once()

    async def test_a_just_restarted_alertmanager_closes_nothing(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Its alerts live in memory: until Prometheus re-sends them, the
        listing is empty, and a silenced alert gets no webhook to reopen it."""
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)
        wired_job["am_started_at"] = datetime.now(UTC) - timedelta(
            seconds=ALERTMANAGER_WARMUP_SECONDS / 5
        )

        await job_module.run_diagnostics_self_check()

        assert not hasattr(_FAKE_REPO_CALLS[0], "reconciled")
        assert _FAKE_REPO_CALLS[0].saved
        wired_job["redis"].set.assert_awaited_once()

    async def test_a_malformed_alertmanager_url_costs_the_tick_nothing(
        self,
        wired_job: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        clean_breakers: None,
    ) -> None:
        """`httpx.InvalidURL` is no `httpx.HTTPError`: it escaped the client and
        killed every tick before the snapshot was saved."""
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)
        monkeypatch.setattr(job_module, "AlertmanagerClient", AlertmanagerClient)
        monkeypatch.setattr(
            job_module.settings, "diagnostics_alertmanager_url", "http://alertmanager:90x3"
        )

        await job_module.run_diagnostics_self_check()

        repo = _FAKE_REPO_CALLS[0]
        assert repo.saved, "the snapshot is persisted"
        assert not hasattr(repo, "reconciled"), "an unreadable Alertmanager closes nothing"
        wired_job["redis"].set.assert_awaited_once()

    async def test_a_status_read_that_raises_closes_nothing(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)

        async def raising_status(self: object) -> AlertmanagerStatusResult:
            raise RuntimeError("client fault")

        monkeypatch.setattr(job_module.AlertmanagerClient, "status", raising_status)

        await job_module.run_diagnostics_self_check()

        assert not hasattr(_FAKE_REPO_CALLS[0], "reconciled")
        wired_job["redis"].set.assert_awaited_once()

    async def test_a_failed_reconciliation_costs_the_tick_nothing_else(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Measured on dev: an unbindable statement once failed the whole tick."""
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)

        async def broken(
            repo: object,
            firing: AlertsResult,
            *,
            alertmanager_started_at: datetime | None,
            now: datetime,
            silence_close_seconds: int,
        ) -> list[str]:
            raise RuntimeError("statement refused")

        monkeypatch.setattr(job_module, "reconcile_alert_incidents", broken)
        await job_module.run_diagnostics_self_check()
        repo = _FAKE_REPO_CALLS[0]
        assert repo.saved, "the snapshot is still persisted"
        wired_job["redis"].set.assert_awaited_once()
