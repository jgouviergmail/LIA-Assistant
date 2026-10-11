"""Unicode and prompt-like text must fit without losing a continuation marker."""

import json
from datetime import UTC, datetime

import pytest
import tiktoken

from src.infrastructure.meeting_reads import MeetingReadPage

pytestmark = pytest.mark.unit


def test_dense_unicode_and_special_tokens_are_counted_without_silent_cut() -> None:
    from src.domains.agents.application.meeting_read_budget import bound_meeting_page

    text = "中文🎙️<|endoftext|>" * 1000
    page = MeetingReadPage(
        view="transcript",
        observed_at=datetime.now(UTC),
        total=len(text),
        offset=0,
        text=text,
        next_offset=None,
        source_digest="a" * 64,
        content_format="json_fragment",
    )
    bounded = bound_meeting_page(page, 800)
    serialized = json.dumps(bounded.model_dump(mode="json"), ensure_ascii=False, default=str)
    from src.core.config import settings

    assert (
        len(
            tiktoken.get_encoding(settings.token_encoding_name).encode(
                serialized, disallowed_special=()
            )
        )
        <= 800
    )
    assert bounded.text and text.startswith(bounded.text)
    assert bounded.next_offset == len(bounded.text)
    assert bounded.source_digest == page.source_digest and bounded.total == page.total


def test_list_budget_keeps_whole_items_and_the_original_total() -> None:
    from src.domains.agents.application.meeting_read_budget import bound_meeting_page

    page = MeetingReadPage(
        view="list",
        observed_at=datetime.now(UTC),
        total=20,
        offset=5,
        data={"items": [{"id": str(i), "title": "中文 " * 80} for i in range(10)]},
    )
    bounded = bound_meeting_page(page, 500)
    assert 0 < len(bounded.data["items"]) < 10
    assert bounded.data["items"][0] == page.data["items"][0]
    assert bounded.next_offset == page.offset + len(bounded.data["items"])
    assert bounded.total == 20


def test_impossible_metadata_budget_fails_without_returning_a_partial_json_object() -> None:
    from src.domains.agents.application.meeting_read_budget import bound_meeting_page

    page = MeetingReadPage(
        view="detail",
        observed_at=datetime.now(UTC),
        total=1,
        offset=0,
        data={"id": "opaque", "status": "ready"},
    )
    with pytest.raises(ValueError):
        bound_meeting_page(page, 1)
