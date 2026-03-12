#!/usr/bin/env python3
"""
Test Dashboard 10 (Redis Rate Limiting) queries against Prometheus.

Diagnoses why some panels show data while others show "No data".
"""

import json
import requests
from pathlib import Path
from typing import Dict, Any

PROMETHEUS_URL = "http://localhost:9090"
DASHBOARD_PATH = Path("D:/Developpement/LIA/infrastructure/observability/grafana/dashboards/10-redis-rate-limiting.json")

def clean_query(query: str) -> str:
    """Replace Grafana variables with test values."""
    replacements = {
        "$key_prefix": ".*",  # Test with "All"
        "$datasource": "Prometheus",
        "$error_type": ".*",
        "$__interval": "5m",
        "$__rate_interval": "5m",
    }

    for var, value in replacements.items():
        query = query.replace(var, value)

    return query

def test_query(query: str, panel_title: str) -> Dict[str, Any]:
    """Test a PromQL query and return results."""
    try:
        clean_q = clean_query(query)

        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": clean_q},
            timeout=10
        )

        if response.status_code != 200:
            return {
                "status": "ERROR",
                "message": f"HTTP {response.status_code}",
                "query": clean_q[:100]
            }

        data = response.json()

        if data.get("status") != "success":
            return {
                "status": "ERROR",
                "message": data.get("error", "Unknown error"),
                "query": clean_q[:100]
            }

        results = data.get("data", {}).get("result", [])

        if len(results) == 0:
            return {
                "status": "NODATA",
                "message": "Query returns empty result set",
                "query": clean_q[:100]
            }

        # Check for NaN values
        has_nan = False
        values = []
        for result in results:
            value = result.get("value", [None, None])[1]
            if value in ["NaN", "Inf", "-Inf", None]:
                has_nan = True
            else:
                try:
                    values.append(float(value))
                except:
                    pass

        if has_nan or not values:
            return {
                "status": "NAN",
                "message": f"Result contains NaN/Inf ({len(results)} series)",
                "query": clean_q[:100]
            }

        return {
            "status": "OK",
            "message": f"{len(results)} series, values: {values}",
            "query": clean_q[:100]
        }

    except requests.exceptions.Timeout:
        return {"status": "ERROR", "message": "Query timeout", "query": query[:100]}
    except requests.exceptions.ConnectionError:
        return {"status": "ERROR", "message": "Cannot connect to Prometheus", "query": query[:100]}
    except Exception as e:
        return {"status": "ERROR", "message": str(e), "query": query[:100]}

def main():
    print("=" * 80)
    print("DASHBOARD 10 - Redis Rate Limiting Query Test")
    print("=" * 80)

    # Check Prometheus connectivity
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": "up"}, timeout=5)
        if response.status_code != 200:
            print(f"\nERROR: Cannot connect to Prometheus at {PROMETHEUS_URL}")
            return
        print(f"\nConnected to Prometheus at {PROMETHEUS_URL}\n")
    except Exception as e:
        print(f"\nERROR: {e}")
        return

    # Load dashboard
    with open(DASHBOARD_PATH, 'r', encoding='utf-8') as f:
        dashboard = json.load(f)

    panels = dashboard.get('panels', [])
    print(f"Total panels in dashboard: {len(panels)}\n")

    # Test key panels
    test_panels = [
        ("Rate Limit Hit Rate (%)", "stat"),
        ("Total Requests (req/s)", "stat"),
        ("Rate Limit Check Latency P95 (ms)", "stat"),
        ("Requests Allowed vs Rejected (req/s)", "timeseries"),
        ("Hit Rate by Endpoint (%)", "timeseries"),
    ]

    results = []

    for title_match, panel_type in test_panels:
        panel = next((p for p in panels if title_match in p.get('title', '') and p.get('type') == panel_type), None)

        if not panel:
            print(f"\nPanel '{title_match}' not found")
            continue

        panel_title = panel.get('title')
        print(f"\n--- Testing: {panel_title} ---")

        targets = panel.get('targets', [])
        for idx, target in enumerate(targets):
            query = target.get('expr', '')
            if not query:
                continue

            result = test_query(query, panel_title)
            results.append({
                "panel": panel_title,
                "query_idx": idx,
                **result
            })

            status_icon = {
                "OK": "OK",
                "NODATA": "NODATA",
                "NAN": "NaN",
                "ERROR": "ERROR"
            }.get(result["status"], "?")

            print(f"  Query #{idx}: [{status_icon}] {result['message']}")
            if result["status"] != "OK":
                print(f"    {result['query']}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    nodata_count = sum(1 for r in results if r["status"] == "NODATA")
    nan_count = sum(1 for r in results if r["status"] == "NAN")
    error_count = sum(1 for r in results if r["status"] == "ERROR")

    print(f"\nTotal queries tested: {len(results)}")
    print(f"  OK: {ok_count}")
    print(f"  NODATA: {nodata_count}")
    print(f"  NaN: {nan_count}")
    print(f"  ERROR: {error_count}")

    if nodata_count > 0 or nan_count > 0:
        print("\nPROBLEM IDENTIFIED:")
        print("  - NODATA: Metrics exist but rate([5m]) returns 0 (no traffic in last 5 min)")
        print("  - NaN: Division by zero or histogram_quantile with insufficient data")
        print("\nRECOMMENDATION:")
        print("  1. Add 'or vector(0)' to queries to show 0 instead of NODATA")
        print("  2. For NaN: Add 'or vector(0)' to prevent division by zero")
        print("  3. Use recording rules for complex queries (already exists for P95)")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
