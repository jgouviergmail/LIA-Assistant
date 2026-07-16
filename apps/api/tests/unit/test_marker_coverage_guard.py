"""Fast unit coverage for the marker-coverage gate logic (audit F006).

The end-to-end gate (``scripts/audit/check_test_marker_coverage.py``) collects the
whole suite (~11k tests) and runs in CI; these tests pin its pure decision logic —
which (root, markers) combinations a CI job selects — without any collection, and
assert the allowlist is well-formed and non-empty-by-accident.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from tests._repo_paths import repo_root_or_skip

_ROOT = repo_root_or_skip()  # repo root
_SCRIPT = _ROOT / "scripts" / "audit" / "check_test_marker_coverage.py"
_ALLOWLIST = Path(__file__).resolve().parents[1] / "marker_coverage_allowlist.json"


def _load_gate():
    spec = importlib.util.spec_from_file_location("_marker_gate", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


class TestTopDir:
    def test_extracts_root_from_nodeid(self):
        assert gate.top_dir("tests/unit/foo/test_x.py::test_a") == "unit"
        assert gate.top_dir("tests/agents/test_y.py::T::t") == "agents"
        assert gate.top_dir("tests/integration/test_z.py::t") == "integration"

    def test_handles_backslashes(self):
        assert gate.top_dir("tests\\unit\\test_x.py::t") == "unit"


class TestSelection:
    def test_plain_unit_test_runs_in_unit_job(self):
        assert gate.selected_by_any_job("tests/unit/test_x.py::t", set()) is True

    def test_integration_marked_unit_test_runs_in_cross_root_collection(self):
        # F006 fix: the unit job excludes 'integration', but the integration job
        # now runs a SECOND collection over tests/unit + tests/agents selecting
        # integration-marked tests — so they no longer fall through the cracks.
        assert gate.selected_by_any_job("tests/unit/test_x.py::t", {"integration"}) is True
        assert gate.selected_by_any_job("tests/agents/test_x.py::t", {"integration"}) is True

    def test_integration_plus_periodic_marker_still_runs_nowhere(self):
        # The cross-root integration collection still excludes e2e/benchmark/
        # multiprocess, so an integration+benchmark test stays out-of-PR.
        assert (
            gate.selected_by_any_job("tests/unit/test_x.py::t", {"integration", "benchmark"})
            is False
        )

    def test_slow_marked_unit_test_runs_nowhere(self):
        assert gate.selected_by_any_job("tests/unit/test_x.py::t", {"slow"}) is False

    def test_e2e_runs_in_no_job(self):
        for root in ("unit", "agents", "integration"):
            assert gate.selected_by_any_job(f"tests/{root}/test_x.py::t", {"e2e"}) is False

    def test_integration_marked_integration_test_runs(self):
        assert gate.selected_by_any_job("tests/integration/test_x.py::t", {"integration"}) is True

    def test_slow_marked_integration_test_runs(self):
        # The integration job does not exclude 'slow'.
        assert gate.selected_by_any_job("tests/integration/test_x.py::t", {"slow"}) is True

    def test_unknown_root_is_not_selected(self):
        assert gate.selected_by_any_job("tests/e2e/test_x.py::t", set()) is False


class TestJobsModel:
    def test_jobs_mirror_the_three_ci_roots(self):
        assert set(gate.JOBS) == {"unit", "agents", "integration"}

    def test_e2e_benchmark_multiprocess_excluded_everywhere(self):
        for excluded in gate.JOBS.values():
            assert {"e2e", "benchmark", "multiprocess"} <= excluded


class TestAllowlist:
    def test_allowlist_is_well_formed(self):
        data = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
        assert "_comment" in data and data["_comment"].strip()
        assert isinstance(data["allow"], list)

    def test_allowlist_entries_are_unique_nodeids(self):
        allow = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))["allow"]
        assert len(allow) == len(set(allow)), "duplicate allowlist entries"
        assert all("::" in n for n in allow), "allowlist entries must be nodeids"

    def test_every_allowlisted_test_is_genuinely_orphaned_by_the_model(self):
        # Each allowlisted nodeid must carry >=1 blocking marker inferred from its
        # path/name context is not possible without collection, but at minimum it
        # must live under a known root (otherwise the path guard, not this one,
        # owns it).
        allow = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))["allow"]
        assert all(gate.top_dir(n) in gate.JOBS for n in allow)
