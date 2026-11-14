"""One discussion as a Markdown document its owner can keep.

What must hold:

- the document is in the reader's language and on the reader's CLOCK — proven
  in a zone far from UTC, on an instant whose local day is not the UTC day;
- the person's words are exported as typed; an answer LIA drew as an HTML
  document is exported as Markdown, through the one conversion door;
- the read is COMPLETE and closed at the instant of the export: every message
  the chat shows, oldest first, no page and no ceiling.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.conversation_target import ConversationKind
from src.domains.conversations import discussion_export
from src.domains.conversations.discussion_export import (
    render_header,
    render_message,
    stream_discussion_markdown,
)
from tests.fixtures.conversation_cases import conversation_target

pytestmark = pytest.mark.unit

#: UTC+13 in November: 22:30 UTC on the 11th is 11:30 on the 12th there.
AUCKLAND = "Pacific/Auckland"
INSTANT = datetime(2026, 11, 11, 22, 30, tzinfo=UTC)


def _message(role: str, content: str, at: datetime = INSTANT) -> Any:
    return SimpleNamespace(role=role, content=content, created_at=at)


class TestTheHeader:
    def test_it_names_the_discussion_and_dates_the_export_on_the_reader_s_clock(self) -> None:
        header = render_header(
            "Trip to Lisbon", language="fr", timezone=AUCKLAND, generated_at=INSTANT
        )

        assert header.startswith("# Trip to Lisbon\n")
        # The reader's day, not the server's.
        assert "12 novembre 2026" in header and "11:30" in header
        assert "11 novembre" not in header

    def test_a_title_holding_a_line_break_stays_one_heading(self) -> None:
        header = render_header(
            "Trip\nto Lisbon", language="en", timezone="UTC", generated_at=INSTANT
        )

        assert header.startswith("# Trip to Lisbon\n")

    @pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
    def test_the_frame_is_in_the_reader_s_language(self, language: str) -> None:
        english = render_header("T", language="en", timezone="UTC", generated_at=INSTANT)
        header = render_header("T", language=language, timezone="UTC", generated_at=INSTANT)

        assert (header == english) is (language == "en")


class TestAMessage:
    def test_it_opens_on_who_spoke_at_the_reader_s_local_time(self) -> None:
        block = render_message(_message("user", "Bonjour"), language="fr", timezone=AUCKLAND)

        head = block.splitlines()[0]
        assert head.startswith("**Toi** (")
        assert "12 novembre 2026" in head and "11:30" in head
        assert "Bonjour" in block
        assert block.rstrip().endswith("---")
        assert not any(line.endswith(" ") for line in block.splitlines())

    def test_the_person_s_words_are_exported_as_typed(self) -> None:
        typed = "<b>not markup to convert</b> and a < b"

        block = render_message(_message("user", typed), language="en", timezone="UTC")

        assert typed in block

    def test_an_answer_drawn_as_html_is_exported_as_markdown(self) -> None:
        answer = '<div class="lia-response"><h2>Plan</h2><p>Two <strong>steps</strong>.</p></div>'

        block = render_message(_message("assistant", answer), language="en", timezone="UTC")

        assert block.startswith("**LIA** (")
        assert "## Plan" in block and "**steps**" in block
        assert "<div" not in block

    def test_a_markdown_answer_is_kept_as_written(self) -> None:
        answer = "1. first\n2. `x < y`"

        block = render_message(_message("assistant", answer), language="en", timezone="UTC")

        assert answer in block

    def test_a_markdown_answer_carrying_an_html_block_keeps_its_prose(self) -> None:
        """Only a DOCUMENT is converted. Converting prose that merely carries a
        block would escape every mark it holds and fold its paragraphs
        (measured 2026-11-12: ``\\*\\*Bonjour\\*\\*`` on one line)."""
        answer = (
            "**Bonjour**,\n\nVoici tes _deux_ rendez-vous :\n\n"
            '<div class="lia-card"><h3>Dentiste</h3></div>\n\nBonne journée.'
        )

        block = render_message(_message("assistant", answer), language="fr", timezone="UTC")

        assert answer in block


class _Reads:
    """Stands in for the dedicated session and the cursor underneath."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.asked: list[tuple[uuid.UUID, datetime]] = []
        self.sessions = 0

    @asynccontextmanager
    async def context(self) -> AsyncIterator[object]:
        self.sessions += 1
        yield object()

    def transcript(self, conversation_id: uuid.UUID, until: datetime) -> str:
        self.asked.append((conversation_id, until))
        return "statement"

    async def stream(self, _db: object, statement: Any, **options: Any) -> AsyncIterator[Any]:
        assert statement == "statement"
        assert options["batch"] == 7
        for row in self.rows:
            yield row


async def _document(reads: _Reads, monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> str:
    monkeypatch.setattr(discussion_export, "get_db_context", reads.context)
    monkeypatch.setattr(discussion_export, "discussion_transcript", reads.transcript)
    monkeypatch.setattr(discussion_export, "stream_all", reads.stream)
    target = conversation_target(
        uuid.uuid4(),
        overrides.pop("conversation_id", uuid.uuid4()),
        kind=ConversationKind.SECONDARY,
    )
    chunks = [
        chunk
        async for chunk in stream_discussion_markdown(
            target,
            title="Trip to Lisbon",
            language="en",
            timezone="UTC",
            generated_at=INSTANT,
            batch=7,
        )
    ]
    return "".join(chunks)


class TestTheDocument:
    async def test_every_message_follows_the_header_in_the_order_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads = _Reads([_message("user", "First"), _message("assistant", "Second")])

        document = await _document(reads, monkeypatch)

        assert document.startswith("# Trip to Lisbon\n")
        assert document.index("First") < document.index("Second")
        # One rule under the header, one closing each message.
        assert document.count("\n---\n") == 3

    async def test_the_read_is_closed_at_the_instant_of_the_export_on_its_own_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads = _Reads([])
        conversation_id = uuid.uuid4()

        await _document(reads, monkeypatch, conversation_id=conversation_id)

        assert reads.asked == [(conversation_id, INSTANT)]
        assert reads.sessions == 1

    async def test_a_discussion_with_nothing_to_show_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document = await _document(_Reads([]), monkeypatch)

        assert document.startswith("# Trip to Lisbon\n")
        assert "No messages" in document
