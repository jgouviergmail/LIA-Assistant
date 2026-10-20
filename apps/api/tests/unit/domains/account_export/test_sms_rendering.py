"""Readable personal exports preserve third-party text without active markup."""

from html import unescape
from html.parser import HTMLParser

import pytest

from src.domains.account_export.builder import _render_sms

pytestmark = pytest.mark.unit


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def test_sms_sender_and_body_are_literal_without_losing_their_text():
    sender = "Alice <img src=https://tracker.invalid/sender> [account](https://evil.invalid)"
    body = (
        "Café 東京 &lt;tag&gt;\n<script>alert('x')</script>\n![tracker](https://tracker.invalid/body)\n"
        + chr(96) * 3
        + "\n$variable$ **own text**"
    )
    markdown = _render_sms(
        [
            {
                "received_at": "2026-10-19T09:00:00Z",
                "sender_encrypted": sender,
                "body_encrypted": body,
            }
        ],
        "fr",
    )
    parsed = Tags()
    parsed.feed(markdown)
    assert not parsed.tags
    assert "![tracker](" not in markdown and "[account](" not in markdown
    decoded = unescape(markdown)
    assert sender in decoded
    assert all(line in decoded for line in body.splitlines())
