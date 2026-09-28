"""The radio's jobs exist where the deployment ships the radio, and only there (ADR-324)."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_RADIO_MEDIA_SWEEP, SCHEDULER_JOB_RADIO_NEWSROOM_COLLECT
from src.domains.radio.jobs import run_newsroom_pass, sweep_radio_media
from src.infrastructure.startup import schedulers
from src.infrastructure.startup.scheduler_radio import register_radio_jobs

pytestmark = pytest.mark.unit


def test_a_deployment_without_the_radio_schedules_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "radio_enabled", False)
    scheduler = MagicMock()

    register_radio_jobs(scheduler)

    scheduler.add_job.assert_not_called()


def test_a_deployment_with_the_radio_schedules_both_jobs_on_their_periods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "radio_enabled", True)
    scheduler = MagicMock()

    register_radio_jobs(scheduler)

    jobs = {call.kwargs["id"]: call for call in scheduler.add_job.call_args_list}
    assert set(jobs) == {SCHEDULER_JOB_RADIO_NEWSROOM_COLLECT, SCHEDULER_JOB_RADIO_MEDIA_SWEEP}
    newsroom = jobs[SCHEDULER_JOB_RADIO_NEWSROOM_COLLECT]
    assert newsroom.args == (run_newsroom_pass,)
    assert newsroom.kwargs["seconds"] == settings.radio_newsroom_interval_seconds
    sweep = jobs[SCHEDULER_JOB_RADIO_MEDIA_SWEEP]
    assert sweep.args == (sweep_radio_media,)
    assert sweep.kwargs["seconds"] == settings.radio_media_sweep_interval_seconds
    for call in jobs.values():
        assert call.kwargs["max_instances"] == 1
        assert call.kwargs["replace_existing"] is True


def test_the_startup_step_calls_the_registrar() -> None:
    assert "register_radio_jobs(scheduler)" in inspect.getsource(schedulers)
