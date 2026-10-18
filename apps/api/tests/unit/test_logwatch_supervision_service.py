"""The daily report reads what the supervision recorded over the day.

Measured on production, 2026-10-18: the report covering 2026-10-17 said
« Aucun redemarrage. Tout est stable. » about a day on which an API container
restarted about 2 050 times under a critical alert that fired for six and a
half hours — the report read container states at 06:25 and no alert at all.
The supervision section reads the WINDOW from Prometheus, Alertmanager and the
incident memory; these tests pin its arithmetic, its wording and the rule that
a source it cannot read is named rather than taken for silence.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from types import ModuleType
from typing import Any

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
SCRIPT = REPO_ROOT / "infrastructure" / "logwatch" / "scripts" / "services" / "lia-supervision"


def _load() -> ModuleType:
    """Load the extensionless service script as a module, writing no bytecode.

    Registered first: ``dataclasses`` resolves postponed annotations through
    ``sys.modules``. No ``__pycache__`` is left beside it: ``deploy.sh`` copies
    that directory onto the host, and the one an import wrote made ``cp`` exit 1
    under ``set -e`` — the deployment stopped at step 4/7.
    """
    loader = importlib.machinery.SourceFileLoader("logwatch_supervision", str(SCRIPT))
    spec = importlib.util.spec_from_loader("logwatch_supervision", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


SUP = _load()

T0 = 1_792_000_000.0  # an arbitrary instant; the arithmetic is relative to it
#: Minutes in the default 24-hour test window: a source that recorded all of them.
FULL_DAY_MINUTES = 24 * 60


def _window(start: float = T0, hours: int = 24) -> Any:
    return SUP.Window(start, start + hours * 3600, "test")


def test_loading_the_script_writes_no_bytecode_beside_it() -> None:
    """`deploy.sh` copies this directory onto the host: a ``__pycache__`` there
    made `cp` exit 1 and `set -e` stop the deployment at step 4/7."""
    assert not (SCRIPT.parent / "__pycache__").exists()


def _series(labels: dict[str, str], stamps: list[float], value: float = 1.0) -> dict[str, Any]:
    return {"metric": labels, "values": [[stamp, str(value)] for stamp in stamps]}


def _instant(labels: dict[str, str], value: float) -> dict[str, Any]:
    return {"metric": labels, "value": [T0, str(value)]}


def _success(result: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


class FakeSources:
    """Prometheus, Alertmanager and docker answering from canned data.

    By default every source recorded the whole window, as on a healthy day: a
    test that wants a blind source says so through ``coverage`` (minutes the
    ``up`` series of a job was recorded) or ``probes_measured``.
    """

    def __init__(self) -> None:
        self.instant: dict[str, list[dict[str, Any]]] = {}
        self.ranges: dict[str, list[dict[str, Any]]] = {}
        self.coverage: dict[str, float] = {
            'up{job="prometheus"}': FULL_DAY_MINUTES,
            'up{job="cadvisor"}': FULL_DAY_MINUTES,
        }
        self.probes_measured: dict[str, float] = {
            "blackbox-backup": FULL_DAY_MINUTES,
            "blackbox-public": FULL_DAY_MINUTES,
        }
        self.rules: list[dict[str, Any]] = [{"name": "ServiceDown", "health": "ok"}]
        self.targets: list[dict[str, Any]] = [{"labels": {"job": "lia-api"}, "health": "up"}]
        self.am_alerts: list[dict[str, Any]] = []
        self.ports: dict[str, str] = {
            "lia-prometheus-prod": "127.0.0.1:9090",
            "lia-alertmanager-prod": "127.0.0.1:9094",
        }
        self.psql_output = ""
        self.commands: list[list[str]] = []
        self.expressions: list[str] = []

    def _coverage_answer(self, expression: str) -> list[dict[str, Any]] | None:
        if "count_over_time(probe_success[" in expression:
            return [
                _instant({"job": job}, minutes) for job, minutes in self.probes_measured.items()
            ]
        for needle, minutes in self.coverage.items():
            if needle in expression:
                return [_instant({}, minutes)] if minutes else []
        return None

    def fetch(self, url: str) -> object:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/api/v2/alerts":
            return self.am_alerts
        if parsed.path == "/api/v1/rules":
            return {"status": "success", "data": {"groups": [{"rules": self.rules}]}}
        if parsed.path == "/api/v1/targets":
            return {"status": "success", "data": {"activeTargets": self.targets}}
        expression = query["query"][0]
        self.expressions.append(expression)
        if parsed.path == "/api/v1/query":
            covered = self._coverage_answer(expression)
            if covered is not None:
                return _success(covered)
        table = self.ranges if parsed.path.endswith("query_range") else self.instant
        for needle, result in table.items():
            if needle in expression:
                return _success(result)
        return _success([])

    def run(self, command: list[str], stdin: str | None) -> str:
        self.commands.append(command)
        if command[:2] == ["docker", "port"]:
            if command[2] not in self.ports:
                raise SUP.SourceUnavailable(f"No such container: {command[2]}")
            return self.ports[command[2]] + "\n"
        if command[:2] == ["docker", "exec"]:
            assert stdin == SUP.INCIDENTS_SQL
            return self.psql_output
        raise AssertionError(command)


class TestTheWindowIsTheReportDay:
    def test_yesterday_is_the_previous_local_day(self) -> None:
        now = datetime(2026, 10, 18, 6, 25, tzinfo=UTC).astimezone()

        window = SUP.report_window("yesterday", now)

        midnight = datetime.combine(now.date(), time.min).astimezone()
        day_before = datetime.combine(now.date() - timedelta(days=1), time.min).astimezone()
        assert window.end == midnight.timestamp()
        assert window.start == day_before.timestamp()

    def test_a_daylight_saving_day_keeps_its_true_length(self) -> None:
        now = datetime(2026, 10, 26, 6, 25, tzinfo=UTC).astimezone()

        window = SUP.report_window("Yesterday", now)

        assert 23 * 3600 <= window.end - window.start <= 25 * 3600

    def test_today_runs_up_to_now_and_anything_else_is_the_last_day(self) -> None:
        now = datetime(2026, 10, 18, 6, 25, tzinfo=UTC).astimezone()

        today = SUP.report_window("today", now)
        other = SUP.report_window("all", now)

        assert today.end == now.timestamp()
        assert other.end - other.start == 24 * 3600
        assert other.label.startswith("dernieres 24 h")


class TestAlertsAreReadAsEpisodes:
    def test_a_gap_splits_a_series_into_two_episodes(self) -> None:
        labels = {"alertname": "SSELatencyP95High", "severity": "warning"}
        stamps = [T0, T0 + 60, T0 + 120, T0 + 3600, T0 + 3660]

        episodes = SUP.alert_episodes([_series(labels, stamps)], _window())

        assert [(e.start, e.end) for e in episodes] == [(T0, T0 + 120), (T0 + 3600, T0 + 3660)]
        assert not any(e.open_at_end for e in episodes)

    def test_critical_comes_first_and_an_episode_reaching_the_end_is_open(self) -> None:
        window = _window()
        warning = _series({"alertname": "B", "severity": "warning"}, [T0])
        critical = _series(
            {"alertname": "ContainerRestartLoop", "severity": "critical", "name": "lia-x"},
            [window.end - 120, window.end - 60, window.end],
        )

        episodes = SUP.alert_episodes([warning, critical], window)

        assert [e.alertname for e in episodes] == ["ContainerRestartLoop", "B"]
        assert episodes[0].target == "lia-x"
        assert episodes[0].open_at_end

    def test_the_section_flags_a_critical_alert_and_caps_long_lists(self) -> None:
        window = _window()
        loop = _series(
            {"alertname": "ContainerRestartLoop", "severity": "critical", "name": "lia-x"},
            [T0 + 600 + 60 * i for i in range(393)],
        )
        noisy = _series(
            {"alertname": "SSELatencyP95High", "severity": "warning"},
            [T0 + 3600 * h for h in range(8)],
        )

        text = "\n".join(
            SUP.render_episodes(SUP.alert_episodes([loop, noisy], window), window, 1.0)
        )

        assert "[CRITIQUE] ContainerRestartLoop  lia-x  *** ATTENTION ***" in text
        assert "(6 h 33 min)" in text
        assert "[WARNING] SSELatencyP95High" in text
        assert "... et 2 autre(s) episode(s)" in text

    def test_no_alert_is_said(self) -> None:
        window = _window()
        assert "Aucune alerte" in "\n".join(SUP.render_episodes([], window, 1.0))


class TestAWindowNoSourceRecordedIsNeverAQuietOne:
    """No sample is not « nothing happened »: before, a Prometheus, a cAdvisor or
    a blackbox exporter that recorded nothing read as « no alert fired », « no
    restart » and « every probe answered » — the opposite of the module's rule."""

    def test_a_prometheus_that_recorded_nothing_evaluated_no_rule(self) -> None:
        sources = FakeSources()
        sources.coverage['up{job="prometheus"}'] = 0
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        text = "\n".join(SUP.render_fired_alerts(prometheus, _window()))

        assert "*** AUCUNE MESURE : Prometheus n a rien enregistre sur la periode ***" in text
        assert "Aucune alerte" not in text

    def test_a_partial_record_says_how_much_of_the_window_it_covers(self) -> None:
        sources = FakeSources()
        sources.coverage['up{job="prometheus"}'] = FULL_DAY_MINUTES / 2
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        text = "\n".join(SUP.render_fired_alerts(prometheus, _window()))

        assert "Prometheus n a mesure que 50 % de la periode  *** A VERIFIER ***" in text
        assert "Aucune alerte n a sonne sur la periode." in text

    def test_coverage_is_read_per_minute_over_the_whole_window(self) -> None:
        sources = FakeSources()
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        share = SUP.coverage(prometheus, SUP.CADVISOR_UP, _window())

        assert share == 1.0
        assert sources.expressions[-1] == (
            'max(count_over_time((up{job="cadvisor"} == 1)[86400s:1m]))'
        )

    def test_a_cadvisor_that_recorded_nothing_saw_no_restart_and_no_peak(self) -> None:
        sources = FakeSources()
        sources.coverage['up{job="cadvisor"}'] = 0
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        restarts = "\n".join(SUP.render_restarts(prometheus, _window()))
        memory = "\n".join(SUP.render_memory(prometheus, _window()))

        assert "*** AUCUNE MESURE : cAdvisor n a rien enregistre sur la periode ***" in restarts
        assert "Aucun redemarrage" not in restarts
        assert "*** AUCUNE MESURE : cAdvisor n a rien enregistre sur la periode ***" in memory
        assert not any("container_start_time_seconds" in e for e in sources.expressions)

    def test_no_probe_series_is_no_measure_never_every_probe_answered(self) -> None:
        sources = FakeSources()
        sources.probes_measured = {}
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        text = "\n".join(SUP.render_probes(prometheus, _window()))

        assert "*** AUCUNE MESURE : aucune sonde n a ete enregistree sur la periode ***" in text
        assert "Toutes les sondes" not in text

    def test_each_probe_says_what_it_measured(self) -> None:
        sources = FakeSources()
        sources.probes_measured["blackbox-egress"] = FULL_DAY_MINUTES / 4
        sources.instant = {"(probe_success == 0)": [_instant({"job": "blackbox-public"}, 12)]}
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        lines = SUP.render_probes(prometheus, _window())

        assert "  blackbox-public : 12 min en echec" in lines
        assert (
            "  blackbox-egress : aucun echec  (mesuree sur 25 % de la periode)  *** A VERIFIER ***"
            in lines
        )
        assert not any(line.startswith("  blackbox-backup") for line in lines)
        assert not any("Toutes les sondes" in line for line in lines)

    def test_a_fully_measured_quiet_day_names_the_probes_it_measured(self) -> None:
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", FakeSources().fetch)

        assert SUP.render_probes(prometheus, _window())[-1] == (
            "  Toutes les sondes mesurees ont repondu : blackbox-backup, blackbox-public."
        )

    def test_a_blind_day_never_reads_as_a_quiet_one(self) -> None:
        sources = FakeSources()
        sources.coverage = {'up{job="prometheus"}': 0, 'up{job="cadvisor"}': 0}
        sources.probes_measured = {}

        text = "\n".join(SUP.build_report(_window(), T0, sources.fetch, sources.run))

        for quiet in ("Aucune alerte n a sonne", "Aucun redemarrage", "Toutes les sondes"):
            assert quiet not in text, quiet
        assert text.count("*** AUCUNE MESURE") == 4


class TestTheAlertingChainReportsOnItself:
    def test_broken_rules_down_targets_and_failed_notifications_are_flagged(self) -> None:
        sources = FakeSources()
        sources.rules = [{"name": "ServiceDown", "health": "ok"}, {"name": "X", "health": "err"}]
        sources.targets = [{"labels": {"job": "cadvisor"}, "health": "down"}]
        sources.instant = {
            "prometheus_notifications_errors_total": [_instant({}, 2)],
            "alertmanager_notifications_total": [_instant({"integration": "email"}, 4)],
            "alertmanager_notifications_failed_total": [_instant({"integration": "webhook"}, 1)],
        }
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        text = "\n".join(SUP.render_chain(prometheus, _window()))

        assert "Regles d alerte chargees : 2, en erreur : 1  *** ATTENTION ***" in text
        assert "Cibles en echec maintenant : cadvisor  *** ATTENTION ***" in text
        assert "2 envoi(s) en erreur ou perdu(s)  *** ATTENTION ***" in text
        assert "Notifications envoyees    : email=4" in text
        assert "NOTIFICATIONS EN ECHEC    : webhook=1" in text

    def test_a_healthy_chain_reads_as_healthy(self) -> None:
        """A rule or target not evaluated yet (Prometheus just restarted) is no failure."""
        sources = FakeSources()
        sources.rules.append({"name": "DiskSpaceCritical", "health": "unknown"})
        sources.targets.append({"labels": {"job": "node"}, "health": "unknown"})
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        text = "\n".join(SUP.render_chain(prometheus, _window()))

        assert "ATTENTION" not in text
        assert "Regles d alerte chargees : 2, en erreur : 0" in text
        assert "Notifications en echec    : 0" in text

    def test_no_rule_loaded_is_flagged_and_many_broken_rules_are_counted(self) -> None:
        sources = FakeSources()
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)
        sources.rules = []

        assert "  Regles d alerte chargees : 0, en erreur : 0  *** ATTENTION ***" in (
            SUP.render_chain(prometheus, _window())
        )
        sources.rules = [{"name": f"Rule{i}", "health": "err"} for i in range(13)]
        lines = SUP.render_chain(prometheus, _window())
        assert sum(line.startswith("    en erreur : ") for line in lines) == 10
        assert "    ... et 3 autre(s)" in lines


class TestRestartsAreCountedOverTheWindow:
    def test_a_loop_is_listed_alone_and_the_rest_is_grouped(self) -> None:
        sources = FakeSources()
        sources.instant = {
            "changes(container_start_time_seconds": [
                _instant({"name": "lia-demo-api"}, 341),
                _instant({"name": "lia-api-prod"}, 1),
                _instant({"name": "lia-web-prod"}, 1),
                _instant({"name": "lia-redis-prod"}, 1),
            ],
            "count_over_time(container_start_time_seconds": [
                _instant({"name": "lia-api-prod"}, 4),
                _instant({"name": "lia-web-prod"}, 4),
            ],
        }
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        lines = SUP.render_restarts(prometheus, _window())

        assert "  lia-demo-api : au moins 341 redemarrage(s)  *** ATTENTION ***" in lines
        assert (
            "  au moins 1 redemarrage(s), recree 3 fois (2) : lia-api-prod, lia-web-prod" in lines
        )
        assert "  au moins 1 redemarrage(s) (1) : lia-redis-prod" in lines

    def test_a_host_boot_inside_the_window_is_named(self) -> None:
        window = _window()
        sources = FakeSources()
        boot = T0 + 3600
        sources.ranges = {
            "node_boot_time_seconds": [
                _series({"job": "node"}, [T0, T0 + 60], value=T0 - 86400),
                _series({"job": "node"}, [T0 + 3700, T0 + 3760], value=boot),
            ]
        }
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", sources.fetch)

        assert SUP.host_boots(prometheus.series("node_boot_time_seconds", window), window) == [boot]
        assert any(
            line.startswith("  Demarrage de l hote : ")
            for line in SUP.render_restarts(prometheus, window)
        )

    def test_a_quiet_day_says_so(self) -> None:
        prometheus = SUP.Prometheus("http://127.0.0.1:9090", FakeSources().fetch)

        assert "  Aucun redemarrage ni recreation sur la periode." in SUP.render_restarts(
            prometheus, _window()
        )


class TestMemoryPeaksAreTheWindowsNotASample:
    def test_each_container_keeps_its_highest_point_and_its_time(self) -> None:
        series = [
            {"metric": {"name": "lia-web-prod"}, "values": [[T0, "60.5"], [T0 + 60, "79.0"]]},
            {"metric": {"name": "lia-promtail-prod"}, "values": [[T0, "95.9"]]},
            {"metric": {"name": "lia-web-prod"}, "values": [[T0 + 120, "40.0"]]},
        ]

        assert SUP.memory_peaks(series) == [
            ("lia-promtail-prod", 95.9, T0),
            ("lia-web-prod", 79.0, T0 + 60),
        ]


class TestIncidentsComeFromTheMemoryTheAdminReads:
    def test_open_incidents_are_listed_with_their_age(self) -> None:
        sources = FakeSources()
        sources.psql_output = (
            "warning\0ContainerMemoryNearLimit\0Container lia-web-prod near its memory limit"
            f"\0{T0 - 86400 * 28}\0{T0 - 86400 * 28}\n"
        )

        text = "\n".join(SUP.render_incidents(sources.run, T0))

        assert "[warning] ContainerMemoryNearLimit : Container lia-web-prod near" in text
        assert "il y a 672 h 00 min" in text

    def test_the_query_is_read_only(self) -> None:
        sources = FakeSources()

        SUP.render_incidents(sources.run, T0)

        command = sources.commands[-1]
        assert "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=20000" in command

    def test_unparseable_rows_are_skipped(self) -> None:
        assert SUP.parse_incidents("garbage\n\nwarning\0a\0b\0x\0y\n") == []


class TestASourceThatCannotBeReadIsNamed:
    def test_prometheus_down_is_said_and_the_other_sources_still_report(self) -> None:
        sources = FakeSources()
        del sources.ports["lia-prometheus-prod"]

        text = "\n".join(SUP.build_report(_window(), T0, sources.fetch, sources.run))

        assert "*** PROMETHEUS INJOIGNABLE" in text
        assert "=== ALERTES ACTIVES MAINTENANT (Alertmanager) ===" in text
        assert "=== INCIDENTS OUVERTS (diagnostic LIA) ===" in text
        assert "REDEMARRAGES" not in text

    def test_a_section_that_breaks_does_not_take_the_others_down(self) -> None:
        def broken() -> list[str]:
            raise KeyError("shape")

        assert SUP._section("X", broken)[-1] == "  *** SECTION EN ERREUR : KeyError ***"

    def test_every_section_is_present_on_a_quiet_day(self) -> None:
        sources = FakeSources()

        text = "\n".join(SUP.build_report(_window(), T0, sources.fetch, sources.run))

        for title in (
            "ALERTES DECLENCHEES",
            "CHAINE D ALERTE",
            "ALERTES ACTIVES MAINTENANT",
            "INCIDENTS OUVERTS",
            "REDEMARRAGES DE CONTENEURS",
            "PICS DE MEMOIRE",
            "SONDES EXTERNES",
        ):
            assert f"=== {title}" in text, title
        assert "ILLISIBLE" not in text and "EN ERREUR" not in text

    def test_an_active_alert_is_shown_in_local_time(self) -> None:
        sources = FakeSources()
        sources.am_alerts = [
            {
                "labels": {"alertname": "ServiceDown", "severity": "critical"},
                "status": {"state": "active"},
                "startsAt": "2026-10-17T11:19:11.544771236Z",
            }
        ]
        expected = datetime(2026, 10, 17, 11, 19, 11, tzinfo=UTC).astimezone()

        text = "\n".join(SUP.render_active_alerts(sources.fetch, "http://127.0.0.1:9094"))

        assert f"[CRITIQUE] ServiceDown depuis {expected:%Y-%m-%d %H:%M}" in text


def test_fake_json_is_what_the_real_endpoints_return() -> None:
    """The fakes answer in the API's own envelope (a fake in another shape
    would test a parser nobody runs)."""
    payload: Callable[[str], object] = FakeSources().fetch
    answer = payload("http://127.0.0.1:9090/api/v1/query?query=up&time=1")
    assert json.loads(json.dumps(answer))["status"] == "success"
