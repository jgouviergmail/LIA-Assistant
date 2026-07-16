"""Runtime domain import-cycles are frozen and shrink-only (audit F009).

ADR-126 decoupled auth/users but 31 runtime bidirectional import cycles remain
across the domains (many through the ``users`` hub). Nothing stopped a *new*
cycle from appearing. This guard freezes the set as a machine-readable baseline
and fails on any new cycle; breaking a cycle lowers the baseline via
``measure_coupling.py --update-cycles``. The metric is AST-derived from
``src/domains`` — deterministic, no runtime import.
"""

from __future__ import annotations

import importlib.util
import json

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
TOOL_PATH = REPO_ROOT / "scripts" / "audit" / "measure_coupling.py"
BASELINE_PATH = REPO_ROOT / "apps" / "api" / ".coupling-cycles-baseline.json"
DOMAINS_DIR = REPO_ROOT / "apps" / "api" / "src" / "domains"


def _load_tool():
    if not TOOL_PATH.exists():
        pytest.skip("guard needs the full repository checkout (scripts/audit/measure_coupling.py).")
    spec = importlib.util.spec_from_file_location("measure_coupling", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _baseline() -> set[str]:
    return set(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["cycles"])


def test_no_new_runtime_cycles() -> None:
    """Every current runtime cycle must already be in the frozen baseline."""
    tool = _load_tool()
    current = set(tool.runtime_cycle_keys(DOMAINS_DIR))
    added = current - _baseline()
    assert not added, (
        "New runtime import cycle(s) introduced (F009) — break the cycle with "
        f"ports/Protocol/events/injection instead of widening it: {sorted(added)}"
    )


def test_baseline_is_not_stale() -> None:
    """A broken cycle must be reflected by lowering the baseline (shrink-only)."""
    tool = _load_tool()
    current = set(tool.runtime_cycle_keys(DOMAINS_DIR))
    removed = _baseline() - current
    assert not removed, (
        "Cycle(s) were broken but the baseline was not lowered — run "
        f"`python scripts/audit/measure_coupling.py --update-cycles`: {sorted(removed)}"
    )


def test_ratchet_detects_a_new_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """A synthetic new cycle must make --check-cycles fail (exit 1)."""
    tool = _load_tool()
    poisoned = sorted(_baseline() | {"zzz_new<->zzz_evil"})
    monkeypatch.setattr(tool, "runtime_cycle_keys", lambda _root: poisoned)
    assert tool._check_cycles(DOMAINS_DIR) == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
