"""Diagnostics self-check job — leader tick: snapshot, prune, tick stamp.

The job must be inert when the flag is off, resilient when persistence fails
(error counted, never raised into APScheduler), and must stamp the liveness
tick ONLY after a successful run — a failing loop must trip the staleness
check, never hide behind a partial pass (product_rollup doctrine).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.diagnostics.checks import CheckResult, CheckStatus
from src.domains.diagnostics.engine import HealthSnapshotDTO
from src.infrastructure.scheduler import diagnostics_self_check as job_module


class _FakeRepo:
    """Records repository calls made by the job."""

    def __init__(self, db: Any) -> None:
        self.db = db
        _FAKE_REPO_CALLS.append(self)
        self.saved: list[dict[str, Any]] = []
        self.pruned_days: int | None = None

    async def save_snapshot(self, *, taken_at: Any, overall: str, results: Any) -> Any:
        self.saved.append({"taken_at": taken_at, "overall": overall, "results": results})
        return object()

    async def prune_snapshots(self, retention_days: int) -> int:
        self.pruned_days = retention_days
        return 3

    async def open_or_touch_incident(self, **kwargs: Any) -> tuple[Any, bool, Any]:
        return "id", True, None

    async def resolve_incident(self, correlation_key: str, **_: Any) -> int:
        return 0

    async def incidents_needing_diagnosis(self, limit: int) -> list[Any]:
        self.diagnosis_limit = limit
        return ["pending-incident"]


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
    state: dict[str, Any] = {"engine_calls": 0, "redis": AsyncMock()}

    async def fake_run_self_check(prom_client: Any = None) -> HealthSnapshotDTO:
        state["engine_calls"] += 1
        return _dto()

    @asynccontextmanager
    async def fake_db_context() -> Any:
        session = AsyncMock()
        yield session

    async def fake_get_redis() -> Any:
        return state["redis"]

    async def fake_diagnose(incidents: Any, *, db: Any, system_prompt: str) -> int:
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

        async def critical_check(prom_client: Any = None) -> HealthSnapshotDTO:
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
        opened_id = "11111111-1111-1111-1111-111111111111"
        notified: list[dict[str, Any]] = []

        from src.domains.diagnostics.incident_sync import IncidentSyncOutcome

        async def fake_sync(repo: Any, results: Any) -> IncidentSyncOutcome:
            outcome = IncidentSyncOutcome()
            outcome.opened_ids.append(opened_id)  # type: ignore[arg-type]
            outcome.opened_keys.append("RedisDown")
            return outcome

        async def fake_notify(**kwargs: Any) -> int:
            notified.append(kwargs)
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
        pumped: list[Any] = []

        async def fake_pump(incidents: Any, *, db: Any, system_prompt: str) -> int:
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

        async def broken_pump(incidents: Any, *, db: Any, system_prompt: str) -> int:
            raise RuntimeError("llm down")

        monkeypatch.setattr(job_module, "diagnose_incidents", broken_pump)
        await job_module.run_diagnostics_self_check()  # must not raise
        # The tick still stamps liveness: diagnosis is best-effort by design.
        wired_job["redis"].set.assert_awaited()

    async def test_persistence_failure_is_counted_never_raised(
        self, wired_job: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(job_module.settings, "diagnostics_enabled", True)

        async def broken_save(**_: Any) -> Any:
            raise RuntimeError("db down")

        monkeypatch.setattr(_FakeRepo, "save_snapshot", staticmethod(broken_save))
        await job_module.run_diagnostics_self_check()  # must not raise
        # A failed run must NOT stamp the liveness tick.
        wired_job["redis"].set.assert_not_awaited()
