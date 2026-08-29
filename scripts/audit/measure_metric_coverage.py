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


def _rule_expressions() -> list[str]:
    """PromQL from the Prometheus rule files — expressions only, never comments.

    Reading the YAML as raw text would let a metric mentioned in a comment
    ("# TODO: wire foo_total to a panel") count as coverage, which defeats the
    guard: the metric would look wired while reaching no operator.
    """
    exprs: list[str] = []
    for path in sorted(PROM_DIR.rglob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover - validated by the observability guard
            continue
        for group in (doc or {}).get("groups") or []:
            for rule in group.get("rules") or []:
                expr = rule.get("expr")
                if isinstance(expr, str):
                    exprs.append(expr)
    return exprs


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


def main(argv: list[str] | None = None) -> int:
    """Print the coverage report; ``--update`` shrinks the ratchet baseline."""
    args = argv if argv is not None else sys.argv[1:]
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
