"""Answers kept lately: named by the person's request, else by the answer's beginning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.domains.radio.facts import FactKind
from src.domains.radio.readers.bookmarks import bookmark_drafts, kept_answers

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=7)


@dataclass
class Row:
    id: UUID
    created_at: datetime
    request_content: str | None
    content: str = "<p>The <b>answer</b>.</p>"


def test_the_week_s_kept_answers_newest_first_named_by_the_request() -> None:
    answers = kept_answers(
        [
            Row(UUID(int=1), NOW - timedelta(days=2), "How do **tides** work?"),
            Row(UUID(int=2), NOW - timedelta(hours=3), None),
            Row(UUID(int=3), NOW - timedelta(days=9), "Too old"),
        ],
        since=SINCE,
    )
    drafts = bookmark_drafts(answers, tz=UTC)
    assert [draft.text for draft in drafts] == [
        "On Saturday 2026-09-26, 04:00, the listener kept an answer of LIA's that begins: "
        '"The answer."',
        'On Thursday 2026-09-24, 07:00, the listener kept LIA\'s answer to: "How do tides work?"',
    ]
    assert {draft.kind for draft in drafts} == {FactKind.BOOKMARK}


def test_a_bookmark_that_says_nothing_is_skipped() -> None:
    assert kept_answers([Row(UUID(int=4), NOW, None, content="  ")], since=SINCE) == []
