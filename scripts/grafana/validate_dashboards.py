#!/usr/bin/env python3
"""
Grafana Dashboards Validation Script

Validates that all Prometheus metrics referenced in Grafana dashboards
are actually exposed by the Prometheus /metrics endpoint.

This prevents dashboard panels showing "NO DATA" due to:
- Metric name typos
- Metrics renamed but dashboards not updated
- Metrics defined but never instrumented

Usage:
    python scripts/validate_dashboards.py [--prometheus-url URL]

Exit codes:
    0: All metrics found
    1: Missing metrics detected
    2: Error (connection, parsing, etc.)

Example:
    python scripts/validate_dashboards.py
    python scripts/validate_dashboards.py --prometheus-url http://localhost:9090

Author: Claude (Anthropic)
Date: 2025-11-07
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Set, Dict, List
from urllib.request import urlopen
from urllib.error import URLError


def extract_metrics_from_promql(expr: str) -> Set[str]:
    """
    Extract metric names from a PromQL expression.

    Handles:
    - Simple metrics: metric_name
    - With labels: metric_name{label="value"}
    - With range: metric_name[5m]
    - Functions: rate(metric_name[5m])
    - Complex queries: histogram_quantile(0.95, sum(rate(metric_name_bucket[5m])) by (le))

    Args:
        expr: PromQL expression string

    Returns:
        Set of metric names found in the expression
    """
    if not expr:
        return set()

    # Pattern: metric_name (letters, numbers, underscores, colons)
    # Must not be preceded by a letter/number (to avoid matching function names)
    # Must be followed by: {, [, space, operator, or end of string
    pattern = r'(?<![a-zA-Z0-9_])([a-z_][a-z0-9_:]*(?:_bucket|_sum|_count|_total)?)'

    metrics = set()
    for match in re.finditer(pattern, expr):
        metric = match.group(1)

        # Filter out PromQL functions (they're lowercase but metrics usually have underscores)
        if metric in {
            'sum', 'rate', 'increase', 'histogram_quantile', 'by', 'avg', 'max', 'min',
            'count', 'stddev', 'stdvar', 'topk', 'bottomk', 'quantile', 'count_values',
            'le', 'and', 'or', 'unless', 'offset', 'bool', 'on', 'ignoring', 'group_left',
            'group_right', 'abs', 'ceil', 'floor', 'exp', 'ln', 'log2', 'log10', 'sqrt',
            'time', 'timestamp', 'sort', 'sort_desc', 'clamp_max', 'clamp_min'
        }:
            continue

        metrics.add(metric)

    return metrics


def extract_metrics_from_dashboard(dashboard_path: Path) -> Dict[str, Set[str]]:
    """
    Extract all Prometheus metric names from a Grafana dashboard JSON.

    Args:
        dashboard_path: Path to dashboard JSON file

    Returns:
        Dict mapping panel title to set of metrics used
    """
    try:
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            dashboard = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️  Error reading {dashboard_path.name}: {e}", file=sys.stderr)
        return {}

    panel_metrics = {}

    # Recursively extract metrics from panels
    def extract_from_panels(panels: List):
        for panel in panels:
            if not isinstance(panel, dict):
                continue

            panel_title = panel.get('title', 'Unknown Panel')
            panel_type = panel.get('type', '')

            # Skip row panels (they're just headers)
            if panel_type == 'row':
                continue

            # Extract from targets (Prometheus queries)
            targets = panel.get('targets', [])
            metrics = set()

            for target in targets:
                if not isinstance(target, dict):
                    continue

                # Prometheus expression
                expr = target.get('expr', '')
                if expr:
                    metrics.update(extract_metrics_from_promql(expr))

                # Also check 'query' field (some dashboards use this)
                query = target.get('query', '')
                if isinstance(query, str):
                    metrics.update(extract_metrics_from_promql(query))

            if metrics:
                panel_metrics[panel_title] = metrics

            # Recursively check nested panels (for collapsed rows)
            if 'panels' in panel:
                extract_from_panels(panel['panels'])

    # Extract from top-level panels
    panels = dashboard.get('panels', [])
    extract_from_panels(panels)

    return panel_metrics


def get_prometheus_metrics(prometheus_url: str) -> Set[str]:
    """
    Fetch all metric names exposed by Prometheus.

    Args:
        prometheus_url: Prometheus base URL (e.g., http://localhost:9090)

    Returns:
        Set of metric names

    Raises:
        URLError: If Prometheus is unreachable
    """
    label_values_url = f"{prometheus_url}/api/v1/label/__name__/values"

    try:
        with urlopen(label_values_url) as response:
            data = json.loads(response.read().decode('utf-8'))

            if data.get('status') != 'success':
                raise ValueError(f"Prometheus API returned status: {data.get('status')}")

            return set(data['data'])

    except URLError as e:
        raise URLError(f"Cannot connect to Prometheus at {prometheus_url}: {e}")


def validate_dashboards(
    dashboards_dir: Path,
    prometheus_url: str
) -> bool:
    """
    Validate all dashboards against Prometheus metrics.

    Args:
        dashboards_dir: Path to Grafana dashboards directory
        prometheus_url: Prometheus base URL

    Returns:
        True if all metrics found, False if missing metrics
    """
    print(f"🔍 Validating Grafana dashboards in: {dashboards_dir}")
    print(f"📊 Fetching metrics from Prometheus: {prometheus_url}")
    print()

    # Get all exposed metrics
    try:
        prometheus_metrics = get_prometheus_metrics(prometheus_url)
        print(f"✅ Found {len(prometheus_metrics)} metrics in Prometheus")
        print()
    except (URLError, ValueError) as e:
        print(f"❌ Error fetching Prometheus metrics: {e}", file=sys.stderr)
        print()
        print("💡 Is Prometheus running? Try: docker-compose up -d prometheus", file=sys.stderr)
        return False

    # Validate each dashboard
    dashboard_files = sorted(dashboards_dir.glob('*.json'))

    if not dashboard_files:
        print(f"⚠️  No dashboard files found in {dashboards_dir}", file=sys.stderr)
        return False

    all_valid = True
    total_panels = 0
    total_metrics = 0
    missing_by_dashboard = {}

    for dashboard_file in dashboard_files:
        print(f"📄 Validating {dashboard_file.name}...")

        panel_metrics = extract_metrics_from_dashboard(dashboard_file)

        if not panel_metrics:
            print(f"   ⚠️  No Prometheus panels found (might be Loki/Tempo only)")
            print()
            continue

        dashboard_missing = {}

        for panel_title, metrics in panel_metrics.items():
            total_panels += 1
            total_metrics += len(metrics)

            missing = metrics - prometheus_metrics

            if missing:
                dashboard_missing[panel_title] = missing
                all_valid = False

        if dashboard_missing:
            missing_by_dashboard[dashboard_file.name] = dashboard_missing
            print(f"   ❌ {len(dashboard_missing)} panels with missing metrics")
        else:
            print(f"   ✅ All metrics found ({len(panel_metrics)} panels)")

        print()

    # Print summary
    print("=" * 80)
    print("📊 VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Dashboards validated: {len(dashboard_files)}")
    print(f"Panels checked: {total_panels}")
    print(f"Unique metrics referenced: {total_metrics}")
    print()

    if all_valid:
        print("✅ SUCCESS: All dashboard metrics are exposed by Prometheus!")
        print()
        return True

    # Print detailed missing metrics report
    print("❌ MISSING METRICS DETECTED")
    print()

    for dashboard_name, panels in missing_by_dashboard.items():
        print(f"Dashboard: {dashboard_name}")
        print("-" * 80)

        for panel_title, metrics in panels.items():
            print(f"  Panel: {panel_title}")
            for metric in sorted(metrics):
                print(f"    ❌ {metric}")
        print()

    print("💡 TROUBLESHOOTING:")
    print("  1. Check if metrics are defined but not instrumented")
    print("     → Search codebase: grep -r 'metric_name' apps/api/src/")
    print()
    print("  2. Check if metric was renamed")
    print("     → Review git history: git log --all --full-history -- '*metrics*.py'")
    print()
    print("  3. Check /metrics endpoint directly")
    print(f"     → curl {os.getenv('API_URL', 'http://localhost:8000')}/metrics | grep metric_name")
    print()

    return False


def main():
    parser = argparse.ArgumentParser(
        description="Validate Grafana dashboards against Prometheus metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate with default Prometheus URL
  python scripts/validate_dashboards.py

  # Validate with custom Prometheus URL
  python scripts/validate_dashboards.py --prometheus-url http://prometheus:9090

Exit codes:
  0 - All metrics found (success)
  1 - Missing metrics detected
  2 - Error (connection, parsing, etc.)
        """
    )

    parser.add_argument(
        '--prometheus-url',
        default='http://localhost:9090',
        help='Prometheus base URL (default: http://localhost:9090)'
    )

    parser.add_argument(
        '--dashboards-dir',
        type=Path,
        default=Path('infrastructure/observability/grafana/dashboards'),
        help='Path to Grafana dashboards directory'
    )

    args = parser.parse_args()

    # Validate dashboards directory exists
    if not args.dashboards_dir.exists():
        print(f"❌ Dashboards directory not found: {args.dashboards_dir}", file=sys.stderr)
        print()
        print(f"💡 Run from project root: cd {Path.cwd().parent}", file=sys.stderr)
        return 2

    try:
        success = validate_dashboards(args.dashboards_dir, args.prometheus_url)
        return 0 if success else 1

    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == '__main__':
    sys.exit(main())
