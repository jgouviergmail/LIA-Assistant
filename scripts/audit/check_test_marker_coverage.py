#!/usr/bin/env python
"""Marker-coverage gate (audit F006): every collected test must run in >=1 CI job.

The path-level taxonomy guard (``apps/api/tests/unit/test_tests_taxonomy_guard.py``)
ensures test FILES live under a CI-executed root, but a well-placed file can still
be entirely deselected by a job's marker expression (``slow`` / ``e2e`` /
``benchmark`` / ``multiprocess`` / ``integration``) and therefore run in NO job —
the false assurance the audit flagged. This gate collects every nodeid with its
markers, models each CI job as ``(root, deselecting-markers)``, and fails if any
collected test is selected by no job and is not in the justified, SHRINK-ONLY
allowlist (``apps/api/tests/marker_coverage_allowlist.json``).

Run from ``apps/api``::

    python ../../scripts/audit/check_test_marker_coverage.py

Exit code 0 = every test runs in a job or is allowlisted; 1 = a new orphan
appeared (or an allowlist entry is stale and must be pruned).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# CI jobs — MUST mirror the pytest invocations in .github/workflows/ci.yml.
# Maps a test root to the marker set that DESELECTS a test in that job.
JOBS: dict[str, set[str]] = {
    "unit": {"integration", "slow", "e2e", "benchmark", "multiprocess"},
    "agents": {"slow", "e2e", "benchmark", "multiprocess"},
    "integration": {"e2e", "benchmark", "multiprocess"},
}

# F006: the integration CI job runs a SECOND collection over tests/unit and
# tests/agents selecting integration-marked tests, so functional DB/Redis tests
# co-located with unit ones still run in a per-PR job. Mirror that collection:
# an integration-marked test under these roots is selected as long as it is not
# also e2e/benchmark/multiprocess.
_CROSS_ROOT_INTEGRATION_ROOTS = {"unit", "agents"}
_CROSS_ROOT_INTEGRATION_EXCLUDES = {"e2e", "benchmark", "multiprocess"}

_ALLOWLIST_PATH = Path("tests/marker_coverage_allowlist.json")


def top_dir(nodeid: str) -> str:
    """Return the test root (``unit`` / ``agents`` / ``integration`` / ...)."""
    parts = nodeid.replace("\\", "/").split("/")
    if parts and parts[0] == "tests" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts else ""


def selected_by_any_job(nodeid: str, markers: set[str]) -> bool:
    """True if at least one CI job collects AND selects this nodeid."""
    root = top_dir(nodeid)
    # Per-root primary collection: a test runs if it is under the job's root and
    # not deselected by that job's marker expression.
    excluded = JOBS.get(root)
    if excluded is not None and not (markers & excluded):
        return True
    # Cross-root integration collection (see _CROSS_ROOT_INTEGRATION_* above).
    if (
        root in _CROSS_ROOT_INTEGRATION_ROOTS
        and "integration" in markers
        and not (markers & _CROSS_ROOT_INTEGRATION_EXCLUDES)
    ):
        return True
    return False


class _Collector:
    def __init__(self) -> None:
        self.records: list[tuple[str, set[str]]] = []

    def pytest_collection_modifyitems(self, items: list) -> None:  # type: ignore[type-arg]
        for item in items:
            self.records.append((item.nodeid, {m.name for m in item.iter_markers()}))


def main() -> int:
    collector = _Collector()
    rc = pytest.main(
        ["--collect-only", "-q", "-p", "no:cacheprovider", "--no-cov", "tests/"],
        plugins=[collector],
    )
    if int(rc) not in (0, 5):  # 0 = collected, 5 = no tests collected
        print(f"ERROR: pytest collection failed (rc={rc}).", file=sys.stderr)
        return 1

    orphaned = {n for (n, markers) in collector.records if not selected_by_any_job(n, markers)}
    allowlist = set(json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))["allow"])

    new_orphans = sorted(orphaned - allowlist)
    stale = sorted(allowlist - orphaned)
    ok = True

    if new_orphans:
        ok = False
        print(
            "FAIL (audit F006): the following test(s) are collected but run in NO CI job "
            "and are not allowlisted:",
            file=sys.stderr,
        )
        for n in new_orphans:
            print(f"    {n}", file=sys.stderr)
        print(
            "  Give the test a marker a job selects (or move it to the right root) so it "
            f"runs, or add it to {_ALLOWLIST_PATH} with a justification.",
            file=sys.stderr,
        )

    if stale:
        ok = False
        print(
            "FAIL: allowlist entries are no longer orphaned — prune them (shrink-only ratchet):",
            file=sys.stderr,
        )
        for n in stale:
            print(f"    {n}", file=sys.stderr)

    if ok:
        print(
            f"OK: {len(collector.records)} tests collected; {len(orphaned)} intentionally "
            "out-of-PR (allowlisted); no new orphan runs in zero jobs."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
