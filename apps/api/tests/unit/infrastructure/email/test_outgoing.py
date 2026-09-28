"""One outgoing e-mail carrying a file (ADR-321).

Gmail, Apple and LIA's own relay all send MIME; what they share is built once.
What a reader of the message must find — whatever mail client they use — is
pinned by PARSING the bytes back, never by comparing strings.
"""

from __future__ import annotations

import email
from email.message import Message
from email.mime.text import MIMEText

import pytest

from src.infrastructure.email.outgoing import (
    MESSAGE_ENVELOPE_HEADROOM_BYTES,
    OutgoingAttachment,
    attachment_part,
    encoded_size,
    max_file_bytes,
    with_attachments,
)

pytestmark = pytest.mark.unit

_PDF = OutgoingAttachment(filename="rapport.pdf", mime_type="application/pdf", data=b"%PDF-1.7 x")


def _reparsed(message: Message) -> Message:
    return email.message_from_bytes(message.as_bytes())


class TestAttachmentPart:
    def test_the_reader_gets_the_same_bytes_under_the_same_name(self) -> None:
        part = _reparsed(attachment_part(_PDF))

        assert part.get_content_type() == "application/pdf"
        assert part.get_content_disposition() == "attachment"
        assert part.get_filename() == "rapport.pdf"
        assert part.get_payload(decode=True) == _PDF.data

    def test_a_name_with_accents_and_ideographs_survives(self) -> None:
        # RFC 2231: the parameter is encoded, never mangled into « ??? ».
        named = OutgoingAttachment(
            filename="Résumé 会议.md", mime_type="text/markdown", data="é".encode()
        )

        part = _reparsed(attachment_part(named))

        assert part.get_filename() == "Résumé 会议.md"

    def test_a_text_file_states_its_charset(self) -> None:
        markdown = OutgoingAttachment(
            filename="lia.md", mime_type="text/markdown", data="Été".encode(), charset="utf-8"
        )

        part = _reparsed(attachment_part(markdown))

        assert part.get_content_type() == "text/markdown"
        assert part.get_content_charset() == "utf-8"
        assert part.get_payload(decode=True).decode("utf-8") == "Été"

    def test_a_type_nobody_declared_is_sent_as_bytes(self) -> None:
        odd = OutgoingAttachment(filename="x.bin", mime_type="nonsense", data=b"\x00\x01")

        assert _reparsed(attachment_part(odd)).get_content_type() == "application/octet-stream"


class TestWithAttachments:
    def test_no_file_leaves_the_message_as_it_was(self) -> None:
        body = MIMEText("Bonjour", "plain", "utf-8")

        assert with_attachments(body, ()) is body

    def test_the_body_comes_first_then_the_file(self) -> None:
        body = MIMEText("Voici le document.", "plain", "utf-8")

        message = _reparsed(with_attachments(body, [_PDF]))

        assert message.get_content_type() == "multipart/mixed"
        first, second = message.get_payload()
        assert first.get_payload(decode=True).decode("utf-8") == "Voici le document."
        assert second.get_filename() == "rapport.pdf"


class TestSizeDerivation:
    @pytest.mark.parametrize("raw", [0, 1, 56, 57, 58, 114, 1_000_000, 3_000_000])
    def test_the_encoded_size_bounds_what_the_wire_carries(self, raw: int) -> None:
        part = attachment_part(OutgoingAttachment("f", "application/octet-stream", b"a" * raw))
        body = part.get_payload()
        assert isinstance(body, str)

        # Base64 lines of 76 characters, each ended by CRLF on the wire.
        wire = len(body.replace("\n", "\r\n"))
        assert wire <= encoded_size(raw)
        if raw % 57 == 0:
            assert wire == encoded_size(raw)

    @pytest.mark.parametrize("limit", [20_000_000, 36_700_160, 10_240_000])
    def test_the_largest_file_fills_the_message_and_one_more_line_would_not(
        self, limit: int
    ) -> None:
        largest = max_file_bytes(limit)

        assert encoded_size(largest) + MESSAGE_ENVELOPE_HEADROOM_BYTES <= limit
        assert encoded_size(largest + 57) + MESSAGE_ENVELOPE_HEADROOM_BYTES > limit

    def test_a_limit_smaller_than_the_envelope_leaves_no_room(self) -> None:
        assert max_file_bytes(MESSAGE_ENVELOPE_HEADROOM_BYTES - 1) == 0
