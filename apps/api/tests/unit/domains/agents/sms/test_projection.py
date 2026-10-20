"""External SMS projections keep exact Unicode pagination under a real token cap."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.agents.sms.projection import SmsToolPage, project_page, projection_tokens
from src.domains.sms.read_schemas import SmsPage, SmsView


def page(body):
    return SmsPage(
        items=[
            SmsView(
                id=uuid4(),
                sender="+33123456789",
                display_name="Contact",
                body=body,
                received_at=datetime.now(UTC),
                date_kind="received",
                origin="iphone",
            )
        ],
        total=9,
        as_of=datetime.now(UTC),
        revision=7,
        next_cursor="opaque-next",
    )


@pytest.mark.parametrize(
    "body",
    ["Bonjour " * 3000, "你好🙂" * 4000, "<|endoftext|>" * 1000, "<script>alert(1)</script>" * 500],
    ids=["long-ascii", "long-cjk-emoji", "token-delimiters", "html-literal"],
)
def test_page_budget_and_exact_unicode_continuation(body):
    source = page(body)
    offset = 0
    parts = []
    while True:
        result = project_page(source, owner=source.items[0].id, body_offset=offset, budget=1500)
        assert projection_tokens(result.model_dump_json()) <= 1500
        assert result.total == 9 and result.next_cursor == "opaque-next"
        assert result.revision == 7
        restored = SmsToolPage.model_validate_json(result.model_dump_json())
        assert restored == result
        item = result.sms_messages[0]
        parts.append(item.body)
        assert item.body_offset == offset
        if item.next_body_offset is None:
            break
        assert item.next_body_offset > offset
        offset = item.next_body_offset
    assert "".join(parts) == body


def test_invalid_offset_never_silently_changes_a_read():
    with pytest.raises(ValueError):
        project_page(page("abc"), owner=uuid4(), body_offset=4)


def test_small_context_refuses_metadata_it_cannot_publish_whole():
    with pytest.raises(ValueError):
        project_page(page("abc"), owner=uuid4(), budget=8)


def test_tokenizer_failure_is_a_conservative_unicode_bound(monkeypatch):
    from src.domains.agents.utils import token_utils

    def unavailable(*args, **kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr(token_utils.tiktoken, "get_encoding", unavailable)
    text = "你好🙂<|endoftext|>"
    assert projection_tokens(text) == len(text.encode("utf-8"))


def test_multi_message_page_reserves_progress_for_every_body():
    source = page("Bonjour " * 4000)
    source = source.model_copy(
        update={"items": [source.items[0].model_copy(update={"id": uuid4()}) for _ in range(3)]}
    )
    result = project_page(source, owner=uuid4(), budget=1500)
    assert len(result.sms_messages) == 3
    assert all(item.body and item.next_body_offset for item in result.sms_messages)
    assert projection_tokens(result.model_dump_json()) <= 1500
