"""What only helps a model read a sentence is cut to its bound, never refused (ADR-372)."""

from __future__ import annotations

import pytest

from src.core.constants import (
    TOOL_ASSIST_LABELS_MAX,
    TOOL_ASSIST_LISTS_MAX,
    TOOL_ASSIST_RECIPIENT_MAX_CHARS,
)
from src.domains.tool_assists.schemas import (
    ComposeAssist,
    FilterSentenceAssist,
    TaskSentenceAssist,
)

pytestmark = pytest.mark.unit


def test_more_lists_than_a_sentence_is_read_against_are_no_refusal() -> None:
    names = [f"List {index}" for index in range(TOOL_ASSIST_LISTS_MAX + 5)]

    asked = TaskSentenceAssist(sentence="call the plumber", lists=names)

    assert asked.lists == names[:TOOL_ASSIST_LISTS_MAX]


def test_more_labels_than_a_sentence_is_read_against_are_no_refusal() -> None:
    names = [f"Label {index}" for index in range(TOOL_ASSIST_LABELS_MAX + 5)]

    asked = FilterSentenceAssist(sentence="from Ana", labels=names)

    assert asked.labels == names[:TOOL_ASSIST_LABELS_MAX]


def test_a_long_list_of_recipients_is_told_as_far_as_its_bound() -> None:
    typed = "ana@example.org, " * TOOL_ASSIST_RECIPIENT_MAX_CHARS

    asked = ComposeAssist(instruction="say hello", recipient=typed)

    assert asked.recipient == typed[:TOOL_ASSIST_RECIPIENT_MAX_CHARS]
