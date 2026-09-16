"""Every e-mail provider produces the SAME vocabulary at its client boundary (ADR-287).

Until 2026-09-15 the "unified format" was the Gmail format: the Graph and IMAP
normalisers FABRICATED a ``payload.headers`` list, a Gmail ``labelIds`` and an
``internalDate`` so that readers written for Gmail would not notice — while
the Graph body stayed raw HTML (converted late, in the agent formatter) and the
IMAP body was flattened by a regex that lost every paragraph and link. A
third provider imitating the first is not a contract: the contract is the
:class:`EmailMessage` vocabulary, and each normaliser is measured against it
on a real-shaped payload. Gmail keeps its native tree until the builder drops
it (ADR-286); the two others fabricate nothing.
"""

from __future__ import annotations

import base64
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.normalizers.email_message import EmailMessage
from src.domains.connectors.clients.normalizers.email_normalizer import normalize_imap_message
from src.domains.connectors.clients.normalizers.html_text import html_to_text, strip_html_to_line
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    normalize_graph_message,
)
from src.domains.connectors.clients.normalizers.reply_trimming import MIN_KEPT_CHARS

pytestmark = [pytest.mark.unit]

HTML_BODY = (
    "<html><body><style>.x{color:red}</style><h1>Weekly digest</h1>"
    "<p>First paragraph with <b>bold</b> text.</p>"
    '<p>Read the <a href="https://example.com/very/long/tracking/url?utm_source=newsletter&amp;utm_id=1234567890">'
    "full story</a> online.</p><ul><li>One</li><li>Two</li></ul></body></html>"
)


def _gmail_full_html_only() -> dict[str, Any]:
    data = base64.urlsafe_b64encode(HTML_BODY.encode()).decode()
    return {
        "id": "18f0a1b2c3d4e5f6",
        "threadId": "18f0a1b2c3d4e5f0",
        "labelIds": ["UNREAD", "INBOX"],
        "snippet": "Weekly digest First paragraph",
        "internalDate": "1789493085929",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "To", "value": "bob@example.com"},
                {"name": "Subject", "value": "Weekly digest"},
                {"name": "Date", "value": "Tue, 15 Sep 2026 10:24:45 -0700"},
            ],
            "parts": [{"mimeType": "text/html", "body": {"data": data}}],
        },
    }


def _graph_message() -> dict[str, Any]:
    return {
        "id": "AAMk-1",
        "conversationId": "conv-1",
        "subject": "Weekly digest",
        "from": {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
        "toRecipients": [{"emailAddress": {"name": "Bob", "address": "bob@example.com"}}],
        "ccRecipients": [],
        "receivedDateTime": "2026-09-15T17:24:45Z",
        "isRead": False,
        "hasAttachments": True,
        "attachments": [
            {"id": "att-1", "name": "report.pdf", "contentType": "application/pdf", "size": 12}
        ],
        "body": {"contentType": "html", "content": HTML_BODY},
        "bodyPreview": "Weekly digest First paragraph",
    }


def _imap_message() -> SimpleNamespace:
    att = SimpleNamespace(filename="report.pdf", content_type="application/pdf", payload=b"x" * 12)
    return SimpleNamespace(
        uid="42",
        subject="Weekly digest",
        from_="alice@example.com",
        to=("bob@example.com",),
        cc=(),
        date=datetime(2026, 9, 15, 17, 24, 45),
        date_str="Tue, 15 Sep 2026 17:24:45 +0000",
        text="",
        html=HTML_BODY,
        attachments=[att],
        flags=(),
    )


def _assert_clean_text_body(body: str) -> None:
    assert "<" not in body, "the body is text, never markup"
    assert ".x{color:red}" not in body, "style blocks are dropped"
    assert "Weekly digest" in body
    assert "First paragraph with bold text." in body
    assert "\n" in body, "paragraphs survive as line breaks"
    assert "One" in body and "Two" in body
    assert "https://example.com/very/long/tracking/url" in body, "links survive with their url"


class TestTheThreeNormalisersSpeakOneVocabulary:
    def test_gmail_html_only_message(self) -> None:
        message = _gmail_full_html_only()
        GoogleGmailClient._normalize_message_fields(message, "full")

        contract = EmailMessage.model_validate(message)
        assert contract.provider == "google"
        assert contract.subject == "Weekly digest"
        assert contract.from_ == "Alice <alice@example.com>"
        assert contract.to == "bob@example.com"
        _assert_clean_text_body(contract.body)

    def test_graph_message(self) -> None:
        out = normalize_graph_message(_graph_message())

        assert "payload" not in out, "Graph fabricates no Gmail tree"
        contract = EmailMessage.model_validate(out)
        assert contract.provider == "microsoft"
        assert contract.from_ == "Alice <alice@example.com>"
        assert contract.to == "Bob <bob@example.com>"
        assert contract.attachments[0].filename == "report.pdf"
        assert "UNREAD" in contract.labelIds
        assert contract.internalDate and contract.internalDate.isdigit()
        _assert_clean_text_body(contract.body)

    def test_imap_message(self) -> None:
        out = normalize_imap_message(_imap_message(), "INBOX")

        assert "payload" not in out, "IMAP fabricates no Gmail tree"
        contract = EmailMessage.model_validate(out)
        assert contract.provider == "apple"
        assert contract.from_ == "alice@example.com"
        assert contract.attachments[0].filename == "report.pdf"
        assert contract.labelIds == ["INBOX", "UNREAD"]
        _assert_clean_text_body(contract.body)

    def test_a_text_body_is_never_touched(self) -> None:
        msg = _imap_message()
        msg.text = "Plain text with a < b comparison."
        out = normalize_imap_message(msg, "INBOX")
        assert out["body"] == "Plain text with a < b comparison."


REPLY_TEXT = (
    "Yes, Thursday at 10 works for me, I will book the room.\n\n"
    "On Tue, 15 Sep 2026 at 09:12, Alice <alice@example.com> wrote:\n"
    "> Could we move the review to Thursday?\n"
    "> Alice\n"
)
REPLY_HTML = (
    "<div>Yes, Thursday at 10 works for me, I will book the room.</div><br>"
    "<div>On Tue, 15 Sep 2026 at 09:12, Alice &lt;alice@example.com&gt; wrote:</div>"
    "<blockquote>Could we move the review to Thursday?<br>Alice</blockquote>"
)
OWN_WORDS = "Yes, Thursday at 10 works for me, I will book the room."


class TestTheQuotedHistoryLeavesAtTheClientBoundary:
    """ADR-287: a reply reaches every reader — the registry, the digest, the
    model — with the person's own words alone; the trimming is one door,
    :func:`clean_reply_body`, under the ``emails_trim_quoted_replies`` switch."""

    def test_gmail_reply(self) -> None:
        message = _gmail_full_html_only()
        data = base64.urlsafe_b64encode(REPLY_TEXT.encode()).decode()
        message["payload"]["parts"] = [{"mimeType": "text/plain", "body": {"data": data}}]
        GoogleGmailClient._normalize_message_fields(message, "full")
        assert message["body"] == OWN_WORDS

    def test_graph_reply(self) -> None:
        graph = _graph_message()
        graph["body"] = {"contentType": "html", "content": REPLY_HTML}
        assert normalize_graph_message(graph)["body"] == OWN_WORDS

    def test_imap_reply(self) -> None:
        msg = _imap_message()
        msg.text = REPLY_TEXT
        assert normalize_imap_message(msg, "INBOX")["body"] == OWN_WORDS

    def test_the_switch_keeps_the_body_whole(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "emails_trim_quoted_replies", False)
        msg = _imap_message()
        msg.text = REPLY_TEXT
        assert normalize_imap_message(msg, "INBOX")["body"] == REPLY_TEXT

    def test_a_bare_thanks_keeps_the_quote_it_answers(self) -> None:
        msg = _imap_message()
        msg.text = "Thanks!\n\nOn Tue, 15 Sep 2026 at 09:12, Alice wrote:\n> Room booked.\n"
        body = normalize_imap_message(msg, "INBOX")["body"]
        assert "Room booked." in body, "below MIN_KEPT_CHARS the quote is what the reader wants"
        assert len("Thanks!") < MIN_KEPT_CHARS


class TestOneHtmlToText:
    def test_html_to_text_keeps_structure_and_links(self) -> None:
        text = html_to_text(HTML_BODY)
        _assert_clean_text_body(text)
        assert (
            "[link](https://example.com/very/long/tracking/url" in text
        ), "a long link keeps its url behind a technical label (ADR-256)"

    def test_strip_html_to_line_is_for_snippets(self) -> None:
        line = strip_html_to_line("<p>HTML &amp; content</p><p>next</p>", max_length=200)
        assert line == "HTML & content next"
        assert strip_html_to_line("<p>" + "x" * 500 + "</p>", max_length=10) == "x" * 10
