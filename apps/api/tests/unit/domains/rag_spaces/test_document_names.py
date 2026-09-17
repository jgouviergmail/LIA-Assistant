"""One sanitiser for every display name a third party or a person wrote.

``document_name`` of the mail source (ADR-262) sanitised a Gmail subject; a
kept answer's request (part A of the 2026-09-16 design) is a person's words
and travels the same way — into a ``Content-Disposition`` header, a zip member
and the interface. Two sanitisers would drift on the next hostile character,
so the mail renderer now delegates to this one.
"""

from __future__ import annotations

import pytest

from src.domains.rag_spaces.document_names import sanitize_document_name
from src.domains.rag_spaces.mail_render import RenderedThread, document_name

pytestmark = pytest.mark.unit

BACKSLASH = chr(92)
HOSTILE = 'Re: "urgent"\r\nX-Injected: 1\tand /etc/passwd' + BACKSLASH + "..\x00"


def test_control_characters_and_separators_are_replaced_by_spaces() -> None:
    name = sanitize_document_name(HOSTILE, fallback="t1", extension=".md")
    assert "\r" not in name and "\n" not in name and "\x00" not in name
    assert "/" not in name and BACKSLASH not in name
    assert name.endswith(".md")


def test_a_name_of_only_noise_takes_the_fallback() -> None:
    assert sanitize_document_name("\r\n\x00///", fallback="t-42", extension=".md") == "t-42.md"


def test_a_normal_name_is_left_alone() -> None:
    assert sanitize_document_name("Budget 2027 — révision", fallback="x", extension=".md") == (
        "Budget 2027 — révision.md"
    )


def test_the_name_is_bounded_by_the_shared_cap() -> None:
    name = sanitize_document_name("x" * 5_000, fallback="x", extension=".md")
    assert len(name) <= 203


def test_the_mail_renderer_delegates_to_the_shared_sanitiser() -> None:
    rendered = RenderedThread(
        markdown="", subject=HOSTILE, last_message_at=None, message_count=1, truncated=False
    )
    assert document_name(rendered, "t1") == sanitize_document_name(
        HOSTILE, fallback="t1", extension=".md"
    )
