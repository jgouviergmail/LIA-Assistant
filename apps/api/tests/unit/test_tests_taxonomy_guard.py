"""Guard: no test file may live outside the CI-executed roots (shrink-only ratchet).

Finding LIA-2026-006 (independent audit, 2026-07-12): 27 test files — 465
collected cases — run in **no** CI job, because ``.github/workflows/ci.yml``
only targets ``tests/unit``, ``tests/agents`` and ``tests/integration``.
Configuration, LLM cache, providers, circuit breaker and streaming can
therefore regress without blocking delivery.

This guard freezes the current out-of-root set as a **shrink-only baseline**:

* any NEW ``test_*.py`` created outside the executed roots fails immediately
  (including in new domains such as ``telephony``);
* the baseline may only shrink — when a file is reclassified into an executed
  root, the guard tells you to remove it from the baseline.

It deliberately does NOT force reclassifying the existing 27 today (that is the
separate LIA-2026-006 remediation). Its job is to stop the leak from growing.

CWD-independent by construction (paths resolved from ``__file__``), unlike the
audit measurement scripts flagged by LIA-2026-023.
"""

from __future__ import annotations

import json
from pathlib import Path

# Keep in sync with the pytest invocations in .github/workflows/ci.yml.
CI_EXECUTED_ROOTS: tuple[str, ...] = ("unit", "agents", "integration")

_TESTS_DIR = Path(__file__).resolve().parents[1]  # apps/api/tests
_BASELINE_PATH = Path(__file__).resolve().parent / "tests_taxonomy_baseline.json"


def _out_of_root_test_files() -> set[str]:
    """Return every ``test_*.py`` under tests/ that no CI job collects."""
    out: set[str] = set()
    for path in _TESTS_DIR.rglob("test_*.py"):
        rel = path.relative_to(_TESTS_DIR).as_posix()
        top = rel.split("/", 1)[0]
        if top not in CI_EXECUTED_ROOTS:
            out.add("tests/" + rel)
    return out


def test_no_new_test_outside_ci_executed_roots() -> None:
    """No test file may appear outside the executed roots beyond the baseline."""
    baseline = set(json.loads(_BASELINE_PATH.read_text(encoding="utf-8")))
    current = _out_of_root_test_files()

    new_debt = sorted(current - baseline)
    assert not new_debt, (
        "New test file(s) live outside the CI-executed roots "
        f"{CI_EXECUTED_ROOTS} and would run in NO CI job (see LIA-2026-006). "
        "Move each under tests/unit, tests/agents or tests/integration with the "
        "correct pytest markers based on its real dependencies:\n  " + "\n  ".join(new_debt)
    )


def test_taxonomy_baseline_only_shrinks() -> None:
    """Baseline entries that no longer exist must be pruned (ratchet down)."""
    baseline = set(json.loads(_BASELINE_PATH.read_text(encoding="utf-8")))
    current = _out_of_root_test_files()

    stale = sorted(baseline - current)
    assert not stale, (
        "The out-of-CI debt shrank (good). Remove these now-absent entries from "
        "tests/unit/tests_taxonomy_baseline.json so the ratchet stays tight:\n  "
        + "\n  ".join(stale)
    )
