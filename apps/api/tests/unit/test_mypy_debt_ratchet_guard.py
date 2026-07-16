"""MyPy exemption surface is frozen and shrink-only (audit F020).

The backend suppresses ~860 real type errors through ``disable_error_code``
overrides in ``pyproject.toml``. This guard freezes that exemption surface as
a set of ``(module, error_code)`` pairs and forbids growth: adding a module to
a disable block or a new code to an existing block fails CI. Removing
exemptions is always allowed (and lowers the baseline via
``measure_mypy_debt.py --update``).

The metric is parsed purely from ``pyproject.toml`` — no MyPy run — so it is
byte-identical on the Windows host pre-commit hook and the Linux CI runner
(closing the recurring host/Docker MyPy divergence).
"""

from __future__ import annotations

import importlib.util
import json

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
TOOL_PATH = REPO_ROOT / "scripts" / "audit" / "measure_mypy_debt.py"
BASELINE_PATH = REPO_ROOT / "apps" / "api" / ".mypy-debt-baseline.json"


def _load_tool():
    if not TOOL_PATH.exists():
        pytest.skip(
            "guard needs the full repository checkout (scripts/audit/measure_mypy_debt.py)."
        )
    spec = importlib.util.spec_from_file_location("measure_mypy_debt", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _baseline_pairs() -> set[tuple[str, str]]:
    raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["pairs"]
    return {(m, c) for m, c in raw}


def test_no_new_mypy_exemptions() -> None:
    """Every current exemption pair must already be in the frozen baseline."""
    tool = _load_tool()
    current = tool.exemption_pairs()
    baseline = _baseline_pairs()
    added = current - baseline
    assert not added, (
        "New MyPy exemption(s) added (F020) — fix the type errors instead of "
        f"widening disable_error_code: {sorted(added)}"
    )


def test_baseline_is_not_stale() -> None:
    """The baseline must not claim exemptions that no longer exist (keep it honest)."""
    tool = _load_tool()
    current = tool.exemption_pairs()
    baseline = _baseline_pairs()
    removed = baseline - current
    assert not removed, (
        "Exemptions were removed but the baseline was not lowered — run "
        f"`python scripts/audit/measure_mypy_debt.py --update`: {sorted(removed)}"
    )


def test_ratchet_detects_a_new_exemption(monkeypatch: pytest.MonkeyPatch) -> None:
    """A synthetic new (module, code) pair must make --check fail (exit 1)."""
    tool = _load_tool()
    baseline = _baseline_pairs()
    poisoned = baseline | {("src.domains.brand_new.evil", "no-any-return")}
    monkeypatch.setattr(tool, "exemption_pairs", lambda: poisoned)
    assert tool._check() == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
