"""The progressive dashboard is seen by its own panels (fresh review B4).

The web stopped calling the bundle build on a page load, so the build duration, the
bundle builds and the « single » refresh scope only saw a refresh-all and external
clients — dashboard 25 would have read near zero — and a lone card refresh, now on the
section route, counted nothing. Each step of an act is timed, and a card refresh is a
refresh request.
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from src.domains.briefing.progressive import (
    act_section,
    act_text,
    initial_cards,
    refresh_section,
)
from src.domains.briefing.service import BriefingService
from tests.unit.domains.briefing.page_load_harness import Rig, make_user
from tests.unit.domains.briefing.progressive_harness import MORNING, progressive_installed

pytestmark = pytest.mark.unit


def _steps(step: str) -> float:
    return (
        REGISTRY.get_sample_value("briefing_act_step_duration_seconds_count", {"step": step}) or 0
    )


def _refreshes(scope: str) -> float:
    return REGISTRY.get_sample_value("briefing_refresh_requests_total", {"scope": scope}) or 0


async def test_each_step_of_an_act_is_timed() -> None:
    rig = Rig()
    user = make_user()
    before = {step: _steps(step) for step in ("initial", "section", "text")}
    with progressive_installed(rig):
        load = await initial_cards(BriefingService(user), now=MORNING)
        await act_section(BriefingService(user), "mails", act=load.act, now=MORNING)
        await act_text(BriefingService(user), act=load.act, force=False, now=MORNING)

    assert {step: _steps(step) - before[step] for step in before} == {
        "initial": 1,
        "section": 1,
        "text": 1,
    }


async def test_a_card_refresh_is_a_single_refresh_request() -> None:
    rig = Rig()
    user = make_user()
    before = _refreshes("single")
    with progressive_installed(rig):
        await refresh_section(BriefingService(user), "mails")

    assert _refreshes("single") == before + 1
    assert _steps("refresh") >= 1
