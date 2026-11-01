"""A document's display name is not trusted (ADR-262).

Until the mail source, ``original_filename`` came from the account owner (an
upload) or from LIA itself (meeting minutes). A Gmail thread makes it a
SUBJECT LINE written by a third party — and that string travels into a
``Content-Disposition`` header, a zip archive and the interface. Two places
must therefore sanitise: the stored name (here), and the header that quotes it
(``core.content_disposition``, tested beside it).
"""

from __future__ import annotations

import pytest

from src.domains.rag_spaces.mail_render import RenderedThread, document_name

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
