"""Budgeted LLM diagnosis pump — pull-based, resumable, injection-safe.

Contracts under test: the daily USD cap gates BEFORE any LLM call (0 disables
the step entirely); a skipped incident keeps ``diagnosis`` NULL so tomorrow's
pump retries it; the runbook loader refuses path-traversal-shaped alertnames
and caps the excerpt; spend is recorded through one atomic INCRBYFLOAT.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.diagnostics import diagnosis as diag_module
from src.domains.diagnostics.diagnosis import DiagnosisOutput


def _incident(alertname: str | None = "RedisDown") -> MagicMock:
    incident = MagicMock()
    incident.id = uuid4()
    incident.correlation_key = alertname or "scheduler_tick"
    incident.alertname = alertname
    incident.severity = "critical"
    incident.title = "Redis is down"
    incident.evidence = {"summary": "redis-exporter unreachable"}
    return incident


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "spent": 0.0,
        "stored": [],
        "llm_calls": 0,
    }

    redis = AsyncMock()

    async def fake_get(key: str) -> str:
        return str(state["spent"])

    async def fake_incrbyfloat(key: str, amount: float) -> float:
        state["spent"] += amount
        return state["spent"]

    redis.get = AsyncMock(side_effect=fake_get)
    redis.incrbyfloat = AsyncMock(side_effect=fake_incrbyfloat)
    redis.expire = AsyncMock()

    async def fake_redis() -> Any:
        return redis

    async def fake_invoke(llm: Any, system: str, human: str) -> tuple[DiagnosisOutput, int, int]:
        state["llm_calls"] += 1
        state["last_human"] = human
        return (
            DiagnosisOutput(
                diagnosis="Redis container stopped",
                probable_cause="OOM kill",
                recommended_actions=["docker restart redis"],
            ),
            500,
            200,
        )

    class _Repo:
        def __init__(self, db: Any) -> None: ...

        async def distinct_admin_languages(self) -> list[str]:
            # Declared rather than left to the AttributeError fallback: a test
            # that reaches its subject through an exception path proves the
            # fallback, not the nominal one.
            return ["en"]

        async def store_diagnosis(self, incident_id: Any, payload: dict[str, Any]) -> None:
            state["stored"].append(payload)

    monkeypatch.setattr(diag_module, "get_redis_cache", fake_redis)
    monkeypatch.setattr(diag_module, "_invoke_diagnostician", fake_invoke)
    # The evidence pack (ADR-266) is collected from Prometheus and Loki by
    # default; a unit test never reaches a telemetry backend, so the pump gets
    # a canned pack unless a test substitutes its own collector.
    monkeypatch.setattr(
        diag_module,
        "collect_diagnosis_context",
        AsyncMock(
            return_value={
                "recipe": None,
                "window_minutes": 30,
                "runtime": {"version": "test", "commit": "", "uptime_seconds": 0},
                "metrics": [],
                "logs": {"status": "skipped"},
            }
        ),
    )
    monkeypatch.setattr(diag_module, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(diag_module, "DiagnosticsRepository", _Repo)
    monkeypatch.setattr(diag_module, "get_cached_cost_usd_eur", lambda *a, **k: (0.01, 0.009))
    monkeypatch.setattr(diag_module.settings, "diagnostics_diagnosis_daily_cost_cap_usd", 1.0)
    state["redis"] = redis
    return state


@pytest.mark.unit
class TestBudget:
    async def test_cap_zero_disables_the_llm_step(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(diag_module.settings, "diagnostics_diagnosis_daily_cost_cap_usd", 0.0)
        done = await diag_module.diagnose_incidents(
            [_incident()], db=MagicMock(), system_prompt="You are the diagnostician."
        )
        assert done == 0
        assert wired["llm_calls"] == 0
        assert wired["stored"] == []  # diagnosis stays NULL → retried tomorrow

    async def test_exhausted_budget_skips_without_llm_call(self, wired: dict[str, Any]) -> None:
        wired["spent"] = 5.0  # over the 1.0 cap
        done = await diag_module.diagnose_incidents(
            [_incident()], db=MagicMock(), system_prompt="You are the diagnostician."
        )
        assert done == 0
        assert wired["llm_calls"] == 0

    async def test_nominal_diagnosis_records_spend_and_stores(self, wired: dict[str, Any]) -> None:
        done = await diag_module.diagnose_incidents(
            [_incident()], db=MagicMock(), system_prompt="You are the diagnostician."
        )
        assert done == 1
        assert wired["llm_calls"] == 1
        stored = wired["stored"][0]
        assert stored["diagnosis"] == "Redis container stopped"
        assert stored["probable_cause"] == "OOM kill"
        assert stored["recommended_actions"] == ["docker restart redis"]
        assert stored["cost_usd"] == pytest.approx(0.01)
        wired["redis"].incrbyfloat.assert_awaited_once()

    async def test_llm_failure_leaves_diagnosis_null_for_retry(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def broken(*_: Any) -> Any:
            raise RuntimeError("provider down")

        monkeypatch.setattr(diag_module, "_invoke_diagnostician", broken)
        done = await diag_module.diagnose_incidents(
            [_incident()], db=MagicMock(), system_prompt="You are the diagnostician."
        )
        assert done == 0
        assert wired["stored"] == []


@pytest.mark.unit
class TestRunbookLoader:
    def test_valid_alertname_loads_and_caps(self, tmp_path: Any, monkeypatch: Any) -> None:
        (tmp_path / "RedisDown.md").write_text("# Runbook\n" + "x" * 10_000, encoding="utf-8")
        monkeypatch.setattr(diag_module.settings, "diagnostics_runbooks_dir", str(tmp_path))
        monkeypatch.setattr(diag_module.settings, "diagnostics_runbook_max_chars", 500)
        excerpt = diag_module.load_runbook_excerpt("RedisDown")
        assert excerpt.startswith("# Runbook")
        assert len(excerpt) <= 500

    @pytest.mark.parametrize(
        "hostile", ["../secrets", "Redis/../../etc", "Redis Down", "", "a" * 200]
    )
    def test_traversal_shaped_names_yield_empty(
        self, hostile: str, tmp_path: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(diag_module.settings, "diagnostics_runbooks_dir", str(tmp_path))
        assert diag_module.load_runbook_excerpt(hostile) == ""

    def test_missing_runbook_yields_empty(self, tmp_path: Any, monkeypatch: Any) -> None:
        monkeypatch.setattr(diag_module.settings, "diagnostics_runbooks_dir", str(tmp_path))
        assert diag_module.load_runbook_excerpt("NoSuchAlert") == ""


@pytest.mark.unit
class TestRunbookCount:
    """Production ran for weeks with an EMPTY runbooks mount and nothing said so:
    `had_runbook` was false on every stored diagnosis. The count makes the gap a
    number an administrator can see, and a boot log can warn about."""

    def test_counts_only_markdown_runbooks(self, tmp_path: Any, monkeypatch: Any) -> None:
        (tmp_path / "RedisDown.md").write_text("# Runbook", encoding="utf-8")
        (tmp_path / "ServiceDown.md").write_text("# Runbook", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("not a runbook", encoding="utf-8")
        monkeypatch.setattr(diag_module.settings, "diagnostics_runbooks_dir", str(tmp_path))

        assert diag_module.count_runbooks() == 2

    def test_a_missing_directory_counts_zero_and_never_raises(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(
            diag_module.settings, "diagnostics_runbooks_dir", str(tmp_path / "absent")
        )

        assert diag_module.count_runbooks() == 0

    def test_an_empty_mount_point_counts_zero(self, tmp_path: Any, monkeypatch: Any) -> None:
        """Exactly the production shape: the directory exists (Docker created the
        mount point) and holds nothing."""
        monkeypatch.setattr(diag_module.settings, "diagnostics_runbooks_dir", str(tmp_path))

        assert diag_module.count_runbooks() == 0


@pytest.mark.unit
class TestEvidencePack:
    async def test_prompt_carries_runbook_and_quoted_evidence(
        self, wired: dict[str, Any], tmp_path: Any, monkeypatch: Any
    ) -> None:
        (tmp_path / "RedisDown.md").write_text("Restart the redis container.", encoding="utf-8")
        monkeypatch.setattr(diag_module.settings, "diagnostics_runbooks_dir", str(tmp_path))
        await diag_module.diagnose_incidents(
            [_incident()], db=MagicMock(), system_prompt="You are the diagnostician."
        )
        human = wired["last_human"]
        assert "Restart the redis container." in human
        assert "redis-exporter unreachable" in human


@pytest.mark.unit
class TestTheEvidencePackIsCollectedOncePerIncident:
    """ADR-266: the pack is fetched at diagnosis time, once per incident whatever
    the number of admin languages, only when a call is actually going to be
    made, and its failure costs the diagnosis nothing."""

    @staticmethod
    def _pack() -> dict[str, Any]:
        return {
            "recipe": "RedisDown",
            "window_minutes": 30,
            "runtime": {"version": "1.42.0", "commit": "abc", "uptime_seconds": 10},
            "metrics": [],
            "logs": {"status": "skipped"},
        }

    async def test_collected_once_for_two_languages_and_stored_with_the_record(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        collector = AsyncMock(return_value=self._pack())
        monkeypatch.setattr(diag_module, "collect_diagnosis_context", collector)

        async def two_languages(self: Any) -> list[str]:
            return ["en", "fr"]

        monkeypatch.setattr(
            diag_module.DiagnosticsRepository, "distinct_admin_languages", two_languages
        )

        stored = await diag_module.diagnose_incidents(
            [_incident()], db=MagicMock(), system_prompt="Write in {language}."
        )

        assert stored == 1
        assert wired["llm_calls"] == 2, "one call per admin language"
        collector.assert_awaited_once()
        assert wired["stored"][0]["context"] == self._pack()
        assert "1.42.0" in wired["last_human"], "the pack reached the prompt"

    async def test_a_failing_collector_costs_the_diagnosis_nothing(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            diag_module, "collect_diagnosis_context", AsyncMock(side_effect=RuntimeError("boom"))
        )

        stored = await diag_module.diagnose_incidents(
            [_incident()], db=MagicMock(), system_prompt="{language}"
        )

        assert stored == 1
        assert wired["stored"][0]["context"] == {"status": "unavailable", "error": "RuntimeError"}

    async def test_an_exhausted_budget_reads_no_telemetry(
        self, wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tick whose budget is spent must not query Loki to decide nothing."""
        collector = AsyncMock(return_value=self._pack())
        monkeypatch.setattr(diag_module, "collect_diagnosis_context", collector)
        wired["spent"] = 1.0

        await diag_module.diagnose_incidents(
            [_incident()], db=MagicMock(), system_prompt="{language}"
        )

        collector.assert_not_awaited()
        assert wired["llm_calls"] == 0
