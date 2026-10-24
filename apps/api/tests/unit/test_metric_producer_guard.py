"""Every series a dashboard panel or a loaded rule reads has a producer (audit AC-006).

The coverage ratchet holds one direction — a metric the code defines reaches a
panel. The other was unguarded: a panel may query a series nobody produces and
draw « No data » for ever, and four did (the product cost and time to a useful
outcome, a hybrid memory search that does not exist). Here every PromQL
expression of a Prometheus panel, or of a rule file ``prometheus.yml`` loads,
resolves each series it reads to a metric the code defines (its exposed suffixes
included), a recording rule, or a declared external producer whose scrape job or
push is configured. A Loki, Tempo or PostgreSQL query is never read as PromQL.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
MEASURE_PATH = REPO_ROOT / "scripts" / "audit" / "measure_metric_coverage.py"
WALKER_PATH = REPO_ROOT / "scripts" / "observability" / "validate_observability.py"


def _load(name: str, path: Path) -> ModuleType:
    if not path.exists():
        pytest.skip("guard needs the full repository checkout (scripts/).")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def measurer() -> ModuleType:
    return _load("measure_metric_coverage", MEASURE_PATH)


def test_every_series_a_panel_or_a_loaded_rule_reads_has_a_producer(measurer: ModuleType) -> None:
    orphans = measurer.series_without_producer()

    assert orphans == {}, "series read with no producer:\n" + "\n".join(
        f"  {series}  <- {', '.join(sorted(sources))}"
        for series, sources in sorted(orphans.items())
    )


def test_a_panel_reading_a_series_nobody_produces_is_caught(
    measurer: ModuleType, tmp_path: Path
) -> None:
    dashboard = {
        "panels": [
            {
                "title": "Phantom",
                "datasource": "$datasource",
                "targets": [{"expr": "sum(rate(lia_phantom_total[5m]))"}],
            },
            {
                "title": "Produced",
                "datasource": {"type": "prometheus", "uid": "$datasource"},
                "targets": [{"expr": "sum(rate(http_requests_total[5m]))"}],
            },
        ]
    }
    (tmp_path / "99-phantom.json").write_text(json.dumps(dashboard), encoding="utf-8")

    orphans = measurer.series_without_producer(measurer.prometheus_expressions(tmp_path))

    assert set(orphans) == {"lia_phantom_total"}
    assert orphans["lia_phantom_total"] == ["99-phantom.json: Phantom"]


@pytest.mark.parametrize(
    "datasource",
    [None, {"uid": "prometheus"}, {"type": "prometheus"}],
    ids=["named-nowhere", "by-uid-only", "by-type-only"],
)
def test_a_target_reading_the_default_or_naming_prometheus_by_uid_is_promql(
    measurer: ModuleType, tmp_path: Path, datasource: dict[str, str] | None
) -> None:
    """Grafana's default datasource is Prometheus (``datasources.yml``, ``isDefault``)."""
    panel: dict[str, object] = {
        "title": "Phantom",
        "targets": [{"expr": "sum(rate(lia_phantom_total[5m]))"}],
    }
    if datasource is not None:
        panel["datasource"] = datasource
    (tmp_path / "97-default.json").write_text(json.dumps({"panels": [panel]}), encoding="utf-8")

    orphans = measurer.series_without_producer(measurer.prometheus_expressions(tmp_path))

    assert orphans == {"lia_phantom_total": ["97-default.json: Phantom"]}


def test_a_loki_query_is_never_read_as_promql(measurer: ModuleType, tmp_path: Path) -> None:
    logs = 'sum(count_over_time({container="lia-api"} |= "phantom_error" [5m]))'
    dashboard = {
        "panels": [
            {"title": "Logs", "datasource": {"type": "loki"}, "targets": [{"expr": logs}]},
            {
                "title": "Row",
                "panels": [
                    {
                        "title": "Nested logs",
                        "datasource": "$datasource_loki",
                        "targets": [{"expr": logs}],
                    }
                ],
            },
        ]
    }
    (tmp_path / "98-logs.json").write_text(json.dumps(dashboard), encoding="utf-8")

    sources = {source for source, _ in measurer.prometheus_expressions(tmp_path)}

    assert not {source for source in sources if source.startswith("98-logs.json")}


@pytest.mark.parametrize(
    ("expr", "series"),
    [
        (
            'sum by (status) (rate(foo_total{job="lia-api", status=~"5.."}[$__rate_interval]))',
            {"foo_total"},
        ),
        ("histogram_quantile(0.95, sum by (le) (rate(bar_bucket[5m])))", {"bar_bucket"}),
        ('label_replace(up, "dst", "$1", "src", "(.*)") or vector(0)', {"up"}),
        ("a_total / ignoring(job) group_left(instance) b_total offset 1h", {"a_total", "b_total"}),
        ("increase(x_total[7d]) > bool 0  # a comment naming ghost_total", {"x_total"}),
        ("job:http_requests:rate5m * on (instance) ${scale}", {"job:http_requests:rate5m"}),
    ],
)
def test_the_extractor_reads_series_never_functions_labels_or_variables(
    measurer: ModuleType, expr: str, series: set[str]
) -> None:
    assert measurer.series_read(expr) == series


def test_every_declared_external_producer_is_configured(measurer: ModuleType) -> None:
    assert measurer.unconfigured_external_producers() == []


def test_the_lint_mode_refuses_a_series_nobody_produces(
    measurer: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    phantom = [("99-phantom.json: Phantom", "sum(rate(lia_phantom_total[5m]))")]
    monkeypatch.setattr(measurer, "prometheus_expressions", lambda dashboard_dir=None: phantom)

    assert measurer.main(["--producers"]) == 1
    assert "lia_phantom_total  <- 99-phantom.json: Phantom" in capsys.readouterr().out


def test_the_lint_mode_refuses_an_external_producer_nothing_configures(
    measurer: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    problem = "ghost_ names scrape job 'ghost', absent from prometheus.yml"
    monkeypatch.setattr(measurer, "unconfigured_external_producers", lambda: [problem])

    assert measurer.main(["--producers"]) == 1
    assert problem in capsys.readouterr().out


def test_lint_observability_runs_the_lint_mode_and_the_tree_passes_it(
    measurer: ModuleType,
) -> None:
    taskfile = (REPO_ROOT / "Taskfile.yml").read_text(encoding="utf-8")
    task = taskfile[taskfile.index("  lint:observability:") :]
    task = task[: task.index("\n\n")]

    assert task.count("scripts/audit/measure_metric_coverage.py --producers") == 2
    assert measurer.main(["--producers"]) == 0


def test_coverage_reads_the_rule_files_prometheus_loads_and_no_other(
    measurer: ModuleType,
) -> None:
    walker = _load("validate_observability", WALKER_PATH)

    assert measurer.coverage_rule_files() == walker._live_rule_files()
    read = {path.name for path in measurer.coverage_rule_files()}
    assert "alerts-product.yml" not in read and "alerts.yml" not in read
