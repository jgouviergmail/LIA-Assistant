"""The push sync job must run shortly after boot, not one interval later.

APScheduler's ``trigger="interval"`` schedules the FIRST run at
``now + interval``. With a 6-hour interval that means: flag switched on →
no channel exists for six hours, and an API that restarts more often than
the interval never opens a channel at all. ADR-178 measured exactly this
class of starvation on the product rollup ("every gauge stayed empty across
4 boots") and fixed it with ``next_run_time``.

Push is the worst case of the family: a job that never runs means the
feature is simply off while the flag says it is on.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

_SCHEDULERS = pathlib.Path("src/infrastructure/startup/schedulers.py")
# Interval jobs whose delay makes a missed first run a FUNCTIONAL outage
# (not just late housekeeping): they must pin next_run_time.
_MUST_RUN_AFTER_BOOT = {"SCHEDULER_JOB_PUSH_CHANNEL_SYNC"}


def _interval_jobs() -> dict[str, set[str]]:
    """{job id constant: set of add_job keyword names} for interval jobs."""
    tree = ast.parse(_SCHEDULERS.read_text(encoding="utf-8"))
    jobs: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_job"):
            continue
        keywords = {kw.arg: kw for kw in node.keywords if kw.arg}
        trigger = keywords.get("trigger")
        if trigger is None or getattr(trigger.value, "value", None) != "interval":
            continue
        if "id" not in keywords:
            continue
        jobs[ast.unparse(keywords["id"].value)] = set(keywords)
    return jobs


class TestFirstRunAfterBoot:
    def test_long_interval_jobs_pin_next_run_time(self) -> None:
        jobs = _interval_jobs()
        missing = [
            job_id
            for job_id in _MUST_RUN_AFTER_BOOT
            if job_id in jobs and "next_run_time" not in jobs[job_id]
        ]
        assert not missing, (
            f"interval job(s) without next_run_time: {missing} — the first run "
            "would only happen one full interval after boot (ADR-178 starvation)."
        )

    def test_the_guarded_jobs_are_actually_registered(self) -> None:
        # A guard that silently stops matching anything protects nothing.
        jobs = _interval_jobs()
        assert _MUST_RUN_AFTER_BOOT <= set(jobs), (
            f"guarded job id(s) no longer registered as interval jobs: "
            f"{_MUST_RUN_AFTER_BOOT - set(jobs)}"
        )
