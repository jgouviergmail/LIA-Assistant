#!/usr/bin/env python3
"""
Analyze alerts.yml to extract all hardcoded thresholds and generate environment variable mapping.

This script:
1. Parses alerts.yml to find all numeric thresholds
2. Generates environment variable names following naming convention
3. Creates mapping for template replacement
4. Outputs summary report

Usage:
    python analyze_thresholds.py

Output:
    - Console: Summary report of all thresholds found
    - threshold_mapping.json: Mapping for template replacement
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

def extract_thresholds_from_expr(expr: str, alert_name: str, component: str) -> List[Tuple[str, float, str]]:
    """
    Extract numeric thresholds from PromQL expression.

    Returns: List of (context, value, unit) tuples
    """
    thresholds = []

    # Pattern 1: "> NUMBER" or "< NUMBER"
    pattern1 = r'([><]=?)\s*(\d+(?:\.\d+)?)'
    for match in re.finditer(pattern1, expr):
        operator = match.group(1)
        value = float(match.group(2))

        # Infer context from expression
        context = ""
        if "* 100" in expr and operator == ">":
            context = "percent"
        elif "* 1000" in expr:
            context = "milliseconds"
        elif "_seconds" in expr:
            context = "seconds"
        elif "_bytes" in expr:
            context = "bytes"
        elif "rate(" in expr:
            context = "rate"

        thresholds.append((context, value, operator))

    return thresholds


def analyze_alerts_file(file_path: Path) -> Dict:
    """
    Analyze alerts.yml and extract all thresholds with metadata.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    results = {
        'total_alerts': 0,
        'alerts_with_thresholds': 0,
        'total_thresholds': 0,
        'by_component': defaultdict(list),
        'by_severity': defaultdict(int),
        'threshold_details': []
    }

    for group in data.get('groups', []):
        group_name = group.get('name', 'unknown')

        for rule in group.get('rules', []):
            results['total_alerts'] += 1

            alert_name = rule.get('alert', 'unknown')
            expr = rule.get('expr', '')
            labels = rule.get('labels', {})
            annotations = rule.get('annotations', {})

            severity = labels.get('severity', 'unknown')
            component = labels.get('component', 'unknown')

            # Extract thresholds
            thresholds = extract_thresholds_from_expr(expr, alert_name, component)

            if thresholds:
                results['alerts_with_thresholds'] += 1
                results['total_thresholds'] += len(thresholds)
                results['by_severity'][severity] += 1

                for context, value, operator in thresholds:
                    threshold_info = {
                        'alert_name': alert_name,
                        'group': group_name,
                        'component': component,
                        'severity': severity,
                        'value': value,
                        'operator': operator,
                        'context': context,
                        'expr': expr.strip(),
                        'description': annotations.get('description', ''),
                        'summary': annotations.get('summary', '')
                    }
                    results['threshold_details'].append(threshold_info)
                    results['by_component'][component].append(threshold_info)

    return results


def generate_env_var_name(threshold_info: Dict) -> str:
    """
    Generate environment variable name following convention:
    ALERT_{COMPONENT}_{METRIC}_{SEVERITY}_{UNIT}

    Examples:
        ALERT_API_ERROR_RATE_CRITICAL_PERCENT
        ALERT_AGENTS_TTFT_WARNING_MS
        ALERT_LLM_DAILY_BUDGET_EUR
    """
    component = threshold_info['component'].upper().replace('-', '_')
    severity = threshold_info['severity'].upper()
    alert_name = threshold_info['alert_name']
    context = threshold_info['context']

    # Extract metric from alert name
    # Examples: HighErrorRate -> ERROR_RATE, AgentsTTFTViolation -> TTFT
    metric = ""

    if "ErrorRate" in alert_name:
        metric = "ERROR_RATE"
    elif "Latency" in alert_name:
        if "P95" in alert_name:
            metric = "LATENCY_P95"
        elif "P99" in alert_name:
            metric = "LATENCY_P99"
        else:
            metric = "LATENCY"
    elif "TTFT" in alert_name:
        metric = "TTFT_P95"
    elif "Router" in alert_name and "Latency" in alert_name:
        metric = "ROUTER_LATENCY_P95"
    elif "Connections" in alert_name:
        metric = "CONNECTIONS"
    elif "Memory" in alert_name:
        metric = "MEMORY"
    elif "CPU" in alert_name:
        metric = "CPU"
    elif "Disk" in alert_name:
        metric = "DISK"
    elif "Budget" in alert_name:
        if "Daily" in alert_name:
            metric = "DAILY_BUDGET"
        elif "Hourly" in alert_name:
            metric = "HOURLY_BUDGET"
        elif "Model" in alert_name:
            metric = "MODEL_BUDGET"
        else:
            metric = "BUDGET"
    elif "Token" in alert_name:
        metric = "TOKEN_RATE"
    else:
        # Fallback: extract from alert name
        metric = re.sub(r'([A-Z])', r'_\1', alert_name).strip('_').upper()

    # Unit suffix
    unit = ""
    if context == "percent":
        unit = "PERCENT"
    elif context == "milliseconds":
        unit = "MS"
    elif context == "seconds":
        unit = "SECONDS"
    elif context == "bytes":
        unit = "BYTES"
    elif "EUR" in threshold_info['description'] or "€" in threshold_info['description']:
        unit = "EUR"

    # Construct env var name
    parts = ["ALERT", component, metric, severity]
    if unit:
        parts.append(unit)

    env_var = "_".join(part for part in parts if part)

    # Clean up
    env_var = env_var.replace("__", "_").replace("CRITICAL_WARNING", severity)

    return env_var


def print_report(results: Dict):
    """Print analysis report to console."""
    print("=" * 80)
    print("ALERTS.YML THRESHOLD ANALYSIS REPORT")
    print("=" * 80)
    print()
    print(f"Total alerts: {results['total_alerts']}")
    print(f"Alerts with thresholds: {results['alerts_with_thresholds']}")
    print(f"Total hardcoded thresholds: {results['total_thresholds']}")
    print()

    print("Thresholds by Severity:")
    for severity, count in sorted(results['by_severity'].items()):
        print(f"  {severity.upper():15s}: {count:3d} alerts")
    print()

    print("Thresholds by Component:")
    for component, thresholds in sorted(results['by_component'].items()):
        print(f"  {component:15s}: {len(thresholds):3d} thresholds")
    print()

    print("=" * 80)
    print("DETAILED THRESHOLD LISTING")
    print("=" * 80)
    print()

    for i, threshold in enumerate(results['threshold_details'], 1):
        env_var = generate_env_var_name(threshold)
        print(f"{i}. Alert: {threshold['alert_name']}")
        print(f"   Component: {threshold['component']} | Severity: {threshold['severity']}")
        print(f"   Threshold: {threshold['operator']} {threshold['value']} ({threshold['context']})")
        print(f"   Env Var: {env_var}")
        print(f"   Summary: {threshold['summary']}")
        print()


if __name__ == "__main__":
    alerts_file = Path(__file__).parent / "alerts.yml"

    if not alerts_file.exists():
        print(f"ERROR: {alerts_file} not found!")
        exit(1)

    print(f"Analyzing {alerts_file}...")
    print()

    results = analyze_alerts_file(alerts_file)
    print_report(results)

    print("=" * 80)
    print(f"Analysis complete! Found {results['total_thresholds']} hardcoded thresholds.")
    print("=" * 80)
