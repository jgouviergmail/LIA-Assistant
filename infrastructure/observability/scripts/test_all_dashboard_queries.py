#!/usr/bin/env python3
"""
Test ALL Grafana dashboard queries against Prometheus
Identifies panels with NODATA, NaN, errors, or other issues
"""
import json
import requests
import re
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

PROMETHEUS_URL = "http://localhost:9090"
DASHBOARDS_PATH = Path("D:/Developpement/LIA/infrastructure/observability/grafana/dashboards")

class DashboardTester:
    def __init__(self):
        self.results = defaultdict(lambda: {
            "total_panels": 0,
            "total_queries": 0,
            "queries_ok": 0,
            "queries_nodata": 0,
            "queries_error": 0,
            "problems": []
        })

    def extract_queries(self, dashboard_json: dict) -> List[Tuple[str, str, str]]:
        """Extract all PromQL queries from dashboard"""
        queries = []
        panels = dashboard_json.get("panels", [])

        for panel in panels:
            panel_title = panel.get("title", "Untitled")
            targets = panel.get("targets", [])

            for target in targets:
                expr = target.get("expr", "")
                if expr:
                    queries.append((panel_title, expr, target.get("refId", "A")))

        return queries

    def test_query(self, query: str) -> Tuple[str, int, str]:
        """
        Test a PromQL query against Prometheus
        Returns: (status, result_count, error_message)
        """
        try:
            # Clean query - remove Grafana variables
            clean_query = self.clean_query(query)

            response = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": clean_query},
                timeout=10
            )

            if response.status_code != 200:
                return ("ERROR", 0, f"HTTP {response.status_code}")

            data = response.json()

            if data.get("status") != "success":
                error_msg = data.get("error", "Unknown error")
                return ("ERROR", 0, error_msg)

            results = data.get("data", {}).get("result", [])

            if len(results) == 0:
                return ("NODATA", 0, "Query returns no results")

            # Check for NaN values
            has_nan = False
            for result in results:
                value = result.get("value", [None, None])[1]
                if value in ["NaN", "Inf", "-Inf", None]:
                    has_nan = True
                    break

            if has_nan:
                return ("NAN", len(results), "Result contains NaN/Inf values")

            return ("OK", len(results), "")

        except requests.exceptions.Timeout:
            return ("ERROR", 0, "Query timeout")
        except requests.exceptions.ConnectionError:
            return ("ERROR", 0, "Cannot connect to Prometheus")
        except Exception as e:
            return ("ERROR", 0, str(e))

    def clean_query(self, query: str) -> str:
        """Remove Grafana variables from query"""
        # Replace common Grafana variables with reasonable defaults
        replacements = {
            r'\$__interval': '5m',
            r'\$__rate_interval': '5m',
            r'\$__range': '1h',
            r'\$interval': '5m',
            r'\$auth_endpoint': '/api/v1/auth/.*',
            r'\$gmail_operation': '.*',
            r'\$event_type': '.*',
            r'\$node_name': '.*',
            r'\$agent_type': '.*',
        }

        for pattern, replacement in replacements.items():
            query = re.sub(pattern, replacement, query)

        return query

    def test_dashboard(self, dashboard_file: Path) -> None:
        """Test all queries in a dashboard"""
        dashboard_name = dashboard_file.stem

        try:
            with open(dashboard_file, 'r', encoding='utf-8') as f:
                dashboard = json.load(f)
        except Exception as e:
            self.results[dashboard_name]["problems"].append({
                "type": "FILE_ERROR",
                "message": f"Cannot read dashboard: {e}"
            })
            return

        queries = self.extract_queries(dashboard)
        self.results[dashboard_name]["total_panels"] = len(dashboard.get("panels", []))
        self.results[dashboard_name]["total_queries"] = len(queries)

        for panel_title, query, ref_id in queries:
            status, count, error_msg = self.test_query(query)

            if status == "OK":
                self.results[dashboard_name]["queries_ok"] += 1
            elif status == "NODATA":
                self.results[dashboard_name]["queries_nodata"] += 1
                self.results[dashboard_name]["problems"].append({
                    "type": "NODATA",
                    "panel": panel_title,
                    "query": query[:100] + "..." if len(query) > 100 else query,
                    "message": error_msg
                })
            elif status == "NAN":
                self.results[dashboard_name]["problems"].append({
                    "type": "NAN",
                    "panel": panel_title,
                    "query": query[:100] + "..." if len(query) > 100 else query,
                    "message": error_msg
                })
            elif status == "ERROR":
                self.results[dashboard_name]["queries_error"] += 1
                self.results[dashboard_name]["problems"].append({
                    "type": "ERROR",
                    "panel": panel_title,
                    "query": query[:100] + "..." if len(query) > 100 else query,
                    "message": error_msg
                })

    def test_all_dashboards(self) -> None:
        """Test all dashboards in the directory"""
        dashboard_files = list(DASHBOARDS_PATH.glob("*.json"))
        dashboard_files = [f for f in dashboard_files if not f.name.startswith("deprecated")]

        print(f"Testing {len(dashboard_files)} dashboards...\n")

        for dashboard_file in sorted(dashboard_files):
            print(f"Testing {dashboard_file.stem}...")
            self.test_dashboard(dashboard_file)

        print("\n" + "="*80)
        self.print_summary()

    def print_summary(self) -> None:
        """Print comprehensive test summary"""
        print("\n DASHBOARD TEST SUMMARY\n")
        print("="*80)

        total_dashboards = len(self.results)
        total_queries = sum(r["total_queries"] for r in self.results.values())
        total_ok = sum(r["queries_ok"] for r in self.results.values())
        total_nodata = sum(r["queries_nodata"] for r in self.results.values())
        total_error = sum(r["queries_error"] for r in self.results.values())

        print(f"\n**Global Statistics**:")
        print(f"  Total Dashboards: {total_dashboards}")
        print(f"  Total Queries: {total_queries}")
        print(f"   Queries OK: {total_ok} ({100*total_ok//total_queries if total_queries else 0}%)")
        print(f"    Queries NODATA: {total_nodata} ({100*total_nodata//total_queries if total_queries else 0}%)")
        print(f"   Queries ERROR: {total_error} ({100*total_error//total_queries if total_queries else 0}%)")

        print(f"\n**Dashboard-by-Dashboard:**\n")

        for dashboard_name in sorted(self.results.keys()):
            result = self.results[dashboard_name]

            status_icon = ""
            if result["queries_error"] > 0:
                status_icon = ""
            elif result["queries_nodata"] > 0:
                status_icon = ""

            print(f"{status_icon} {dashboard_name}:")
            print(f"     Panels: {result['total_panels']}, Queries: {result['total_queries']}")
            print(f"     OK: {result['queries_ok']}, NODATA: {result['queries_nodata']}, ERROR: {result['queries_error']}")

            if result["problems"]:
                print(f"     Problems:")
                for problem in result["problems"][:3]:  # Show max 3 problems per dashboard
                    print(f"       - [{problem['type']}] {problem['panel']}: {problem['message']}")
                if len(result["problems"]) > 3:
                    print(f"       ... and {len(result['problems']) - 3} more")
            print()

        # Critical issues summary
        print("\n CRITICAL ISSUES:\n")
        critical_count = 0
        for dashboard_name, result in self.results.items():
            for problem in result["problems"]:
                if problem["type"] == "ERROR":
                    print(f"   {dashboard_name} / {problem['panel']}")
                    print(f"     Error: {problem['message']}")
                    print(f"     Query: {problem['query']}")
                    print()
                    critical_count += 1

        if critical_count == 0:
            print("   No critical errors found!")

        print("\n" + "="*80)

def main():
    tester = DashboardTester()

    # Check Prometheus connectivity
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": "up"}, timeout=5)
        if response.status_code != 200:
            print(f" Cannot connect to Prometheus at {PROMETHEUS_URL}")
            return
        print(f"Connected to Prometheus at {PROMETHEUS_URL}\\n")
    except Exception as e:
        print(f"Cannot connect to Prometheus: {e}")
        return

    tester.test_all_dashboards()

if __name__ == "__main__":
    main()
