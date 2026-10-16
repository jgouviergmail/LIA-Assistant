"""How an Apple (IMAP/SMTP) message is composed, for a send and a draft alike (ADR-344).

A draft saved with APPEND must be the message the send would have sent. Two
defects the shared composition closed: a display name outside ASCII encoded the
WHOLE recipient header — addresses included — so readers saw a name and no
address; and a reply to all copied every recipient instead of answering the
other ``To`` recipients where mail clients put them.
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart

import pytest

from src.domains.connectors.clients.apple_compose import (
    forward_message,
    new_message,
    reply_message,
)
from src.domains.connectors.clients.mailbox_drafts import prepare_for_smtp
from src.infrastructure.email.outgoing import OutgoingAttachment

pytestmark = pytest.mark.unit

ME = "jane@icloud.com"
ORIGINAL = {
    "from": "Bob Martin <bob@example.com>",
    "to": "jane@icloud.com, carol@example.com",
    "cc": "dave@example.com",
    "subject": "Quarterly report",
    "date": "Mon, 20 Jul 2026 09:00:00 +0000",
    "body": "Original body",
    "rfc_message_id": "<original@example.com>",
}


def _text(message: MIMEMultipart) -> str:
    part = message.get_payload()[0]
    payload = part.get_payload(decode=True)
    assert isinstance(payload, bytes)
    return payload.decode("utf-8")


class TestNewMessage:
    def test_a_name_outside_ascii_keeps_its_address_readable(self) -> None:
        message = new_message(
            sender=ME,
            to="Élodie Exemple <elodie@example.com>, bob@example.com",
            subject="Été",
            body="Bonjour",
        )

        assert "<elodie@example.com>, bob@example.com" in message.as_string()
        assert message["From"] == ME
        assert message["Message-ID"] and message["Date"]

    def test_a_blind_copy_is_kept_for_a_draft_and_left_out_of_the_send(self) -> None:
        message = new_message(
            sender=ME, to="bob@example.com", subject="Hi", body="Body", bcc="boss@example.com"
        )
        assert message["Bcc"] == "boss@example.com"

        recipients = prepare_for_smtp(message)

        assert recipients == ["bob@example.com", "boss@example.com"]
        assert message["Bcc"] is None

    def test_a_draft_may_have_no_recipient_yet(self) -> None:
        assert new_message(sender=ME, to="", subject="Idée", body="…")["To"] is None

    def test_files_follow_the_body(self) -> None:
        message = new_message(
            sender=ME,
            to="bob@example.com",
            subject="Hi",
            body="Body",
            attachments=[OutgoingAttachment("a.pdf", "application/pdf", b"%PDF")],
        )

        assert [p.get_filename() for p in message.get_payload()[1:]] == ["a.pdf"]


class TestReplyMessage:
    def test_a_reply_uses_the_original_reply_to_header(self) -> None:
        message = reply_message(
            {**ORIGINAL, "reply_to": "Help <help@example.com>"}, "Thanks", sender=ME
        )

        assert message["To"] == "Help <help@example.com>"

    def test_a_reply_to_all_answers_the_others_and_never_the_person(self) -> None:
        message = reply_message(ORIGINAL, "Thanks", sender=ME, reply_all=True)

        assert message["To"] == "Bob Martin <bob@example.com>, carol@example.com"
        assert message["Cc"] == "dave@example.com"
        assert message["In-Reply-To"] == "<original@example.com>"
        assert message["Subject"] == "Re: Quarterly report"
        assert _text(message).startswith("Thanks\n\nOn Mon, 20 Jul 2026")
        assert "> Original body" in _text(message)

    def test_a_chosen_recipient_replaces_the_sender(self) -> None:
        message = reply_message(ORIGINAL, "Thanks", sender=ME, override_to="erin@example.com")

        assert (message["To"], message["Cc"]) == ("erin@example.com", None)


class TestForwardMessage:
    def test_a_forward_carries_the_original_and_its_files(self) -> None:
        message = forward_message(
            ORIGINAL,
            [OutgoingAttachment("report.pdf", "application/pdf", b"%PDF")],
            sender=ME,
            to="erin@example.com",
            body="FYI",
        )

        assert message["Subject"] == "Fwd: Quarterly report"
        assert _text(message).startswith("FYI\n\n---------- Forwarded message ---------\n")
        assert message.get_payload()[1].get_all("Content-Type") == ["application/pdf"]
