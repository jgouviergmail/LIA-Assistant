"""A downloaded file's name is not trusted (ADR-262, ADR-369).

A document's display name can be a subject line a third party wrote; an
attachment's name is the sender's. Either travels into a ``Content-Disposition``
header: the quoted ASCII half keeps no control character and nothing that ends
the quoted string, and the UTF-8 half is percent-encoded whole.
"""

from __future__ import annotations

import pytest

from src.core.content_disposition import attachment_disposition, served_media_type

pytestmark = pytest.mark.unit

BACKSLASH = chr(92)
#: A name that tries everything at once: header injection (CRLF), an early end
#: of the quoted string (a double quote and a backslash), path separators, a NUL.
HOSTILE = 'Re: "urgent"\r\nX-Injected: 1\tand /etc/passwd' + BACKSLASH + "..\x00"


def test_no_control_character_or_quote_survives_in_the_quoted_half() -> None:
    head = attachment_disposition(HOSTILE, "document.md").split("; filename*=")[0]
    assert "\r" not in head and "\n" not in head and "\x00" not in head
    # The quoted string cannot be ended early: exactly two quotes remain.
    assert head.count('"') == 2
    assert BACKSLASH not in head


def test_the_utf8_half_is_percent_encoded_whole() -> None:
    tail = attachment_disposition(HOSTILE, "document.md").split("; filename*=UTF-8''")[1]
    assert "/" not in tail and "\r" not in tail and " " not in tail


def test_a_name_with_nothing_ascii_falls_back() -> None:
    value = attachment_disposition("会議のメモ", "document.md")
    assert 'filename="document.md"' in value
    # The UTF-8 half still carries the real name, percent-encoded.
    assert "filename*=UTF-8''" in value


def test_a_plain_name_is_preserved() -> None:
    assert attachment_disposition("report.pdf", "document.pdf") == (
        "attachment; filename=\"report.pdf\"; filename*=UTF-8''report.pdf"
    )


@pytest.mark.parametrize(
    ("declared", "served"),
    [
        ("application/pdf", "application/pdf"),
        ("image/svg+xml", "image/svg+xml"),
        ("text/html\r\nX-Injected: 1", "application/octet-stream"),
        ("", "application/octet-stream"),
        ("pdf", "application/octet-stream"),
    ],
)
def test_a_declared_type_is_served_only_when_it_is_one(declared: str, served: str) -> None:
    """The sender writes the type: a malformed one would be a header to forge."""
    assert served_media_type(declared) == served
