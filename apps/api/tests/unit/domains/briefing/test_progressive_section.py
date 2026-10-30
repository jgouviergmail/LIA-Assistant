"""One section of a dashboard act: one source, once across workers, filed under the act."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from src.core.exceptions import ResourceConflictError, ValidationError
from src.domains.briefing.act_token import new_act_id
from src.domains.briefing.progressive import (
    BriefingContextChanged,
    act_section,
    initial_cards,
    refresh_section,
)
from src.domains.briefing.progressive_router import (
    ERROR_CODE_CONTEXT_CHANGED,
    get_act_section,
    post_section_refresh,
)
from src.domains.briefing.schemas import CardStatus
from src.domains.briefing.service import BriefingService
from tests.unit.domains.briefing.page_load_harness import Rig, make_user
from tests.unit.domains.briefing.progressive_harness import MORNING, progressive_installed

pytestmark = pytest.mark.unit


async def test_section_reads_exactly_one_source() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        initial = await initial_cards(BriefingService(user), now=MORNING)
        rig.reset_calls()
        section = await act_section(BriefingService(user), "weather", act=initial.act, now=MORNING)

    assert dict(rig.calls) == {"weather": 1}
    assert section.status is CardStatus.OK


async def test_section_under_act_records_once() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig) as register:
        initial = await initial_cards(BriefingService(user), now=MORNING)
        act_id = register.spend_runs[0]
        await asyncio.gather(
            act_section(BriefingService(user), "weather", act=initial.act, now=MORNING),
            act_section(BriefingService(user), "mails", act=initial.act, now=MORNING),
        )

    assert {"weather", "mails"} <= set(register.opened(act_id))
    assert {row["run_id"] for row in register.rows()} == {act_id}
    assert set(register.consulted) == {act_id}
    assert set(register.spend_runs) == {act_id}
    assert {run_id for run_id, _, _ in register.decisions} == {act_id}
    assert all(once for _, _, once in register.decisions)


async def test_one_section_is_read_once_across_concurrent_acts() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        first = await initial_cards(BriefingService(user), now=MORNING)
        second = await initial_cards(BriefingService(user), now=MORNING)
        rig.reset_calls()
        sections = await asyncio.gather(
            act_section(BriefingService(user), "agenda", act=first.act, now=MORNING),
            act_section(BriefingService(user), "agenda", act=second.act, now=MORNING),
        )

    assert rig.calls["agenda"] == 1
    assert [section.status for section in sections] == [CardStatus.OK, CardStatus.OK]


async def test_section_request_after_local_midnight_is_409() -> None:
    rig = Rig()
    user = make_user(timezone="Europe/Paris")
    before_midnight = datetime(2026, 10, 28, 22, 59, tzinfo=UTC)  # 23:59 in Paris
    with progressive_installed(rig):
        initial = await initial_cards(BriefingService(user), now=before_midnight)
        after_midnight = before_midnight + timedelta(minutes=2)
        with pytest.raises(BriefingContextChanged):
            await act_section(BriefingService(user), "weather", act=initial.act, now=after_midnight)

    assert rig.calls["weather"] == 0


async def test_the_route_answers_a_changed_context_with_409() -> None:
    rig = Rig()
    user = make_user()
    long_ago = datetime(2020, 1, 1, 8, 0, tzinfo=UTC)
    with progressive_installed(rig):
        stale = await initial_cards(BriefingService(user), now=long_ago)
        with pytest.raises(ResourceConflictError) as refused:
            await get_act_section("weather", act=stale.act, current_user=user)

    assert refused.value.detail == {"code": ERROR_CODE_CONTEXT_CHANGED}
    assert rig.calls["weather"] == 0


async def test_expired_act_is_409() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        initial = await initial_cards(BriefingService(user), now=MORNING)
        with pytest.raises(BriefingContextChanged):
            await act_section(
                BriefingService(user),
                "weather",
                act=initial.act,
                now=initial.act_expires_at + timedelta(seconds=1),
            )


async def test_a_foreign_act_runs_as_a_fresh_act_of_the_caller() -> None:
    rig = Rig()
    owner, intruder = make_user(), make_user()
    with progressive_installed(rig) as register:
        foreign = await initial_cards(BriefingService(owner), now=MORNING)
        foreign_act = register.spend_runs[-1]
        section = await act_section(
            BriefingService(intruder), "weather", act=foreign.act, now=MORNING
        )
        own_run = register.spend_runs[-1]

    assert section.status is CardStatus.OK
    assert own_run != foreign_act
    assert own_run.startswith("briefing_act_")
    assert register.opened(own_run) == ["weather"]
    assert "weather" not in register.opened(foreign_act)


async def test_refresh_reads_the_source_again_and_writes_no_text() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        initial = await initial_cards(BriefingService(user), now=MORNING)
        await act_section(BriefingService(user), "weather", act=initial.act, now=MORNING)
        rig.reset_calls()
        section = await refresh_section(BriefingService(user), "weather")

    assert dict(rig.calls) == {"weather": 1}
    assert section.status is CardStatus.OK
    assert section.from_cache is False
    assert rig.summarised == []


async def test_unknown_or_hidden_section_is_refused_before_any_read() -> None:
    rig = Rig()
    user = make_user(hidden=("weather",))
    with progressive_installed(rig):
        for name in ("weather", "nope"):
            with pytest.raises(ValidationError):
                await post_section_refresh(name, current_user=user)
        with pytest.raises(ValidationError):
            await get_act_section("nope", act=new_act_id(), current_user=user)

    assert sum(rig.calls.values()) == 0


async def test_the_initial_route_opens_an_act_its_text_route_honours() -> None:
    from src.domains.briefing.progressive_router import get_initial_cards, post_act_text
    from src.domains.briefing.schemas import BriefingTextRequest

    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        initial = await get_initial_cards(current_user=user)
        text = await post_act_text(
            BriefingTextRequest(act=initial.act, force=False), current_user=user
        )

    assert initial.act
    assert text.state == "ready"


async def test_the_text_route_answers_a_changed_context_with_409() -> None:
    from src.domains.briefing.progressive_router import post_act_text
    from src.domains.briefing.schemas import BriefingTextRequest

    rig = Rig()
    user = make_user()
    long_ago = datetime(2020, 1, 1, 8, 0, tzinfo=UTC)
    with progressive_installed(rig):
        stale = await initial_cards(BriefingService(user), now=long_ago)
        with pytest.raises(ResourceConflictError) as refused:
            await post_act_text(BriefingTextRequest(act=stale.act, force=False), current_user=user)

    assert refused.value.detail == {"code": ERROR_CODE_CONTEXT_CHANGED}
