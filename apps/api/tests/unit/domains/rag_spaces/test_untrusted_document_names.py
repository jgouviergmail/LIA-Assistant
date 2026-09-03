"""A document's display name is not trusted (ADR-262).

Until the mail source, ``original_filename`` came from the account owner (an
upload) or from LIA itself (meeting minutes). A Gmail thread makes it a
SUBJECT LINE written by a third party — and that string travels into a
``Content-Disposition`` header, a zip archive and the interface. Two places
must therefore sanitise: the stored name, and the header that quotes it.
"""

from __future__ import annotations

import pytest

from src.domains.rag_spaces.mail_render import RenderedThread, document_name
from src.domains.rag_spaces.router import _attachment

pytestmark = pytest.mark.unit

BACKSLASH = chr(92)
#: A subject that tries everything at once: header injection (CRLF), an early
#: end of the quoted string (a double quote and a backslash), path separators
#: and a NUL.
HOSTILE = 'Re: "urgent"\r\nX-Injected: 1\tand /etc/passwd' + BACKSLASH + "..\x00"


def _rendered(subject: str) -> RenderedThread:
    return RenderedThread(
        markdown="",
        subject=subject,
        last_message_at=None,
        message_count=1,
        truncated=False,
    )


class TestStoredName:
    def test_control_characters_and_separators_never_reach_the_stored_name(self) -> None:
        name = document_name(_rendered(HOSTILE), "t1")
        assert "\r" not in name and "\n" not in name and "\x00" not in name
        assert "/" not in name and BACKSLASH not in name
        assert name.endswith(".md")

    def test_a_subject_of_only_noise_falls_back_to_the_thread_id(self) -> None:
        assert document_name(_rendered("\r\n\x00///"), "t-42") == "t-42.md"

    def test_a_normal_subject_is_left_alone(self) -> None:
        assert document_name(_rendered("Budget 2027 — révision"), "t1") == (
            "Budget 2027 — révision.md"
        )

    def test_the_name_is_bounded(self) -> None:
        assert len(document_name(_rendered("x" * 5_000), "t1")) <= 203


class TestAttachmentHeader:
    def test_no_control_character_or_quote_survives_in_the_quoted_half(self) -> None:
        value = _attachment(HOSTILE, "document.md")["Content-Disposition"]
        head = value.split("; filename*=")[0]
        assert "\r" not in head and "\n" not in head and "\x00" not in head
        # The quoted string cannot be ended early: exactly two quotes remain.
        assert head.count('"') == 2
        assert BACKSLASH not in head

    def test_a_name_with_nothing_ascii_falls_back(self) -> None:
        value = _attachment("会議のメモ", "document.md")["Content-Disposition"]
        assert 'filename="document.md"' in value
        # The UTF-8 half still carries the real name, percent-encoded.
        assert "filename*=UTF-8''" in value

    def test_a_plain_name_is_preserved(self) -> None:
        value = _attachment("report.pdf", "document.pdf")["Content-Disposition"]
        assert 'filename="report.pdf"' in value
