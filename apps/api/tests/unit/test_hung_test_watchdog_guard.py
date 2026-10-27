"""Guard: a test that hangs is interrupted, with every thread's stack (AC-033a).

Why
---
No per-test bound existed: neither pytest-timeout nor ``faulthandler_timeout``.
Two pytest processes started on 2026-10-20 were still alive two days later, and
the V14 audit's mass re-runs stalled without a single stack to read. The CI jobs
had no ``timeout-minutes`` either, so a hang ran to the platform's six-hour limit.

``apps/api/pyproject.toml`` now sets ``faulthandler_timeout`` and
``faulthandler_exit_on_timeout``: past the bound, faulthandler writes every
thread's stack and ends the process — under xdist, the worker, so the test is
reported failed and the run goes on. These tests run a deliberately hanging test
under the REAL configuration, sequentially and under xdist, with the bound
lowered on the command line alone.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
PYPROJECT = REPO_ROOT / "apps" / "api" / "pyproject.toml"

pytestmark = pytest.mark.unit

#: Below this, the bound would cut legitimate slow tests rather than hangs.
GENEROUS_FLOOR_SECONDS = 300.0
#: The hanging test sleeps this long; an interrupted run ends far earlier.
HANG_SECONDS = 60
#: The bound the subprocess runs under (lowered on its command line only).
TEST_BOUND_SECONDS = 2

HANGING_TEST = f"import time\n\n\ndef test_hangs():\n    time.sleep({HANG_SECONDS})\n"


def _ini_options() -> dict[str, object]:
    options = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"]
    ini: dict[str, object] = options["ini_options"]
    return ini


def _run_hanging_test(
    tmp_path: Path, *extra: str
) -> tuple[subprocess.CompletedProcess[str], float]:
    (tmp_path / "test_hang.py").write_text(HANGING_TEST, encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "pytest_cov.plugin",
        "-p",
        "pytest_asyncio.plugin",
        "-p",
        "xdist.plugin",
        "test_hang.py",
        "-c",
        str(PYPROJECT),
        "--rootdir",
        str(tmp_path),
        "-o",
        f"faulthandler_timeout={TEST_BOUND_SECONDS}",
        "--no-cov",
        "-p",
        "no:cacheprovider",
        *extra,
    ]
    # This synthetic child needs only its configured option parsers and xdist.
    # Loading every installed plugin again in the controller and worker makes
    # startup compete with the parent suite before the watchdog can even run.
    child_env = os.environ.copy()
    child_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    started = time.monotonic()
    process = subprocess.run(
        command,
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=HANG_SECONDS - 5,
    )
    return process, time.monotonic() - started


def test_the_watchdog_is_configured_and_generous() -> None:
    ini = _ini_options()
    timeout = ini.get("faulthandler_timeout")

    assert ini.get("faulthandler_exit_on_timeout") is True, (
        "without exit, faulthandler only prints the stack: the hung test then "
        "runs on until the CI job's own limit"
    )
    assert isinstance(timeout, int | float) and timeout >= GENEROUS_FLOOR_SECONDS


@pytest.mark.parametrize("extra", [(), ("-n", "1")], ids=["sequential", "xdist"])
def test_a_hung_test_is_interrupted_with_its_stack(tmp_path: Path, extra: tuple[str, ...]) -> None:
    process, elapsed = _run_hanging_test(tmp_path, *extra)
    output = process.stdout + process.stderr

    assert process.returncode != 0, output[-2000:]
    assert elapsed < HANG_SECONDS - 15, f"the hang was not cut short ({elapsed:.1f} s)"
    assert "Timeout" in output, output[-2000:]
    assert "test_hang.py" in output and "test_hangs" in output, output[-2000:]
