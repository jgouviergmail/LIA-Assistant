"""« For you » briefing card (P15, Lot 4 — interdomain program).

Aggregates Lot 2 (open loops) + Lot 3 (automations digest) outputs into one
LLM-free section. Open loops are flag-gated (section NOT_CONFIGURED hides
the sub-block); the automations digest is always available.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.fetchers import fetch_for_you
from src.domains.briefing.schemas import ForYouData

NOW = datetime.now(UTC)
TZ = ZoneInfo("Europe/Paris")


def _loop(subject="rappeler le plombier", due=None, direction="user_owes"):
    return SimpleNamespace(
        id=uuid4(),
        subject=subject,
        counterparty="le plombier",
        direction=direction,
        due_hint=due,
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=1),
    )


def _action(title="Revue de presse IA", executed=None, next_at=None, enabled=True):
    return SimpleNamespace(
        id=uuid4(),
        title=title,
        last_executed_at=executed,
        next_trigger_at=next_at or NOW + timedelta(hours=20),
        is_enabled=enabled,
    )


def _db_ctx():
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        yield MagicMock()

    return _ctx


@pytest.mark.unit
class TestFetchForYou:
    async def test_aggregates_loops_and_automations(self):
        loop_repo = MagicMock()
        loop_repo.list_open_for_user = AsyncMock(return_value=[_loop()])
        sched_service = MagicMock()
        sched_service.list_for_user = AsyncMock(
            return_value=[
                _action(executed=NOW - timedelta(hours=3)),
                _action(title="Vieille", executed=NOW - timedelta(days=3)),
            ]
        )

        with (
            patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
            patch(
                "src.domains.open_loops.repository.OpenLoopRepository",
                return_value=loop_repo,
            ),
            patch(
                "src.domains.scheduled_actions.service.ScheduledActionService",
                return_value=sched_service,
            ),
            patch(
                "src.domains.briefing.fetchers.settings",
                SimpleNamespace(
                    open_loops_enabled=True,
                    briefing_max_open_loops_items=3,
                    briefing_max_mails_items=5,
                ),
            ),
        ):
            data = await fetch_for_you(user_id=uuid4(), user_tz=TZ)

        assert isinstance(data, ForYouData)
        assert len(data.open_loops) == 1
        assert data.open_loops[0].subject == "rappeler le plombier"
        # Digest: only executions within the last 24 h
        assert len(data.recent_automations) == 1
        assert data.recent_automations[0].title == "Revue de presse IA"
        # Next upcoming automation (enabled, soonest next_trigger_at)
        assert data.next_automation is not None

    async def test_next_automation_carries_preformatted_local_time(self):
        """The card shows the actual execution time, not a vague label:
        ``next_trigger_local`` is pre-formatted backend-side (user timezone +
        language), same doctrine as ``ReminderItem.trigger_at_local``."""
        tomorrow_9h = (datetime.now(TZ) + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        sched_service = MagicMock()
        sched_service.list_for_user = AsyncMock(
            return_value=[_action(next_at=tomorrow_9h.astimezone(UTC))]
        )

        with (
            patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
            patch(
                "src.domains.scheduled_actions.service.ScheduledActionService",
                return_value=sched_service,
            ),
            patch(
                "src.domains.briefing.fetchers.settings",
                SimpleNamespace(
                    open_loops_enabled=False,
                    briefing_max_open_loops_items=3,
                    briefing_max_mails_items=5,
                ),
            ),
        ):
            data = await fetch_for_you(user_id=uuid4(), user_tz=TZ, language="fr")

        assert data.next_automation is not None
        assert data.next_automation.next_trigger_local == "09:00 demain"

    async def test_loops_hidden_when_flag_off(self):
        sched_service = MagicMock()
        sched_service.list_for_user = AsyncMock(return_value=[])

        loop_repo = MagicMock()
        loop_repo.list_open_for_user = AsyncMock(return_value=[_loop()])

        with (
            patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
            patch(
                "src.domains.open_loops.repository.OpenLoopRepository",
                return_value=loop_repo,
            ),
            patch(
                "src.domains.scheduled_actions.service.ScheduledActionService",
                return_value=sched_service,
            ),
            patch(
                "src.domains.briefing.fetchers.settings",
                SimpleNamespace(
                    open_loops_enabled=False,
                    briefing_max_open_loops_items=3,
                    briefing_max_mails_items=5,
                ),
            ),
        ):
            data = await fetch_for_you(user_id=uuid4(), user_tz=TZ)

        assert data.open_loops == []
        loop_repo.list_open_for_user.assert_not_awaited()

    async def test_disabled_automations_never_next(self):
        sched_service = MagicMock()
        sched_service.list_for_user = AsyncMock(return_value=[_action(title="Off", enabled=False)])
        with (
            patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
            patch(
                "src.domains.scheduled_actions.service.ScheduledActionService",
                return_value=sched_service,
            ),
            patch(
                "src.domains.briefing.fetchers.settings",
                SimpleNamespace(
                    open_loops_enabled=False,
                    briefing_max_open_loops_items=3,
                    briefing_max_mails_items=5,
                ),
            ),
        ):
            data = await fetch_for_you(user_id=uuid4(), user_tz=TZ)

        assert data.next_automation is None


@pytest.mark.unit
class TestCardsBundleForYou:
    def test_bundle_carries_the_seventh_section(self):
        from src.domains.briefing.constants import SECTION_FOR_YOU, SECTION_NAMES
        from src.domains.briefing.schemas import CardsBundle

        assert SECTION_FOR_YOU == "for_you"
        assert SECTION_FOR_YOU in SECTION_NAMES
        assert "for_you" in CardsBundle.model_fields


@pytest.mark.unit
class TestForYouInSynthesis:
    """(b) — the synthesis sees the for_you section and the portrait block."""

    def _bundle_with_for_you(self):
        from src.domains.briefing.schemas import (
            CardsBundle,
            CardSection,
            CardStatus,
            ForYouAutomationItem,
            ForYouLoopItem,
        )

        empty = CardSection(status=CardStatus.NOT_CONFIGURED, generated_at=NOW)
        for_you = CardSection(
            status=CardStatus.OK,
            generated_at=NOW,
            data=ForYouData(
                open_loops=[
                    ForYouLoopItem(
                        id="l1",
                        subject="rappeler le plombier",
                        counterparty="le plombier",
                        direction="user_owes",
                        due_hint=None,
                        days_open=3,
                    )
                ],
                recent_automations=[ForYouAutomationItem(id="a1", title="Revue de presse IA")],
                next_automation=None,
            ),
        )
        return CardsBundle(
            weather=empty,
            agenda=empty,
            mails=empty,
            birthdays=empty,
            reminders=empty,
            health=empty,
            for_you=for_you,
            tasks=empty,
            documents=empty,
        )

    def test_summarizer_renders_open_loops_and_automations(self):
        from src.domains.briefing.llm import _summarize_cards_for_llm

        rendered = _summarize_cards_for_llm(self._bundle_with_for_you(), verbose=True)
        assert "rappeler le plombier" in rendered
        assert "Revue de presse IA" in rendered

    async def test_synthesis_prompt_receives_portrait_block(self):

        from src.domains.briefing import llm as briefing_llm

        user = SimpleNamespace(
            id=uuid4(),
            display_name="Jo",
            first_name="Jo",
            full_name="Jo Lemoine",
            email="jo@example.com",
            journals_enabled=True,
        )
        captured: dict = {}

        async def _fake_invoke(*, rendered, user, target_prefix, kind):
            captured["rendered"] = rendered
            return "Synthèse.", None

        with (
            patch.object(briefing_llm, "BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA", 1),
            patch.object(briefing_llm, "_invoke_and_track", _fake_invoke),
            patch.object(
                briefing_llm,
                "load_prompt",
                return_value="{user_name}|{today_iso}|{time_of_day}|{day_of_week}|{language}|{personality_brief}|{active_sections}|{user_model_block}",
            ),
            patch.object(briefing_llm, "_resolve_personality", AsyncMock(return_value="p")),
            patch(
                "src.domains.journals.portrait_builder.build_journal_user_model_block",
                AsyncMock(return_value="PORTRAIT_BRIEF_BLOCK"),
            ),
        ):
            text, _ = await briefing_llm.generate_synthesis(
                user=user,
                user_tz=TZ,
                cards=self._bundle_with_for_you(),
                language="fr",
            )

        assert text == "Synthèse."
        assert "PORTRAIT_BRIEF_BLOCK" in captured["rendered"]


@pytest.mark.unit
class TestForYouHasContent:
    def test_empty_for_you_is_empty_section(self):
        from src.domains.briefing.service import _has_content

        assert (
            _has_content(ForYouData(open_loops=[], recent_automations=[], next_automation=None))
            is False
        )

    def test_any_subblock_counts_as_content(self):
        from src.domains.briefing.schemas import ForYouAutomationItem
        from src.domains.briefing.service import _has_content

        assert (
            _has_content(
                ForYouData(
                    open_loops=[],
                    recent_automations=[],
                    next_automation=ForYouAutomationItem(id="a", title="T"),
                )
            )
            is True
        )
