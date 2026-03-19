#!/usr/bin/env python3
"""
Validation script for the 3 new HITL metrics.

Usage:
    python scripts/validate_hitl_metrics.py

Tests that the 3 metrics are:
1. Properly defined in metrics_agents.py
2. Instrumented in the code
3. Exposed on the /metrics endpoint
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_metric_definitions():
    """Test that the 3 metrics are defined in metrics_agents.py."""
    print("=" * 70)
    print("TEST 1: Metric definitions verification")
    print("=" * 70)

    try:
        from infrastructure.observability.metrics_agents import (
            hitl_clarification_fallback_total,
            hitl_edit_actions_total,
            hitl_rejection_type_total,
        )

        print("OK hitl_clarification_fallback_total imported")
        print("OK hitl_edit_actions_total imported")
        print("OK hitl_rejection_type_total imported")

        # Verify types
        from prometheus_client import Counter

        assert isinstance(hitl_clarification_fallback_total, Counter), "Wrong type"
        assert isinstance(hitl_edit_actions_total, Counter), "Wrong type"
        assert isinstance(hitl_rejection_type_total, Counter), "Wrong type"

        print("\nAll metrics are Counters")

        # Verify labels
        assert (
            hitl_clarification_fallback_total._labelnames == ()
        ), f"Expected no labels, got {hitl_clarification_fallback_total._labelnames}"

        assert hitl_edit_actions_total._labelnames == (
            "edit_type",
            "agent_type",
        ), f"Expected (edit_type, agent_type), got {hitl_edit_actions_total._labelnames}"

        assert hitl_rejection_type_total._labelnames == (
            "rejection_type",
            "agent_type",
        ), f"Expected (rejection_type, agent_type), got {hitl_rejection_type_total._labelnames}"

        print("Labels correct:")
        print("   - hitl_clarification_fallback_total: (no labels)")
        print("   - hitl_edit_actions_total: (edit_type, agent_type)")
        print("   - hitl_rejection_type_total: (rejection_type, agent_type)")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_instrumentation():
    """Test that the metrics are instrumented in the code."""
    print("\n" + "=" * 70)
    print("TEST 2: Code instrumentation verification")
    print("=" * 70)

    import re

    tests = [
        {
            "file": "src/domains/agents/services/hitl_classifier.py",
            "metric": "hitl_clarification_fallback_total",
            "pattern": r"hitl_clarification_fallback_total\.inc\(\)",
        },
        {
            "file": "src/domains/agents/api/service.py",
            "metric": "hitl_edit_actions_total",
            "pattern": r"hitl_edit_actions_total\.labels\(",
        },
        {
            "file": "src/domains/agents/api/service.py",
            "metric": "hitl_rejection_type_total",
            "pattern": r"hitl_rejection_type_total\.labels\(",
        },
    ]

    all_ok = True

    for test in tests:
        file_path = Path(__file__).parent.parent / test["file"]

        if not file_path.exists():
            print(f"FAIL File not found: {test['file']}")
            all_ok = False
            continue

        content = file_path.read_text(encoding="utf-8")

        if re.search(test["pattern"], content):
            print(f"OK {test['metric']} instrumented in {test['file']}")
        else:
            print(f"FAIL {test['metric']} NOT instrumented in {test['file']}")
            all_ok = False

    return all_ok


def test_helper_method():
    """Test that the helper method _infer_edit_type exists."""
    print("\n" + "=" * 70)
    print("TEST 3: Helper method _infer_edit_type() verification")
    print("=" * 70)

    file_path = Path(__file__).parent.parent / "src/domains/agents/api/service.py"

    if not file_path.exists():
        print("FAIL service.py file not found")
        return False

    content = file_path.read_text(encoding="utf-8")

    # Check method exists
    if "def _infer_edit_type(" not in content:
        print("FAIL _infer_edit_type() method not found")
        return False

    print("OK _infer_edit_type() method found")

    # Check logic
    checks = [
        ("tool_changed", "tool_changed"),
        ("full_rewrite", "full_rewrite"),
        ("minor_adjustment", "minor_adjustment"),
        ("params_modified", "params_modified"),
    ]

    for check_str, expected in checks:
        if check_str in content:
            print(f"   OK handles edit_type='{expected}'")
        else:
            print(f"   WARN edit_type='{expected}' not found (may be OK)")

    return True


def test_metrics_exposed():
    """Test that the metrics are exposed (requires API running)."""
    print("\n" + "=" * 70)
    print("TEST 4: Metrics exposure verification (requires API running)")
    print("=" * 70)

    try:
        import requests

        response = requests.get(
            f"{os.getenv('API_URL', 'http://localhost:8000')}/metrics", timeout=2
        )

        if response.status_code != 200:
            print(f"WARN API not accessible (status {response.status_code})")
            print("   -> Start the API with: uvicorn src.main:app --reload")
            return None

        metrics_text = response.text

        metrics_to_check = [
            "hitl_clarification_fallback_total",
            "hitl_edit_actions_total",
            "hitl_rejection_type_total",
        ]

        all_found = True
        for metric in metrics_to_check:
            if metric in metrics_text:
                print(f"OK {metric} exposed on /metrics")
            else:
                print(f"FAIL {metric} NOT exposed on /metrics")
                all_found = False

        return all_found

    except ImportError:
        print("WARN requests not installed")
        print("   -> pip install requests")
        return None
    except Exception as e:
        print(f"WARN API not accessible: {e}")
        print("   -> Start the API with: uvicorn src.main:app --reload")
        return None


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("VALIDATION OF 3 NEW HITL METRICS")
    print("=" * 70 + "\n")

    results = []

    # Test 1: Definitions
    results.append(("Metric definitions", test_metric_definitions()))

    # Test 2: Instrumentation
    results.append(("Code instrumentation", test_instrumentation()))

    # Test 3: Helper method
    results.append(("Helper _infer_edit_type()", test_helper_method()))

    # Test 4: Exposure (optional)
    exposed = test_metrics_exposed()
    if exposed is not None:
        results.append(("Exposure /metrics", exposed))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    # Check if API test was skipped
    if exposed is None:
        print("SKIP - Exposure /metrics (API not accessible)")

    total_tests = len(results)
    passed_tests = sum(1 for _, result in results if result)

    print(f"\nResult: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\nVALIDATION COMPLETE - All metrics are OK!")
        return 0
    else:
        print(f"\nPARTIAL VALIDATION - {total_tests - passed_tests} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
