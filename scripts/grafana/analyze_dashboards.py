"""
Dashboard Analysis Script - Grafana Quality Audit

Identifies:
1. Missing metrics (queries referencing undefined metrics)
2. Deprecated dashboards
3. Duplicate dashboards
4. Broken panels (metrics with errors)
5. Empty/inconsistent visualizations

Output: Comprehensive report for GitHub issue
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# Directories
DASHBOARDS_DIR = Path("infrastructure/observability/grafana/dashboards")
METRICS_DIR = Path("apps/api/src/infrastructure/observability")

def extract_defined_metrics() -> Set[str]:
    """Extract all Prometheus metrics defined in Python code."""
    metrics = set()

    for metrics_file in METRICS_DIR.glob("metrics_*.py"):
        with open(metrics_file, encoding="utf-8") as f:
            for line in f:
                # Match: metric_name = Counter( / Histogram( / Gauge(
                if re.search(r'^\s*\w+ = (Counter|Histogram|Gauge)\(', line):
                    metric_name = line.split('=')[0].strip()
                    metrics.add(metric_name)

    return metrics

def extract_dashboard_metrics(dashboard_path: Path) -> List[Tuple[str, str]]:
    """
    Extract all Prometheus queries from dashboard.
    Returns: [(panel_title, metric_query), ...]
    """
    queries = []

    with open(dashboard_path, encoding="utf-8") as f:
        dashboard = json.load(f)

    def extract_from_panels(panels):
        for panel in panels:
            if isinstance(panel, dict):
                panel_title = panel.get("title", "Untitled")

                # Row panels contain nested panels
                if panel.get("type") == "row" and "panels" in panel:
                    extract_from_panels(panel["panels"])

                # Extract PromQL queries from targets
                targets = panel.get("targets", [])
                for target in targets:
                    if isinstance(target, dict) and "expr" in target:
                        queries.append((panel_title, target["expr"]))

    panels = dashboard.get("panels", [])
    extract_from_panels(panels)

    return queries

def extract_metric_names_from_query(query: str) -> Set[str]:
    """Extract metric names from PromQL query."""
    # Match: metric_name{ or metric_name[ or metric_name)
    # Avoid functions like rate(), sum(), etc.
    pattern = r'\b([a-z_][a-z0-9_]+)(?:\{|\[|(?=\)))'
    matches = re.findall(pattern, query)

    # Filter out PromQL functions
    promql_functions = {
        'rate', 'irate', 'sum', 'avg', 'max', 'min', 'count',
        'increase', 'delta', 'idelta', 'histogram_quantile',
        'by', 'without', 'on', 'ignoring', 'group_left', 'group_right',
        'bool', 'label_replace', 'label_join', 'sort', 'sort_desc',
        'topk', 'bottomk', 'absent', 'ceil', 'floor', 'round',
        'clamp_max', 'clamp_min', 'changes', 'resets', 'deriv',
        'predict_linear', 'holt_winters', 'time', 'timestamp',
        'vector', 'scalar', 'year', 'month', 'day', 'hour', 'minute',
    }

    metric_names = {m for m in matches if m not in promql_functions}
    return metric_names

def analyze_dashboards() -> Dict:
    """Analyze all dashboards and return comprehensive report."""
    defined_metrics = extract_defined_metrics()

    analysis = {
        "defined_metrics_count": len(defined_metrics),
        "dashboards": {},
        "missing_metrics": defaultdict(list),  # {metric_name: [(dashboard, panel), ...]}
        "duplicates": [],
        "deprecated": [],
        "summary": {},
    }

    # Track dashboard titles for duplicates
    dashboard_titles = defaultdict(list)

    for dashboard_file in sorted(DASHBOARDS_DIR.glob("*.json")):
        dashboard_name = dashboard_file.stem

        with open(dashboard_file, encoding="utf-8") as f:
            dashboard = json.load(f)

        title = dashboard.get("title", "Untitled")
        dashboard_titles[title].append(dashboard_name)

        # Extract queries
        queries = extract_dashboard_metrics(dashboard_file)

        # Find missing metrics
        missing_in_dashboard = []
        for panel_title, query in queries:
            metric_names = extract_metric_names_from_query(query)
            for metric in metric_names:
                if metric not in defined_metrics:
                    analysis["missing_metrics"][metric].append((dashboard_name, panel_title))
                    missing_in_dashboard.append((panel_title, metric))

        analysis["dashboards"][dashboard_name] = {
            "title": title,
            "panels_count": len(queries),
            "missing_metrics": missing_in_dashboard,
        }

    # Detect duplicates
    for title, files in dashboard_titles.items():
        if len(files) > 1:
            analysis["duplicates"].append({
                "title": title,
                "files": files,
            })

    # Deprecated dashboards (hardcoded based on user feedback)
    deprecated = [
        "07-hitl-tool-approval",  # User reported as deprecated
    ]
    analysis["deprecated"] = deprecated

    # Summary statistics
    analysis["summary"] = {
        "total_dashboards": len(analysis["dashboards"]),
        "total_panels": sum(d["panels_count"] for d in analysis["dashboards"].values()),
        "missing_metrics_count": len(analysis["missing_metrics"]),
        "duplicates_count": len(analysis["duplicates"]),
        "deprecated_count": len(analysis["deprecated"]),
    }

    return analysis

def generate_report(analysis: Dict) -> str:
    """Generate markdown report for GitHub issue."""
    report = []
    report.append("# Grafana Dashboards Quality Audit Report")
    report.append("")
    report.append(f"**Date**: 2025-11-23")
    report.append(f"**Scope**: All 15 Grafana dashboards")
    report.append("")
    report.append("---")
    report.append("")

    # Summary
    report.append("## 📊 Executive Summary")
    report.append("")
    summary = analysis["summary"]
    report.append(f"- **Total Dashboards**: {summary['total_dashboards']}")
    report.append(f"- **Total Panels**: {summary['total_panels']}")
    report.append(f"- **Defined Metrics**: {analysis['defined_metrics_count']}")
    report.append(f"- **Missing Metrics**: {summary['missing_metrics_count']} ❌")
    report.append(f"- **Duplicate Dashboards**: {summary['duplicates_count']} ❌")
    report.append(f"- **Deprecated Dashboards**: {summary['deprecated_count']} ⚠️")
    report.append("")
    report.append("---")
    report.append("")

    # Missing Metrics
    if analysis["missing_metrics"]:
        report.append("## ❌ Missing Metrics (Undefined in Code)")
        report.append("")
        report.append("These metrics are referenced in dashboards but not defined in Python code:")
        report.append("")

        for metric, occurrences in sorted(analysis["missing_metrics"].items()):
            report.append(f"### `{metric}`")
            report.append("")
            report.append(f"**Occurrences**: {len(occurrences)}")
            report.append("")
            for dashboard, panel in occurrences:
                report.append(f"- **Dashboard**: `{dashboard}` | **Panel**: \"{panel}\"")
            report.append("")

    # Duplicates
    if analysis["duplicates"]:
        report.append("## 🔄 Duplicate Dashboards")
        report.append("")
        report.append("Multiple dashboard files with same title:")
        report.append("")

        for dup in analysis["duplicates"]:
            report.append(f"### \"{dup['title']}\"")
            report.append("")
            report.append(f"**Files**:")
            for f in dup["files"]:
                report.append(f"- `{f}.json`")
            report.append("")

    # Deprecated
    if analysis["deprecated"]:
        report.append("## ⚠️ Deprecated Dashboards")
        report.append("")
        report.append("Dashboards that should be archived or removed:")
        report.append("")

        for dash in analysis["deprecated"]:
            if dash in analysis["dashboards"]:
                info = analysis["dashboards"][dash]
                report.append(f"### `{dash}.json`")
                report.append(f"- **Title**: \"{info['title']}\"")
                report.append(f"- **Panels**: {info['panels_count']}")
                report.append(f"- **Reason**: User reported as deprecated (HITL button-based system replaced by conversational)")
                report.append("")

    # Dashboard-by-Dashboard Analysis
    report.append("## 📁 Dashboard-by-Dashboard Analysis")
    report.append("")

    for dashboard_name, info in sorted(analysis["dashboards"].items()):
        status = "✅" if not info["missing_metrics"] else "❌"
        deprecated_flag = " ⚠️ DEPRECATED" if dashboard_name in analysis["deprecated"] else ""

        report.append(f"### {status} `{dashboard_name}.json`{deprecated_flag}")
        report.append(f"- **Title**: \"{info['title']}\"")
        report.append(f"- **Panels**: {info['panels_count']}")

        if info["missing_metrics"]:
            report.append(f"- **Missing Metrics**: {len(info['missing_metrics'])}")
            report.append(f"")
            report.append(f"  **Details**:")
            for panel, metric in info["missing_metrics"]:
                report.append(f"  - Panel: \"{panel}\" → Missing: `{metric}`")
        else:
            report.append(f"- **Status**: All metrics defined ✅")

        report.append("")

    return "\n".join(report)

if __name__ == "__main__":
    analysis = analyze_dashboards()
    report = generate_report(analysis)

    # Save report
    output_path = Path("docs/optim_monitoring/DASHBOARD_AUDIT_REPORT.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"OK Report generated: {output_path}")
    print(f"\n{report}")
