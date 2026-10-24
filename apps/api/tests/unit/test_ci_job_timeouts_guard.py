"""Guard: every workflow job carries its own time limit (AC-033a).

Why
---
Twenty-five jobs across five workflows declared no ``timeout-minutes`` (measured
2026-10-23): a hung step ran to GitHub's six-hour limit, and nothing ended it
earlier with a verdict. The limits are sized from measurement — about twice the
longest of the recent successful runs (``gh run view``, 2026-10-23), never under
ten minutes — so a limit detects a hang; it is not a performance target. A job
that legitimately grows past its limit gets a new measurement, not a removal.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

pytestmark = pytest.mark.unit

#: GitHub's own ceiling for a job on a hosted runner: a limit at or above it bounds nothing.
PLATFORM_LIMIT_MINUTES = 360
#: Anti-vacuity floor: 31 jobs across eight workflows on 2026-10-23.
MIN_EXPECTED_JOBS = 25


def _jobs() -> Iterator[tuple[str, str, dict[str, object]]]:
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_id, job in (workflow.get("jobs") or {}).items():
            yield path.name, str(job_id), job


def _bounded(value: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 < value < PLATFORM_LIMIT_MINUTES
    )


def test_the_scan_sees_the_workflows() -> None:
    assert len(list(_jobs())) >= MIN_EXPECTED_JOBS


def test_every_job_declares_a_time_limit_below_the_platform_one() -> None:
    unbounded = [
        f"{workflow}: {job_id} (timeout-minutes={job.get('timeout-minutes')!r})"
        for workflow, job_id, job in _jobs()
        # A reusable-workflow call takes no timeout-minutes: the called jobs carry theirs.
        if "uses" not in job and not _bounded(job.get("timeout-minutes"))
    ]

    assert not unbounded, (
        "these jobs run to GitHub's six-hour limit when a step hangs; give each a "
        "measured timeout-minutes (about twice its longest recent run):\n  "
        + "\n  ".join(unbounded)
    )


def test_the_guard_reads_real_files(tmp_path: Path) -> None:
    """Guard the guard: the predicate refuses what it must refuse."""
    assert _bounded(15)
    for refused in (None, 0, -5, True, "15", PLATFORM_LIMIT_MINUTES, 15.5):
        assert not _bounded(refused), refused
