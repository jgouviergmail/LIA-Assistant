"""Snapshot → incident synchronisation (self-check side of the correlation).

One outage ⇒ one incident: a check DECLARING an alertname converges on the
alert's correlation key; a check without one correlates on its check_id.
Critical opens (or touches); ok auto-resolves ONLY self_check-sourced
incidents (the alert's own resolved event owns alert-sourced ones).

The repository doubles implement the ports the functions declare
(``IncidentRecorder``, ``SilentIncidentResolver``) with their exact signatures:
no ignored diagnostic stands between a double and the contract it stands for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.domains.diagnostics import incident_sync
from src.domains.diagnostics.checks import CheckResult, CheckStatus
from src.domains.diagnostics.incident_sync import IncidentRecorder, SilentIncidentResolver
from src.domains.diagnostics.models import INCIDENT_SOURCE_SELF_CHECK
from src.infrastructure.telemetry.models import ActiveAlert, AlertsResult, TelemetryStatus


@dataclass(frozen=True)
class _Opened:
    """One open-or-touch call, as the repository received it."""

    correlation_key: str
    source: str
    alertname: str | None
    evidence: dict[str, object]


class _FakeRepo(IncidentRecorder):
    def __init__(self) -> None:
        self.opened: list[_Opened] = []
        self.resolved: list[tuple[str, str | None]] = []
        self.created_flag = True

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
        self.opened.append(_Opened(correlation_key, source, alertname, evidence or {}))
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
            repo, [_result("redis", CheckStatus.CRITICAL, alertname="RedisDown")]
        )
        assert outcome.opened_ids and repo.opened[0].correlation_key == "RedisDown"
        assert repo.opened[0].source == INCIDENT_SOURCE_SELF_CHECK
        assert repo.opened[0].alertname == "RedisDown"

    async def test_critical_without_alertname_uses_the_check_id(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo, [_result("scheduler_tick", CheckStatus.CRITICAL)]
        )
        assert repo.opened[0].correlation_key == "scheduler_tick"

    async def test_ok_resolves_only_self_check_sourced(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo, [_result("redis", CheckStatus.OK, alertname="RedisDown")]
        )
        assert repo.resolved == [("RedisDown", INCIDENT_SOURCE_SELF_CHECK)]
        assert repo.opened == []

    async def test_degraded_and_unknown_neither_open_nor_resolve(self) -> None:
        """Degraded is watched, not incident-worthy; unknown is blindness."""
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo,
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
            repo, [_result("redis", CheckStatus.CRITICAL, alertname="RedisDown")]
        )
        assert outcome.opened_ids == []
        assert outcome.touched == 1

    async def test_evidence_carries_the_exact_measured_value(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo, [_result("redis", CheckStatus.CRITICAL, alertname="RedisDown")]
        )
        assert repo.opened[0].evidence["value"] == 1.0
        assert repo.opened[0].evidence["check_id"] == "redis"


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
            repo, [_result("embedding_failure_rate", CheckStatus.CRITICAL)]
        )
        evidence = repo.opened[0].evidence
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
        warn, crit = evidence["warn"], evidence["crit"]
        assert isinstance(warn, int | float)
        assert isinstance(crit, int | float)
        assert warn < crit

    async def test_in_process_check_keeps_a_pack_without_invented_thresholds(self) -> None:
        """An in-process check has no settings pair: absent beats fabricated."""
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo, [_result("database", CheckStatus.CRITICAL)]
        )
        evidence = repo.opened[0].evidence
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
            repo, [_result("embedding_failure_rate", CheckStatus.CRITICAL)]
        )
        assert repo.opened[0].evidence["window_minutes"] == 30

    async def test_an_in_process_check_has_no_window_to_state(self) -> None:
        repo = _FakeRepo()
        await incident_sync.sync_incidents_from_results(
            repo, [_result("database", CheckStatus.CRITICAL)]
        )
        assert "window_minutes" not in repo.opened[0].evidence

    async def test_a_real_detail_is_kept(self) -> None:
        repo = _FakeRepo()
        result = CheckResult(
            check_id="platform_egress",
            status=CheckStatus.CRITICAL,
            value=None,
            detail="api.openai.com:443 unreachable (TimeoutError)",
            alertname=None,
        )
        await incident_sync.sync_incidents_from_results(repo, [result])
        assert repo.opened[0].evidence["detail"] == (
            "api.openai.com:443 unreachable (TimeoutError)"
        )


@dataclass(frozen=True)
class _SilentCall:
    """One reconciliation statement, as the repository received it."""

    firing_alertnames: set[str]
    silent_since: datetime
    now: datetime


class _ReconcileRepo(SilentIncidentResolver):
    def __init__(self, resolved: list[str]) -> None:
        self.calls: list[_SilentCall] = []
        self._resolved = resolved

    async def resolve_silent_alert_incidents(
        self, *, firing_alertnames: set[str], silent_since: datetime, now: datetime
    ) -> list[str]:
        self.calls.append(_SilentCall(firing_alertnames, silent_since, now))
        return self._resolved


def _firing(*names: str, status: TelemetryStatus = "ok") -> AlertsResult:
    return AlertsResult(
        status=status,
        alerts=[
            ActiveAlert(
                fingerprint=f"fp-{name}",
                name=name,
                severity="warning",
                component="",
                starts_at="",
                summary="",
                description="",
                runbook="",
            )
            for name in names
        ],
    )


NOW = datetime(2026, 10, 18, 8, 0, tzinfo=UTC)
#: An Alertmanager up long enough for its listing to be whole.
LONG_UP = NOW - timedelta(days=2)


@pytest.mark.unit
class TestReconcileAlertIncidents:
    """A lost « resolved » delivery left an incident open for 28 days
    (production, 2026-09-20 → 10-18). Closing it reads Alertmanager — the same
    authority — and never closes on doubt."""

    async def test_alertmanager_unreadable_closes_nothing(self) -> None:
        repo = _ReconcileRepo(["ContainerMemoryNearLimit"])

        resolved = await incident_sync.reconcile_alert_incidents(
            repo,
            _firing(status="unavailable"),
            alertmanager_started_at=LONG_UP,
            now=NOW,
            silence_close_seconds=3600,
        )

        assert resolved == []
        assert repo.calls == []

    async def test_the_firing_names_and_the_silence_bound_reach_the_repository(self) -> None:
        repo = _ReconcileRepo(["ContainerMemoryNearLimit"])

        resolved = await incident_sync.reconcile_alert_incidents(
            repo,
            _firing("SSELatencyP95High", "", "ServiceDown"),
            alertmanager_started_at=LONG_UP,
            now=NOW,
            silence_close_seconds=3600,
        )

        assert resolved == ["ContainerMemoryNearLimit"]
        assert repo.calls == [
            _SilentCall(
                firing_alertnames={"SSELatencyP95High", "ServiceDown"},
                silent_since=NOW - timedelta(seconds=3600),
                now=NOW,
            )
        ]

    async def test_nothing_firing_is_a_valid_answer(self) -> None:
        """An empty listing from a READABLE, settled Alertmanager is a fact, not doubt."""
        repo = _ReconcileRepo([])

        await incident_sync.reconcile_alert_incidents(
            repo,
            _firing(),
            alertmanager_started_at=LONG_UP,
            now=NOW,
            silence_close_seconds=3600,
        )

        assert repo.calls and repo.calls[0].firing_alertnames == set()


@pytest.mark.unit
class TestARestartedAlertmanagerIsNotBelievedYet:
    """Alertmanager keeps its alerts in memory: just restarted, it answers « ok »
    with an empty or partial listing until Prometheus re-sends what is firing.
    Read then, a silenced alert — which no webhook re-delivers — had its
    incident closed, and nothing ever reopened it."""

    async def test_a_listing_younger_than_the_warmup_closes_nothing(self) -> None:
        repo = _ReconcileRepo(["ContainerMemoryNearLimit"])
        just_started = NOW - timedelta(seconds=incident_sync.ALERTMANAGER_WARMUP_SECONDS - 1)

        resolved = await incident_sync.reconcile_alert_incidents(
            repo,
            _firing(),
            alertmanager_started_at=just_started,
            now=NOW,
            silence_close_seconds=3600,
        )

        assert resolved == []
        assert repo.calls == []

    async def test_a_listing_as_old_as_the_warmup_is_believed(self) -> None:
        repo = _ReconcileRepo(["ContainerMemoryNearLimit"])
        settled = NOW - timedelta(seconds=incident_sync.ALERTMANAGER_WARMUP_SECONDS)

        resolved = await incident_sync.reconcile_alert_incidents(
            repo,
            _firing(),
            alertmanager_started_at=settled,
            now=NOW,
            silence_close_seconds=3600,
        )

        assert resolved == ["ContainerMemoryNearLimit"]
        assert len(repo.calls) == 1

    async def test_an_unknown_start_closes_nothing(self) -> None:
        """The status endpoint unreadable: the listing cannot be dated."""
        repo = _ReconcileRepo(["ContainerMemoryNearLimit"])

        resolved = await incident_sync.reconcile_alert_incidents(
            repo, _firing(), alertmanager_started_at=None, now=NOW, silence_close_seconds=3600
        )

        assert resolved == []
        assert repo.calls == []
