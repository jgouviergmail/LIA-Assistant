"""Snapshot → incident synchronisation (self-check side of the correlation).

One outage ⇒ one incident: a check DECLARING an alertname converges on the
alert's correlation key; a check without one correlates on its check_id.
Critical opens (or touches); ok auto-resolves ONLY self_check-sourced
incidents (the alert's own resolved event owns alert-sourced ones).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from src.domains.diagnostics import incident_sync
from src.domains.diagnostics.checks import CheckResult, CheckStatus
from src.domains.diagnostics.models import INCIDENT_SOURCE_SELF_CHECK


class _FakeRepo:
    def __init__(self) -> None:
        self.opened: list[dict[str, Any]] = []
        self.resolved: list[tuple[str, str | None]] = []
        self.created_flag = True

    async def open_or_touch_incident(self, **kwargs: Any) -> tuple[Any, bool, Any]:
        self.opened.append(kwargs)
        return uuid4(), self.created_flag, None

    async def resolve_incident(self, correlation_key: str, *, source: str | None = None) -> int:
        self.resolved.append((correlation_key, source))
        return 1


def _result(check_id: str, status: CheckStatus, alertname: str | None = None) -> CheckResult:
    return CheckResult(check_id=check_id, status=status, value=1.0, detail="", alertname=alertname)


@pytest.mark.unit
class TestSyncIncidents:
    async def test_critical_with_alertname_uses_the_alert_correlation_key(self) -> None:
        repo = _FakeRepo()
        outcome = await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("redis", CheckStatus.CRITICAL, alertname="RedisDown")],
        )
        assert outcome.opened_ids and repo.opened[0]["correlation_key"] == "RedisDown"
        assert repo.opened[0]["source"] == INCIDENT_SOURCE_SELF_CHECK
        assert repo.opened[0]["alertname"] == "RedisDown"

    async def test_critical_without_alertname_uses_the_check_id(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("scheduler_tick", CheckStatus.CRITICAL)],
        )
        assert repo.opened[0]["correlation_key"] == "scheduler_tick"

    async def test_ok_resolves_only_self_check_sourced(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("redis", CheckStatus.OK, alertname="RedisDown")],
        )
        assert repo.resolved == [("RedisDown", INCIDENT_SOURCE_SELF_CHECK)]
        assert repo.opened == []

    async def test_degraded_and_unknown_neither_open_nor_resolve(self) -> None:
        """Degraded is watched, not incident-worthy; unknown is blindness."""
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [
                _result("disk_usage", CheckStatus.DEGRADED),
                _result("api_error_rate", CheckStatus.UNKNOWN),
            ],
        )
        assert repo.opened == []
        assert repo.resolved == []

    async def test_touch_of_existing_incident_reports_no_new_opening(self) -> None:
        repo = _FakeRepo()
        repo.created_flag = False
        outcome = await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("redis", CheckStatus.CRITICAL, alertname="RedisDown")],
        )
        assert outcome.opened_ids == []
        assert outcome.touched == 1

    async def test_evidence_carries_the_exact_measured_value(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("redis", CheckStatus.CRITICAL, alertname="RedisDown")],
        )
        assert repo.opened[0]["evidence"]["value"] == 1.0
        assert repo.opened[0]["evidence"]["check_id"] == "redis"


@pytest.mark.unit
class TestEvidenceReachesTheIncident:
    """The enriched pack must reach the STORED incident, not just exist.

    `evidence_for` is only worth anything if the diagnostician reads it, and the
    diagnostician reads `incident.evidence`. A unit test on the enricher alone
    would still pass if the sync kept writing the old three fields.
    """

    async def test_stored_evidence_carries_the_thresholds_and_unit(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("embedding_failure_rate", CheckStatus.CRITICAL)],
        )
        evidence = repo.opened[0]["evidence"]
        # The original fields are still there — nothing regressed. The empty
        # detail is the one exception: an empty string was quoted back by the
        # model as "the detail is empty" (2026-09-05), so absence beats blank.
        assert evidence["check_id"] == "embedding_failure_rate"
        assert evidence["value"] == 1.0
        assert "detail" not in evidence
        # ...and the value can now be JUDGED: a number, its unit, its verdict
        # and the two levels it was compared against.
        assert evidence["status"] == CheckStatus.CRITICAL.value
        assert evidence["unit"] == "percent"
        assert isinstance(evidence["warn"], int | float)
        assert isinstance(evidence["crit"], int | float)
        assert evidence["warn"] < evidence["crit"]

    async def test_in_process_check_keeps_a_pack_without_invented_thresholds(self) -> None:
        """An in-process check has no settings pair: absent beats fabricated."""
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("database", CheckStatus.CRITICAL)],
        )
        evidence = repo.opened[0]["evidence"]
        assert evidence["check_id"] == "database"
        assert evidence["status"] == CheckStatus.CRITICAL.value
        assert "warn" not in evidence and "crit" not in evidence


@pytest.mark.unit
class TestEvidenceNamesItsWindowAndKeepsOnlyRealDetail:
    """Two things the 2026-09-05 diagnosis asked for and could not get: over
    WHAT period the rate was measured, and a detail that said something."""

    async def test_a_prometheus_check_states_its_measurement_window(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("embedding_failure_rate", CheckStatus.CRITICAL)],
        )
        evidence = repo.opened[0]["evidence"]
        assert evidence["window_minutes"] == 30

    async def test_an_in_process_check_has_no_window_to_state(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,  # type: ignore[arg-type]
            [_result("database", CheckStatus.CRITICAL)],
        )
        assert "window_minutes" not in repo.opened[0]["evidence"]

    async def test_a_real_detail_is_kept(self) -> None:
        repo = _FakeRepo()
        result = CheckResult(
            check_id="platform_egress",
            status=CheckStatus.CRITICAL,
            value=None,
            detail="api.openai.com:443 unreachable (TimeoutError)",
            alertname=None,
        )
        await incident_sync.sync_incidents_from_results(repo, [result])  # type: ignore[arg-type]
        assert repo.opened[0]["evidence"]["detail"] == (
            "api.openai.com:443 unreachable (TimeoutError)"
        )
