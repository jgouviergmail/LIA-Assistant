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


def _run(script: str, cwd: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(AUDIT_DIR / script)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    assert (
        "not found" not in result.stderr
    ), f"{script} from {cwd} could not locate its default source dir:\n{result.stderr}"
    return result.stdout


@pytest.mark.parametrize("script, signature", list(SCRIPTS.items()))
def test_default_run_is_cwd_independent(script: str, signature: str, tmp_path: Path):
    """Default (no-arg) run yields the same metrics from three different CWDs."""
    api_dir = REPO_ROOT / "apps" / "api"
    outputs = {
        "repo_root": _run(script, REPO_ROOT),
        "apps_api": _run(script, api_dir),
        "temp_dir": _run(script, tmp_path),
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
