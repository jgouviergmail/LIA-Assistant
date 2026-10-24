#!/usr/bin/env python3
"""Which Prometheus metrics defined in code are wired into observability.

A metric nobody can see is a metric nobody acts on: ADR-148 shipped
``heartbeat_source_dropped_total`` precisely because a source that failed open
left no trace, and the defect went unnoticed for a week. This script measures
the inverse risk — a metric that EXISTS but reaches no dashboard, recording
rule or alert.

"Covered" means the metric name is referenced by at least one of:
  - a Grafana dashboard panel expression (rows walked recursively),
  - a Prometheus recording rule,
  - a Prometheus alerting rule.

Histograms/summaries are matched on their exposed suffixes too
(``_bucket`` / ``_count`` / ``_sum``), because a dashboard legitimately charts
``foo_bucket`` while the code defines ``foo``.

Usage (from any directory):
    python scripts/audit/measure_metric_coverage.py            # report
    python scripts/audit/measure_metric_coverage.py --json     # machine-readable
    python scripts/audit/measure_metric_coverage.py --update   # shrink the ratchet baseline
    python scripts/audit/measure_metric_coverage.py --producers  # every series read has a producer

Paths resolve from this file's location, so the script is CWD-independent
(F023 — the same trap that made the audit scripts fail from the repo root).
Standard library plus PyYAML, and the dashboard walker reused from
``scripts/observability/validate_observability.py`` (single source of truth for
how a Grafana row nests its children).
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "apps" / "api" / "src"
PROM_DIR = REPO_ROOT / "infrastructure" / "observability" / "prometheus"
BASELINE_PATH = REPO_ROOT / "apps" / "api" / "tests" / "unit" / "metric_coverage_baseline.json"

#: prometheus_client constructors whose first positional argument is the metric name.
METRIC_FACTORIES = frozenset({"Counter", "Gauge", "Histogram", "Summary", "Info", "Enum"})

#: Suffixes Prometheus exposes for histogram/summary families.
EXPOSED_SUFFIXES = ("", "_bucket", "_count", "_sum")


def _load_dashboard_walker() -> Any:
    """Reuse the observability validator's panel walker (nested rows included)."""
    path = REPO_ROOT / "scripts" / "observability" / "validate_observability.py"
    spec = importlib.util.spec_from_file_location("validate_observability", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rel(path: Path) -> str:
    """Repo-relative display path, falling back to the basename off-tree (tests)."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def metrics_defined_in_code(src_dir: Path | None = None) -> dict[str, str]:
    """Return ``{metric_name: repo-relative defining file}`` for every code metric.

    Parsed with AST rather than a regex: the constructors span several lines
    and carry comments, and a regex over source text cannot tell a metric
    constructor from a call that merely ends in one of those names. Measured
    2026-08-29 on this tree: 490 with AST against 491 with a regex, the extra
    entry being ``ZoneInfo("UTC")`` read as an ``Info`` metric.

    Args:
        src_dir: Backend source root; defaults to ``apps/api/src``.

    Returns:
        Mapping of metric name to the file that defines it.
    """
    root = src_dir or SRC_DIR
    found: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:  # pragma: no cover - defensive
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in METRIC_FACTORIES:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.setdefault(first.value, _rel(path))
    return found


def coverage_rule_files() -> list[Path]:
    """The rule files Prometheus loads — the ``rule_files`` of ``prometheus.yml``.

    Only a loaded rule reaches an operator. Every ``*.yml`` of the directory used
    to count, the dormant legacy catalogues and the unmounted product alerts
    included (audit AC-006), so a metric read by a rule that never evaluates
    would have looked wired.
    """
    walker = _load_dashboard_walker()
    files: list[Path] = walker._live_rule_files()
    return files


def _rules(path: Path) -> list[dict[str, Any]]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:  # pragma: no cover - validated by the observability guard
        return []
    return [rule for group in (doc or {}).get("groups") or [] for rule in group.get("rules") or []]


def _rule_expressions() -> list[str]:
    """PromQL from the loaded rule files — expressions only, never comments.

    Reading the YAML as raw text would let a metric mentioned in a comment
    ("# TODO: wire foo_total to a panel") count as coverage, which defeats the
    guard: the metric would look wired while reaching no operator.
    """
    return [
        rule["expr"]
        for path in coverage_rule_files()
        for rule in _rules(path)
        if isinstance(rule.get("expr"), str)
    ]


def observability_corpus() -> str:
    """Every dashboard panel expression plus every Prometheus rule expression."""
    walker = _load_dashboard_walker()
    parts: list[str] = []
    for dashboard in sorted(walker.DASHBOARD_DIR.glob("*.json")):
        data = json.loads(dashboard.read_text(encoding="utf-8"))
        parts.extend(walker._iter_panel_exprs(data.get("panels", []) or []))
    parts.extend(_rule_expressions())
    return "\n".join(parts)


def uncovered_metrics(
    defined: dict[str, str] | None = None, corpus: str | None = None
) -> list[str]:
    """Metric names defined in code but referenced nowhere in observability."""
    defined = defined if defined is not None else metrics_defined_in_code()
    blob = corpus if corpus is not None else observability_corpus()
    missing = []
    for name in defined:
        pattern = "|".join(re.escape(name + suffix) for suffix in EXPOSED_SUFFIXES)
        if not re.search(rf"\b(?:{pattern})\b", blob):
            missing.append(name)
    return sorted(missing)


# ---------------------------------------------------------------------------
# The other direction: every series an operator is shown has a producer (AC-006)
# ---------------------------------------------------------------------------

#: Grafana datasource values whose targets are PromQL (the rest is LogQL, TraceQL, SQL).
PROMETHEUS_DATASOURCES = frozenset({"prometheus", "$datasource"})

#: What a target naming no datasource reads: Grafana's default, provisioned as
#: Prometheus (``grafana/provisioning/datasources/datasources.yml``, ``isDefault``).
DEFAULT_DATASOURCE = "prometheus"

#: Series families no LIA code defines, each with what produces it: a scrape job of
#: prometheus.yml, or Tempo's metrics generator writing span metrics remotely. The
#: guard checks every producer named here is configured, so the list cannot hold a
#: family nothing feeds any more.
EXTERNAL_PRODUCERS: dict[str, str] = {
    "container_": "job:cadvisor",
    "node_": "job:node",
    "pg_": "job:postgresql",
    "redis_": "job:redis",
    "probe_": "job:blackbox",
    "prometheus_": "job:prometheus",
    "loki_": "job:loki",
    "tempo_": "job:tempo",
    "traces_spanmetrics_": "remote_write:infrastructure/observability/tempo/tempo.yml",
}

#: Series Prometheus synthesizes for every target it scrapes.
SYNTHETIC_SERIES = frozenset({"up"})

_PROMQL_NOISE = (
    re.compile(r"#[^\n]*"),  # comments of multi-line rule expressions
    re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`[^`]*`'),  # string literals
    re.compile(r"\$\{[^}]*\}|\$\w+"),  # Grafana variables
    re.compile(r"\{[^{}]*\}"),  # label matchers
    re.compile(r"\[[^\]]*\]"),  # ranges and subqueries
    re.compile(r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)"),
)
_PROMQL_KEYWORDS = frozenset(
    {"by", "without", "on", "ignoring", "group_left", "group_right", "offset", "bool", "and",
     "or", "unless", "atan2", "inf", "nan", "Inf", "NaN"}
)  # fmt: skip
_SERIES_TOKEN = re.compile(r"\b([a-zA-Z_:][a-zA-Z0-9_:]*)\b(?!\s*\()")


def series_read(expr: str) -> set[str]:
    """The series names a PromQL expression reads — never a function, label or variable."""
    for noise in _PROMQL_NOISE:
        expr = noise.sub(" ", expr)
    return {token for token in _SERIES_TOKEN.findall(expr) if token not in _PROMQL_KEYWORDS}


def _datasource_kind(datasource: Any) -> str:
    """A datasource's type, else its uid — a target naming none reads the default."""
    if isinstance(datasource, dict):
        datasource = datasource.get("type") or datasource.get("uid")
    return str(datasource) if datasource else DEFAULT_DATASOURCE


def _panel_expressions(
    dashboard: Path, panels: list[dict[str, Any]], inherited: Any = None
) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for panel in panels:
        datasource = panel.get("datasource") or inherited
        for target in panel.get("targets", []) or []:
            kind = _datasource_kind(target.get("datasource") or datasource)
            if "expr" in target and kind in PROMETHEUS_DATASOURCES:
                found.append((f"{dashboard.name}: {panel.get('title', '?')}", target["expr"]))
        found += _panel_expressions(dashboard, panel.get("panels", []) or [], datasource)
    return found


def prometheus_expressions(dashboard_dir: Path | None = None) -> list[tuple[str, str]]:
    """``(source, expr)`` for every PromQL target of a dashboard and every loaded rule.

    Args:
        dashboard_dir: Dashboards to read; the provisioned ones by default.

    Returns:
        Each expression with where it is shown, ``<dashboard>: <panel title>`` or
        ``<rule file>: <alert or record>``.
    """
    directory = dashboard_dir or _load_dashboard_walker().DASHBOARD_DIR
    found: list[tuple[str, str]] = []
    for dashboard in sorted(directory.glob("*.json")):
        data = json.loads(dashboard.read_text(encoding="utf-8"))
        found += _panel_expressions(dashboard, data.get("panels", []) or [])
    for path in coverage_rule_files():
        for rule in _rules(path):
            if isinstance(rule.get("expr"), str):
                found.append(
                    (f"{path.name}: {rule.get('alert') or rule.get('record')}", rule["expr"])
                )
    return found


def _produced_series() -> set[str]:
    """Every series the code exposes: each metric with the suffixes its family adds."""
    produced: set[str] = set()
    for name in metrics_defined_in_code():
        base = name.removesuffix("_total")
        for suffix in ("", "_total", "_bucket", "_count", "_sum", "_created"):
            produced |= {name + suffix, base + suffix}
    for path in coverage_rule_files():
        produced |= {rule["record"] for rule in _rules(path) if "record" in rule}
    return produced


def series_without_producer(
    expressions: list[tuple[str, str]] | None = None,
) -> dict[str, list[str]]:
    """Series read by a panel or a loaded rule that nothing produces.

    Args:
        expressions: ``(source, expr)`` pairs; every dashboard and loaded rule by default.

    Returns:
        ``{series: [sources]}`` — empty when every series has a producer.
    """
    produced = _produced_series()
    orphans: dict[str, list[str]] = {}
    for source, expr in expressions if expressions is not None else prometheus_expressions():
        for series in sorted(series_read(expr) - produced - SYNTHETIC_SERIES):
            if not any(series.startswith(prefix) for prefix in EXTERNAL_PRODUCERS):
                orphans.setdefault(series, []).append(source)
    return orphans


def unconfigured_external_producers() -> list[str]:
    """Declared external producers that nothing configures — the declaration must stay true."""
    scrape = yaml.safe_load((PROM_DIR / "prometheus.yml").read_text(encoding="utf-8")) or {}
    jobs = {config.get("job_name") for config in scrape.get("scrape_configs") or []}
    missing = []
    for prefix, producer in EXTERNAL_PRODUCERS.items():
        kind, _, where = producer.partition(":")
        if kind == "job" and where not in jobs:
            missing.append(f"{prefix} names scrape job {where!r}, absent from prometheus.yml")
        elif kind == "remote_write" and "remote_write" not in (REPO_ROOT / where).read_text(
            encoding="utf-8"
        ):
            missing.append(f"{prefix} names a remote write {where} does not configure")
    return missing


def load_baseline() -> list[str]:
    """The allowlist of metrics knowingly not wired to any dashboard."""
    if not BASELINE_PATH.exists():
        return []
    return list(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["uncovered"])


def _write_baseline(uncovered: list[str]) -> None:
    """Persist the shrink-only allowlist (sorted, with its own doc header)."""
    payload = {
        "_doc": (
            "Metrics defined in code that no dashboard, recording rule or alert "
            "references. Enforced by tests/unit/test_metric_coverage_ratchet_guard.py. "
            "SHRINK-ONLY: wire a metric to a panel and remove it here (run "
            "`task ratchet:metrics`). Adding an entry means shipping a metric nobody "
            "can see — justify it in review."
        ),
        "uncovered": sorted(uncovered),
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _update_baseline(defined: dict[str, str], missing: list[str]) -> int:
    """Shrink the baseline to what is still uncovered; never add an entry.

    Mirrors ``update_file_size_baseline.py``: absorbing a newly blind metric here
    would turn the ratchet into a rubber stamp — the exact failure mode ADR-148
    was about, a signal disappearing with nobody noticing. A new uncovered metric
    must be wired to a panel, or added by hand with a reason in review.
    """
    previous = set(load_baseline())
    kept = sorted(previous & set(missing))
    unlisted = sorted(set(missing) - previous)
    for name in sorted(previous - set(missing)):
        print(f"  removed (now covered): {name}")
    _write_baseline(kept)
    print(f"baseline: {len(previous)} -> {len(kept)} entries")
    if unlisted:
        print(f"\nREFUSED to add {len(unlisted)} newly blind metric(s):")
        for name in unlisted:
            print(f"  - {name}  ({defined[name]})")
        print("Wire each to a panel, or add it to the baseline by hand with a reason.")
        return 1
    return 0


def _check_producers() -> int:
    """Refuse a series read with no producer, or a declared producer nothing configures."""
    orphans = series_without_producer()
    unconfigured = unconfigured_external_producers()
    if not orphans and not unconfigured:
        print("producers: every series a panel or a loaded rule reads has a producer.")
        return 0
    print(
        f"::error::{len(orphans)} series read with no producer, "
        f"{len(unconfigured)} declared producer(s) not configured:"
    )
    for series, sources in sorted(orphans.items()):
        print(f"  {series}  <- {', '.join(sorted(sources))}")
    for problem in unconfigured:
        print(f"  {problem}")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Print the coverage report; ``--update`` shrinks the ratchet baseline."""
    args = argv if argv is not None else sys.argv[1:]
    if "--producers" in args:
        return _check_producers()
    defined = metrics_defined_in_code()
    missing = uncovered_metrics(defined)
    covered = len(defined) - len(missing)

    if "--json" in args:
        print(json.dumps({"defined": len(defined), "covered": covered, "uncovered": missing}))
        return 0

    if "--update" in args:
        return _update_baseline(defined, missing)

    print(f"defined={len(defined)} covered={covered} uncovered={len(missing)}")
    print(f"coverage: {100 * covered / len(defined):.1f}%")
    for name in missing:
        print(f"  {name}  ({defined[name]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
