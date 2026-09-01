"""Audit measurement scripts must be CWD-independent (audit F023).

``measure_sloc`` / ``measure_cc`` / ``measure_coupling`` defaulted their target
to a *relative* ``src`` / ``src/domains``, so running them from the repo root —
as ``docs/audit/AUDIT_PROTOCOL.md`` prescribes — failed with "source directory
not found" (exit 1, reproduced in the 2026-07 audit). They now resolve their
default from ``__file__``. This test proves the default invocation succeeds and
yields identical output from any working directory (repo root, apps/api, and an
unrelated temp dir).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
AUDIT_DIR = REPO_ROOT / "scripts" / "audit"

# Script → a signature substring its healthy stdout must contain.
SCRIPTS: dict[str, str] = {
    "measure_sloc.py": "files=",
    "measure_cc.py": "functions=",
    "measure_coupling.py": "domains=",
}


def _run(script: str, signature: str, cwd: Path) -> str:
    # These scripts are GATES: 0 = clean, 1 = threshold exceeded (measure_cc
    # reports 346 functions over CC 15 and exits 1 with complete output). Any
    # OTHER code means the INTERPRETER died (measured on Windows under the
    # pre-commit hook's 8 xdist workers: exit 3221225477 = 0xC0000005 access
    # violation at startup, empty stdout/stderr — a runner resource problem,
    # not a script behavior). One bounded retry absorbs that crash class
    # WITHOUT masking an F023 regression: a wrong-output or "not found" run
    # still fails, only a dead interpreter earns a second attempt.
    #
    # The return code alone is not enough to recognise that death. Measured
    # 2026-09-02 under those same eight workers: a run came back with a GATE
    # code and an EMPTY stdout, so the loop broke on the first attempt and the
    # caller's assertion failed on a blank string — a runner problem reported
    # as an audit regression. A healthy run ALWAYS prints its signature, so the
    # retry waits for the evidence the script actually ran, not merely for a
    # plausible exit code. Two signature-less attempts still fail, loudly.
    result = None
    for _attempt in range(2):
        result = subprocess.run(
            [sys.executable, str(AUDIT_DIR / script)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        if result.returncode in (0, 1) and signature in result.stdout:
            break
    assert result is not None
    assert (
        "not found" not in result.stderr
    ), f"{script} from {cwd} could not locate its default source dir:\n{result.stderr}"
    assert result.returncode in (0, 1), (
        f"{script} from {cwd} died TWICE with code {result.returncode} — runner "
        f"resource exhaustion goes beyond the flake this retry absorbs:\n"
        f"{result.stderr[-2000:]}"
    )
    return result.stdout


@pytest.mark.parametrize("script, signature", list(SCRIPTS.items()))
def test_default_run_is_cwd_independent(script: str, signature: str, tmp_path: Path) -> None:
    """Default (no-arg) run yields the same metrics from three different CWDs."""
    api_dir = REPO_ROOT / "apps" / "api"
    outputs = {
        "repo_root": _run(script, signature, REPO_ROOT),
        "apps_api": _run(script, signature, api_dir),
        "temp_dir": _run(script, signature, tmp_path),
    }

    for where, out in outputs.items():
        assert signature in out, f"{script} produced no metrics from {where}:\n{out}"

    distinct = set(outputs.values())
    assert len(distinct) == 1, (
        f"{script} output depends on CWD (F023 regression); "
        f"got {len(distinct)} distinct outputs across "
        f"{list(outputs)}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
