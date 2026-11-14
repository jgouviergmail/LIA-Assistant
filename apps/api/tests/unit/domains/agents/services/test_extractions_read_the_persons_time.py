"""The four background extractions read the person's time (ADR-381 amendment, ADR-380).

The exchange each one reads is stamped in the person's zone, and the present it is told
is written in the same zone and names it: a relative date (« demain », « vendredi »)
resolves against ONE clock, the person's. Proven in a zone away from UTC: Auckland is
UTC+13 in November, so the person's day is already the next one when UTC's is not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.infrastructure.llm.message_view import WRITTEN_AT_KEY

pytestmark = pytest.mark.unit

AUCKLAND = ZoneInfo("Pacific/Auckland")
SAID = datetime(2026, 11, 13, 19, 30, tzinfo=UTC)  # Sat 14 Nov 2026, 08:30 in Auckland
STAMP = "[Sat 14 Nov 2026, 08:30]"
PRESENT = "Sat 14 Nov 2026, 08:30 (Pacific/Auckland)"
REQUEST = "Rappelle-moi d'appeler le plombier demain"


def _exchange() -> list[HumanMessage | AIMessage]:
    return [
        HumanMessage(REQUEST, additional_kwargs={WRITTEN_AT_KEY: SAID.isoformat()}),
        AIMessage("C'est noté."),
    ]


def test_memories_read_the_exchange_stamped_in_the_persons_zone() -> None:
    from src.domains.agents.services.memory_extraction_context import (
        format_messages_for_extraction,
    )

    lines = format_messages_for_extraction(_exchange(), zone=AUCKLAND).splitlines()

    assert lines == [f"USER: {STAMP} {REQUEST}", "ASSISTANT: C'est noté."]


def test_memories_are_told_the_present_in_the_persons_zone() -> None:
    from src.domains.agents.services.memory_extraction_context import render_extraction_prompt

    rendered = render_extraction_prompt(
        conversation="",
        existing_memories="None",
        known_relationships=[],
        health_context="",
        zone=AUCKLAND,
        now=SAID,
    )

    assert PRESENT in rendered
    assert "13/11/2026" not in rendered  # UTC's day, which is not the person's


def test_interests_read_the_exchange_stamped_and_the_present_in_the_zone() -> None:
    from src.domains.interests.services.extraction_service import (
        _format_messages_for_extraction,
        _render_extraction_prompt,
    )

    lines = _format_messages_for_extraction(_exchange(), zone=AUCKLAND).splitlines()
    rendered = _render_extraction_prompt("", [], "en", zone=AUCKLAND, now=SAID)

    assert lines[0] == f"USER: {STAMP} {REQUEST}"
    assert PRESENT in rendered and "13/11/2026" not in rendered


def test_open_loops_read_the_tail_stamped_and_the_present_in_the_zone() -> None:
    from src.domains.agents.services import open_loop_extractor as loops

    lines = loops._format_messages_tail(_exchange(), zone=AUCKLAND).splitlines()
    prompt = loops.render_system_prompt(zone=AUCKLAND, now=SAID)

    assert lines[0] == f"USER: {STAMP} {REQUEST}"
    assert PRESENT in prompt


def test_an_offset_less_deadline_is_the_persons_wall_time() -> None:
    """Told the present in the person's zone, a bare « 09:00 » is theirs — never UTC's."""
    from src.domains.agents.services import open_loop_extractor as loops

    due = loops._parse_due_hint("2026-11-15T09:00:00", zone=AUCKLAND)

    assert due == datetime(2026, 11, 15, 9, 0, tzinfo=AUCKLAND)
    assert due is not None and due.astimezone(UTC) == datetime(2026, 11, 14, 20, 0, tzinfo=UTC)
    # An explicit offset is the model's own instant, kept as it is.
    assert loops._parse_due_hint("2026-11-15T09:00:00+01:00", zone=AUCKLAND) == datetime(
        2026, 11, 15, 8, 0, tzinfo=UTC
    )


def test_the_journal_reads_the_exchange_stamped() -> None:
    from src.domains.journals.extraction_context import _format_messages_for_extraction

    lines = _format_messages_for_extraction(_exchange(), zone=AUCKLAND).splitlines()

    assert lines[0] == f"USER: {STAMP} {REQUEST}"
