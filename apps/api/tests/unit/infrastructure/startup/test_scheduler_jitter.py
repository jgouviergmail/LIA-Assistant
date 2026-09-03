"""Interval jobs must not all fire on the same second.

Measured in production on 2026-09-01. The interval periods are 5, 5, 15, 30, 30
and 60 minutes — every one a multiple of five — and they all start counting at
scheduler start. Only one job carried an offset and none carried jitter, so the
alignment was arithmetic and permanent: six jobs in the same second, every hour.

That is what produced the embedding incident. Each proactive job runs an agent,
each agent issues several embeddings, and the provider quota is not exceeded by
the volume (a steady four calls a minute passed without a single error) but by
the concentration.

This guard reads the REGISTERED triggers rather than the source, so a job added
later is covered without anyone remembering this file exists.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

#: The startup step AND every extracted registrar it calls — a job registered
#: in a module this tuple does not name would escape the guard.
_SCHEDULERS = (
    pathlib.Path("src/infrastructure/startup/schedulers.py"),
    pathlib.Path("src/infrastructure/startup/scheduler_meetings.py"),
    pathlib.Path("src/infrastructure/startup/scheduler_push.py"),
)

#: Jobs that must stay on an exact cadence, with the reason each one earns it.
#:
#: This list is the whole point of the guard: an exemption is a written
#: decision, not a job somebody forgot.
JITTER_EXEMPT: dict[str, str] = {
    "SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR": (
        "Executes actions the USER dated. Jitter here is not spreading load, "
        "it is delivering late."
    ),
}


def _interval_job_calls() -> list[ast.Call]:
    """Every ``add_job(..., trigger="interval", ...)`` in the startup step."""
    nodes = [
        node
        for path in _SCHEDULERS
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
    ]
    calls: list[ast.Call] = []
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_job"):
            continue
        for kw in node.keywords:
            if (
                kw.arg == "trigger"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == "interval"
            ):
                calls.append(node)
    return calls


def _job_id(call: ast.Call) -> str:
    for kw in call.keywords:
        if kw.arg == "id":
            if isinstance(kw.value, ast.Name):
                return kw.value.id
            if isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
    return "<unnamed>"


def _has_jitter(call: ast.Call) -> bool:
    return any(kw.arg == "jitter" for kw in call.keywords)


class TestEveryIntervalJobIsSpread:
    def test_the_startup_step_registers_interval_jobs_at_all(self) -> None:
        """Guards the guard: a refactor that stopped matching would make every
        assertion below vacuously true."""
        assert len(_interval_job_calls()) >= 10

    def test_every_interval_job_carries_jitter_or_a_written_exemption(self) -> None:
        missing = [
            _job_id(call)
            for call in _interval_job_calls()
            if not _has_jitter(call) and _job_id(call) not in JITTER_EXEMPT
        ]
        assert not missing, (
            "Interval jobs without jitter align on the same second forever "
            f"(measured: six in one second, hourly): {missing}. Add jitter, or "
            "add the job to JITTER_EXEMPT with the reason it must stay exact."
        )

    def test_an_exempt_job_really_has_no_jitter(self) -> None:
        """An exemption that is not exercised is a comment pretending to be a
        rule; if the job gains jitter, the entry must go."""
        for call in _interval_job_calls():
            job_id = _job_id(call)
            if job_id in JITTER_EXEMPT:
                assert not _has_jitter(call), (
                    f"{job_id} is listed as needing an exact cadence but carries "
                    "jitter — remove it from JITTER_EXEMPT or remove the jitter."
                )


class TestJitterSizing:
    """The helper that turns a period into a spread."""

    def test_jitter_is_a_fraction_of_the_period_never_the_whole(self) -> None:
        from src.infrastructure.startup.schedulers import jitter_seconds_for

        for minutes in (1, 5, 15, 30, 60):
            jitter = jitter_seconds_for(minutes=minutes)
            assert 0 < jitter < minutes * 60, (
                "A jitter as wide as the period lets two consecutive runs " "overlap or invert."
            )

    def test_a_longer_period_gets_a_wider_spread(self) -> None:
        from src.infrastructure.startup.schedulers import jitter_seconds_for

        assert jitter_seconds_for(minutes=60) > jitter_seconds_for(minutes=5)

    def test_a_short_period_still_gets_a_usable_spread(self) -> None:
        """A percentage of a very short period rounds to zero, which would
        silently leave the fastest jobs aligned — exactly the ones that
        collide most often."""
        from src.infrastructure.startup.schedulers import jitter_seconds_for

        assert jitter_seconds_for(seconds=30) >= 1

    def test_seconds_and_minutes_describe_the_same_period_identically(self) -> None:
        from src.infrastructure.startup.schedulers import jitter_seconds_for

        assert jitter_seconds_for(minutes=5) == jitter_seconds_for(seconds=300)

    def test_a_non_positive_period_yields_no_jitter_rather_than_raising(self) -> None:
        """Startup must never fail on arithmetic; a misconfigured interval is
        already reported by the settings layer."""
        from src.infrastructure.startup.schedulers import jitter_seconds_for

        assert jitter_seconds_for(minutes=0) == 0
        assert jitter_seconds_for(seconds=-5) == 0
