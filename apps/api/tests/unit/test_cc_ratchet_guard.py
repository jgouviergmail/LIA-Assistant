"""Backend cyclomatic complexity is frozen and shrink-only (audit F011/F015).

The audit found backend coordinators with CC up to 89 (`_stream_with_new_services`,
`planner_node_v3`, `_handle_execution_plan`) and 351 functions at/over CC 15,
with no gate preventing new complexity. This guard freezes two monotone caps —
the count of functions >= threshold and the single worst function — so neither
can grow. Decomposing a hotspot lowers the baseline via
`measure_cc.py --update-ratchet`. Metric is AST-derived (deterministic).

Staleness policy (deliberately tolerant, unlike the discrete-set ratchets):
`over`/`max` are AGGREGATE counts over the whole tree, so an unrelated edit can
incidentally drop a function below the threshold. Forcing a baseline update on
every such drift (strict ``cur == base``) would fail the suite for a *good*
change that introduced no regression — pure friction, zero safety. So the guard
and the CLI agree on a single failure condition: **regression only**
(``cur > base``). Improvements are accepted; the baseline is a valid ceiling
that is tightened opportunistically during real decomposition work. This differs
on purpose from the coupling-cycles / mypy-debt / permanent-skip ratchets, whose
metric is a *discrete set* removed by a deliberate act — there, strict staleness
(a removed item must be reflected) is meaningful and cheap.
"""

from __future__ import annotations

import importlib.util
import json

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
TOOL_PATH = REPO_ROOT / "scripts" / "audit" / "measure_cc.py"
BASELINE_PATH = REPO_ROOT / "apps" / "api" / ".cc-baseline.json"
SRC_DIR = REPO_ROOT / "apps" / "api" / "src"


def _load_tool():
    if not TOOL_PATH.exists():
        pytest.skip("guard needs the full repository checkout (scripts/audit/measure_cc.py).")
    spec = importlib.util.spec_from_file_location("measure_cc", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def test_cc_does_not_regress() -> None:
    """Neither the count >= threshold nor the max CC may exceed the baseline."""
    tool = _load_tool()
    base = _baseline()
    cur = tool.cc_stats(threshold=base["threshold"])
    assert cur["over"] <= base["over"], (
        f"functions >= CC {base['threshold']} grew to {cur['over']} > {base['over']} "
        "(F011/F015) — decompose, don't raise the cap."
    )
    assert (
        cur["max"] <= base["max"]
    ), f"max CC grew to {cur['max']} > {base['max']} (F011/F015) — decompose the hotspot."


def test_check_ratchet_tolerates_improvement(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI and guard agree: an improvement (cur < base) must NOT fail (exit 0).

    This locks the CLI↔test coherence the audit flagged: `task lint:cc`
    (`--check-ratchet`) accepts an improvement, so the guard suite must not
    contradict it by failing on the very same state. Only a regression fails.
    """
    tool = _load_tool()
    base = _baseline()
    monkeypatch.setattr(
        tool,
        "cc_stats",
        lambda **_kw: {
            "over": max(0, base["over"] - 3),
            "max": max(1, base["max"] - 1),
            "threshold": base["threshold"],
        },
    )
    assert tool._check_ratchet() == 0


def test_ratchet_detects_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    """A synthetic complexity increase must make --check-ratchet fail (exit 1)."""
    tool = _load_tool()
    base = _baseline()
    monkeypatch.setattr(
        tool,
        "cc_stats",
        lambda **_kw: {
            "over": base["over"] + 5,
            "max": base["max"] + 1,
            "threshold": base["threshold"],
        },
    )
    assert tool._check_ratchet() == 1


# --- F046: one shared verdict, exercised across every case -------------------
# `ratchet_verdict` is the single source of truth the CLI (`_check_ratchet`) and
# these tests both consume, so the two entrypoints can never disagree.

_BASE = {"over": 350, "max": 89, "threshold": 15}


def test_verdict_regression_over_blocks() -> None:
    tool = _load_tool()
    v = tool.ratchet_verdict({**_BASE, "over": 351}, _BASE)
    assert v["status"] == "regressed" and v["blocking"] is True


def test_verdict_regression_max_blocks() -> None:
    tool = _load_tool()
    v = tool.ratchet_verdict({**_BASE, "max": 90}, _BASE)
    assert v["status"] == "regressed" and v["blocking"] is True


def test_verdict_equality_is_within_and_nonblocking() -> None:
    tool = _load_tool()
    v = tool.ratchet_verdict(dict(_BASE), _BASE)
    assert v["status"] == "within" and v["blocking"] is False and not v["advisories"]


def test_verdict_total_improvement_is_advisory() -> None:
    tool = _load_tool()
    v = tool.ratchet_verdict({**_BASE, "over": 349}, _BASE)
    assert v["status"] == "improved" and v["blocking"] is False and len(v["advisories"]) == 1


def test_verdict_max_improvement_is_advisory() -> None:
    tool = _load_tool()
    v = tool.ratchet_verdict({**_BASE, "max": 80}, _BASE)
    assert v["status"] == "improved" and v["blocking"] is False and len(v["advisories"]) == 1


def test_verdict_mixed_improvement_lists_both() -> None:
    tool = _load_tool()
    v = tool.ratchet_verdict({**_BASE, "over": 349, "max": 80}, _BASE)
    assert v["status"] == "improved" and v["blocking"] is False and len(v["advisories"]) == 2


def test_verdict_invalid_baseline_blocks() -> None:
    tool = _load_tool()
    v = tool.ratchet_verdict({"over": 1, "max": 1, "threshold": 15}, {"over": 1, "max": 1})
    assert v["status"] == "invalid" and v["blocking"] is True


def test_real_cli_check_ratchet_is_green() -> None:
    """Integration: the ACTUAL CLI subprocess agrees with the guard (exit 0).

    Proves the shipped `task lint:cc` and this suite share one verdict — the
    contradiction F046 flagged (CLI green while the guard was red) cannot recur.
    """
    import subprocess
    import sys

    if not TOOL_PATH.exists():
        pytest.skip("guard needs the full repository checkout.")
    result = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--check-ratchet"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"real CLI --check-ratchet exited {result.returncode}, contradicting the "
        f"green guard suite (F046).\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
