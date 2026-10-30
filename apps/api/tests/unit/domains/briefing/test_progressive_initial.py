"""The initial dashboard response: what shows at once, never a slow source (spec §5.8, D2)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.core.config import settings
from src.domains.briefing.act_token import briefing_context_digest, verify_act
from src.domains.briefing.progressive import act_section, initial_cards
from src.domains.briefing.schemas import CardStatus
from src.domains.briefing.service import BriefingService
from tests.unit.domains.briefing.page_load_harness import Rig, make_user
from tests.unit.domains.briefing.progressive_harness import MORNING, progressive_installed

pytestmark = pytest.mark.unit

#: The sections read from their cache or left pending; the others are read live.
SLOW = ("weather", "agenda", "mails", "birthdays", "health", "for_you", "tasks", "documents")


async def test_initial_returns_cached_local_and_pending() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig) as register:
        cold = await initial_cards(BriefingService(user), now=MORNING)

        assert {name: rig.calls[name] for name in SLOW} == dict.fromkeys(SLOW, 0)
        assert rig.calls["reminders"] == rig.calls["workboard"] == 1
        assert cold.pending == list(SLOW)
        for name in SLOW:
            assert getattr(cold.cards, name).status is CardStatus.PENDING
        assert cold.cards.reminders.status is CardStatus.OK
        assert cold.cards.workboard.status is CardStatus.OK

        # The weather settles through its section read; the next load serves it from cache.
        await act_section(BriefingService(user), "weather", act=cold.act, now=MORNING)
        rig.reset_calls()
        warm = await initial_cards(BriefingService(user), now=MORNING)

    assert rig.calls["weather"] == 0
    assert warm.cards.weather.status is CardStatus.OK
    assert warm.cards.weather.from_cache is True
    assert "weather" not in warm.pending
    assert register.decisions[0][2] is True  # filed once per act


async def test_hidden_section_is_a_placeholder_never_pending() -> None:
    rig = Rig()
    user = make_user(hidden=("weather", "reminders"))
    with progressive_installed(rig):
        initial = await initial_cards(BriefingService(user), now=MORNING)

    assert initial.cards.weather.status is CardStatus.HIDDEN
    assert initial.cards.reminders.status is CardStatus.HIDDEN
    assert "weather" not in initial.pending
    assert rig.calls["weather"] == rig.calls["reminders"] == 0


async def test_the_act_is_signed_for_the_caller_and_the_current_context() -> None:
    rig = Rig()
    user = make_user()
    service = BriefingService(user)
    with progressive_installed(rig) as register:
        initial = await initial_cards(service, now=MORNING)

    digest = briefing_context_digest(
        hidden=frozenset(),
        language=service.language,
        timezone=str(service.user_tz),
        local_day=MORNING.astimezone(service.user_tz).date(),
    )
    verdict = verify_act(initial.act, user_id=user.id, context_digest=digest, now=MORNING)
    assert verdict.check == "valid"
    assert initial.act_expires_at == MORNING + timedelta(
        seconds=settings.briefing_act_token_ttl_seconds
    )
    assert initial.section_concurrency == settings.briefing_section_concurrency
    # The local reads are this act's: consultations, spend and decision under its id.
    assert sorted(register.opened(str(verdict.act_id))) == ["reminders", "sms", "workboard"]
    assert register.spend_runs == [verdict.act_id]
    assert register.decisions == [(verdict.act_id, "briefing_cards", True)]


async def test_nothing_read_files_no_decision() -> None:
    rig = Rig()
    user = make_user(hidden=("reminders", "workboard", "sms"))
    with progressive_installed(rig) as register:
        await initial_cards(BriefingService(user), now=MORNING)

    assert register.decisions == []
