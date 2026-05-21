"""Unit tests for the briefing greeting agenda hint.

The greeting is a "today" greeting generated from a compact, non-verbose card
summary. Before the fix, that summary passed only ``agenda_count`` and dropped
the event dates, so the greeting could not tell that the only agenda item is
*tomorrow* — it could imply the appointment is today. ``start_local`` is already
locale-rendered with the day ("demain 08:00" / a date), so surfacing the next
event's start gives the greeting the temporal context it needs. The verbose
synthesis already received the dates and was therefore always correct.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from src.domains.briefing.llm import _summarize_cards_for_llm
from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    CardsBundle,
    CardSection,
    CardStatus,
)


def _section(status: CardStatus = CardStatus.NOT_CONFIGURED, data: object = None) -> CardSection:
    return CardSection(status=status, data=data, generated_at=datetime.now(UTC))


def _bundle_with_agenda(events: list[AgendaEventItem]) -> CardsBundle:
    return CardsBundle(
        weather=_section(),
        agenda=_section(CardStatus.OK, AgendaData(events=events)),
        mails=_section(),
        birthdays=_section(),
        reminders=_section(),
        health=_section(),
    )


@pytest.mark.unit
class TestGreetingAgendaHint:
    def test_greeting_summary_lists_events_with_day_aware_starts(self):
        """verbose=False gives the upcoming events with per-event day-aware starts
        (no misleading aggregate count) so the greeting can react to the day's
        shape and tell today from tomorrow without lumping them together."""
        events = [
            AgendaEventItem(title="Ramonage", start_local="15:00"),
            AgendaEventItem(title="Dentiste", start_local="demain 08:00"),
        ]
        summary = json.loads(_summarize_cards_for_llm(_bundle_with_agenda(events), verbose=False))
        assert summary["agenda"] == [
            {"title": "Ramonage", "start": "15:00"},
            {"title": "Dentiste", "start": "demain 08:00"},
        ]

    def test_greeting_summary_empty_agenda_is_empty_list(self):
        summary = json.loads(_summarize_cards_for_llm(_bundle_with_agenda([]), verbose=False))
        assert summary["agenda"] == []

    def test_synthesis_summary_unchanged_lists_titles(self):
        """verbose=True (synthesis) keeps listing titles + start — no regression."""
        events = [AgendaEventItem(title="Ramonage", start_local="demain 08:00")]
        summary = json.loads(_summarize_cards_for_llm(_bundle_with_agenda(events), verbose=True))
        assert summary["agenda"][0]["title"] == "Ramonage"
        assert summary["agenda"][0]["start"] == "demain 08:00"


@pytest.mark.unit
class TestGreetingPromptFormatting:
    """The greeting prompt is rendered via ``str.format`` — any stray unescaped
    ``{`` / ``}`` is parsed as a replacement field and raises KeyError at runtime,
    silently degrading the greeting to the static fallback. This pins that the
    template formats cleanly with the exact kwargs ``generate_greeting`` passes."""

    def test_greeting_prompt_formats_without_stray_braces(self):
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.domains.briefing.constants import BRIEFING_GREETING_PROMPT_NAME

        template = load_prompt(BRIEFING_GREETING_PROMPT_NAME, version="v1")
        # Must not raise: a literal `{...}` in the template (other than the known
        # placeholders) would trigger KeyError / ValueError here.
        rendered = template.format(
            user_name="Jérôme",
            today_iso="2026-05-21",
            time_of_day="afternoon",
            day_of_week="Thursday",
            language="fr",
            personality_brief="warm, direct",
            active_sections='{"agenda":{"count":1,"next":{"title":"Ramonage","start":"15:00"}}}',
        )
        assert "Jérôme" in rendered
