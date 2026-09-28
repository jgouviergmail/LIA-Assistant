"""LIA's own relay carries a file too (ADR-321).

Without a connected mailbox, a person sends a generated file or an answer to
their OWN verified address through the instance's relay. The reader must find
the typed words (both alternatives) and the file — read back as a mail client
would, from the bytes handed to SMTP.
"""

from __future__ import annotations

import email
from email.header import decode_header, make_header
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.email.email_service import EmailService
from src.infrastructure.email.outgoing import OutgoingAttachment

pytestmark = pytest.mark.unit


@pytest.fixture
def relay() -> EmailService:
    with patch("src.infrastructure.email.email_service.settings") as settings:
        settings.smtp_host = "smtp.example.com"
        settings.smtp_port = 587
        settings.smtp_user = ""
        settings.smtp_password = ""
        settings.smtp_from = "noreply@example.com"
        return EmailService()


async def test_the_file_follows_both_alternatives(relay: EmailService) -> None:
    deliver = MagicMock()
    note = OutgoingAttachment(
        filename="lia-2026-09-25.md", mime_type="text/markdown", data=b"# Hi", charset="utf-8"
    )

    with patch.object(relay, "_deliver", deliver):
        sent = await relay.send_email(
            "me@example.com", "Réponse de LIA", "<pre>Voici</pre>", "Voici", attachments=[note]
        )

    assert sent is True
    to_email, payload = deliver.call_args.args
    assert to_email == "me@example.com"
    message = email.message_from_string(payload)
    assert message.get_content_type() == "multipart/mixed"
    assert str(make_header(decode_header(message["Subject"]))) == "Réponse de LIA"
    alternative, attached = message.get_payload()
    assert alternative.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in alternative.get_payload()] == ["text/plain", "text/html"]
    assert attached.get_filename() == "lia-2026-09-25.md"
    assert attached.get_payload(decode=True) == b"# Hi"


async def test_without_a_file_the_message_is_built_as_before(relay: EmailService) -> None:
    deliver = MagicMock()

    with patch.object(relay, "_deliver", deliver):
        await relay.send_email("me@example.com", "Hi", "<p>x</p>", "x")

    message = email.message_from_string(deliver.call_args.args[1])
    assert message.get_content_type() == "multipart/alternative"
