"""Guard: what a panel or an alert reads from a keep-listed target is kept.

Prometheus scrapes Loki, Alloy, Tempo and Grafana for the few series their
alert and the meta-health dashboard read, through a ``keep`` list per job
(``prometheus.yml``): their full /metrics were ~9,000 series nobody read
(measured 2026-10-03). The other side of a keep-list is a panel added later on a
series the list drops — it renders "No data" forever and reads as a healthy
silence. Every metric a dashboard or a core alert selects with one of those
``job`` labels must match that job's keep expression.

The exporters joined the rule on 2026-10-12 (ADR-333 amendment): on production
cAdvisor published 7,137 series and the dashboards and rules read eight
families; postgres-exporter published 3,590 and five were read. Their
selectors carry no ``job`` label (a panel selects
``container_memory_working_set_bytes{name="lia-api-prod"}``), so an exporter's
series are recognised by the family prefix its metric names share, declared
in ``EXPORTER_FAMILIES``. Recording rules and the product alerts are read too:
a recording rule over a dropped series is the same healthy silence.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
OBSERVABILITY = REPO_ROOT / "infrastructure" / "observability"
PIPELINE_JOBS = ("loki", "alloy", "tempo", "grafana")
# An exporter job and the metric-name prefixes that identify its series in an
# expression (cAdvisor also exports ``machine_*`` for the host it runs on).
EXPORTER_FAMILIES: dict[str, tuple[str, ...]] = {
    "cadvisor": ("container_", "machine_"),
    "postgresql": ("pg_",),
}
RULE_FILES = ("alerts-core.yml", "alerts.yml", "recording_rules.yml")
_SELECTOR = re.compile(
    r'([a-zA-Z_:][a-zA-Z0-9_:]*)\{[^}]*\bjob="(' + "|".join(PIPELINE_JOBS) + r')"'
)
_FAMILY_PREFIXES = tuple(p for prefixes in EXPORTER_FAMILIES.values() for p in prefixes)
_FAMILY_IDENT = re.compile(
    r"(?<![a-zA-Z0-9_:])((?:" + "|".join(_FAMILY_PREFIXES) + r")[a-zA-Z0-9_:]*)"
)


def _keep_expressions(jobs_wanted: tuple[str, ...]) -> dict[str, re.Pattern[str] | None]:
    """Each wanted job's keep expression; None for a job that keeps nothing."""
    config = yaml.safe_load(
        (OBSERVABILITY / "prometheus" / "prometheus.yml").read_text(encoding="utf-8")
    )
    jobs: dict[str, re.Pattern[str] | None] = {}
    for scrape in config["scrape_configs"]:
        if scrape["job_name"] not in jobs_wanted:
            continue
        rules = scrape.get("metric_relabel_configs") or []
        keep = [
            r for r in rules if r.get("action") == "keep" and r.get("source_labels") == ["__name__"]
        ]
        jobs[scrape["job_name"]] = re.compile(f"^(?:{keep[0]['regex']})$") if keep else None
    return jobs


def _expressions() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []

    def walk(panels: list[dict[str, Any]], source: str) -> None:
        for panel in panels:
            for target in panel.get("targets") or []:
                if isinstance(target.get("expr"), str):
                    found.append((source, target["expr"]))
            walk(panel.get("panels") or [], source)

    for path in sorted((OBSERVABILITY / "grafana" / "dashboards").glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")).get("panels") or [], path.name)
    for name in RULE_FILES:
        path = OBSERVABILITY / "prometheus" / name
        if not path.exists():
            continue
        rules = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for group in rules.get("groups") or []:
            for rule in group.get("rules") or []:
                if isinstance(rule.get("expr"), str):
                    found.append((name, rule["expr"]))
    return found


def _exporter_job_of(metric: str) -> str:
    return next(job for job, prefixes in EXPORTER_FAMILIES.items() if metric.startswith(prefixes))


def _dropped_by(keep: dict[str, re.Pattern[str] | None], job: str, metric: str) -> bool:
    """True when ``job``'s keep-list (None = keeps nothing) does not keep ``metric``."""
    pattern = keep[job]
    return pattern is None or not pattern.match(metric)


def test_every_pipeline_job_declares_what_it_keeps() -> None:
    assert set(_keep_expressions(PIPELINE_JOBS)) == set(
        PIPELINE_JOBS
    ), "a pipeline job lost its scrape config"


def test_every_pipeline_series_a_panel_or_an_alert_reads_is_kept() -> None:
    keep = _keep_expressions(PIPELINE_JOBS)
    dropped = sorted(
        {
            (source, metric, job)
            for source, expr in _expressions()
            for metric, job in _SELECTOR.findall(expr)
            if metric != "up" and _dropped_by(keep, job, metric)
        }
    )

    assert not dropped, f"series read but dropped by their job's keep-list: {dropped}"


def test_every_exporter_job_declares_what_it_keeps() -> None:
    keep = _keep_expressions(tuple(EXPORTER_FAMILIES))

    assert set(keep) == set(EXPORTER_FAMILIES), "an exporter job lost its scrape config"
    assert all(
        keep.values()
    ), f"an exporter job keeps its whole /metrics: {[j for j, k in keep.items() if k is None]}"


def test_every_exporter_series_a_panel_or_a_rule_reads_is_kept() -> None:
    keep = _keep_expressions(tuple(EXPORTER_FAMILIES))
    dropped = sorted(
        {
            (source, metric, _exporter_job_of(metric))
            for source, expr in _expressions()
            for metric in _FAMILY_IDENT.findall(expr)
            if _dropped_by(keep, _exporter_job_of(metric), metric)
        }
    )

    assert not dropped, f"series read but dropped by their job's keep-list: {dropped}"


def test_the_guard_sees_the_series_it_exists_for() -> None:
    read = {metric for _, expr in _expressions() for metric, _ in _SELECTOR.findall(expr)}
    families = {metric for _, expr in _expressions() for metric in _FAMILY_IDENT.findall(expr)}

    assert {"loki_write_dropped_entries_total", "tempo_distributor_spans_received_total"} <= read
    assert {"container_memory_working_set_bytes", "pg_stat_database_numbackends"} <= families
