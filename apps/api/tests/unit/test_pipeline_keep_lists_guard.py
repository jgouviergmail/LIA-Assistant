"""Guard: what a panel or an alert reads from the pipeline's own targets is kept.

Prometheus scrapes Loki, Alloy, Tempo and Grafana for the few series their
alert and the meta-health dashboard read, through a ``keep`` list per job
(``prometheus.yml``): their full /metrics were ~9,000 series nobody read
(measured 2026-10-03). The other side of a keep-list is a panel added later on a
series the list drops — it renders "No data" forever and reads as a healthy
silence. Every metric a dashboard or a core alert selects with one of those
``job`` labels must match that job's keep expression.
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
_SELECTOR = re.compile(
    r'([a-zA-Z_:][a-zA-Z0-9_:]*)\{[^}]*\bjob="(' + "|".join(PIPELINE_JOBS) + r')"'
)


def _keep_expressions() -> dict[str, re.Pattern[str] | None]:
    """Each pipeline job's keep expression; None for a job that keeps nothing."""
    config = yaml.safe_load(
        (OBSERVABILITY / "prometheus" / "prometheus.yml").read_text(encoding="utf-8")
    )
    jobs: dict[str, re.Pattern[str] | None] = {}
    for scrape in config["scrape_configs"]:
        if scrape["job_name"] not in PIPELINE_JOBS:
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
    rules = yaml.safe_load(
        (OBSERVABILITY / "prometheus" / "alerts-core.yml").read_text(encoding="utf-8")
    )
    for group in rules["groups"]:
        for rule in group["rules"]:
            found.append(("alerts-core.yml", rule["expr"]))
    return found


def test_every_pipeline_job_declares_what_it_keeps() -> None:
    assert set(_keep_expressions()) == set(PIPELINE_JOBS), "a pipeline job lost its scrape config"


def test_every_pipeline_series_a_panel_or_an_alert_reads_is_kept() -> None:
    keep = _keep_expressions()
    dropped = sorted(
        {
            (source, metric, job)
            for source, expr in _expressions()
            for metric, job in _SELECTOR.findall(expr)
            if metric != "up" and (keep[job] is None or not keep[job].match(metric))
        }
    )

    assert not dropped, f"series read but dropped by their job's keep-list: {dropped}"


def test_the_guard_sees_the_pipeline_series_it_exists_for() -> None:
    read = {metric for _, expr in _expressions() for metric, _ in _SELECTOR.findall(expr)}

    assert {"loki_write_dropped_entries_total", "tempo_distributor_spans_received_total"} <= read
