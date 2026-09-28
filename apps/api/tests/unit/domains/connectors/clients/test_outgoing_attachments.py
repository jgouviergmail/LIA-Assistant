"""A file sent from the connected mailbox, on the three providers alike (ADR-321).

The parity contract holds the SIGNATURE (``test_provider_parity_contract``);
this module holds the BEHAVIOUR: whichever mailbox the person connected, the
reader receives the typed words and the file, under its name. Every message is
read back the way a mail client would read it — parsed, never string-compared.
"""

from __future__ import annotations

import base64
import email
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import (
    APPLE_MAIL_MESSAGE_MAX_BYTES,
    GMAIL_SEND_MESSAGE_MAX_BYTES,
    GOOGLE_GMAIL_UPLOAD_BASE_URL,
    OUTLOOK_INLINE_ATTACHMENT_MAX_BYTES,
)
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from src.infrastructure.email.outgoing import OutgoingAttachment, max_file_bytes

pytestmark = pytest.mark.unit

_FILE = OutgoingAttachment(filename="Compte rendu é.pdf", mime_type="application/pdf", data=b"%PDF")
_NOTE = OutgoingAttachment(
    filename="lia-2026-09-25.md",
    mime_type="text/markdown",
    data="# Réponse".encode(),
    charset="utf-8",
)


def _oauth_credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        token_type="Bearer",
    )


def _header(message: Message, name: str) -> str:
    return str(make_header(decode_header(message[name])))


def _parts(message: Message) -> tuple[Message, list[Message]]:
    body, *files = message.get_payload()
    return body, files


class TestGmail:
    @pytest.fixture
    def gmail(self) -> tuple[GoogleGmailClient, AsyncMock]:
        client = GoogleGmailClient(uuid4(), _oauth_credentials(), MagicMock())
        spy = AsyncMock(return_value={"id": "m1", "threadId": "t1"})
        client._make_request = spy  # type: ignore[method-assign]
        return client, spy

    async def test_a_file_leaves_through_the_upload_uri_as_raw_rfc822(
        self, gmail: tuple[GoogleGmailClient, AsyncMock]
    ) -> None:
        client, spy = gmail

        await client.send_email(
            to="bob@example.com", subject="Été", body="Voici.", attachments=[_FILE]
        )

        args, kwargs = spy.await_args
        assert args == ("POST", "/users/me/messages/send")
        assert kwargs["base_url"] == GOOGLE_GMAIL_UPLOAD_BASE_URL
        assert kwargs["params"] == {"uploadType": "media"}
        assert kwargs["extra_headers"] == {"Content-Type": "message/rfc822"}
        message = email.message_from_bytes(kwargs["content"])
        assert _header(message, "Subject") == "Été"
        assert _header(message, "To") == "bob@example.com"
        body, (attached,) = _parts(message)
        assert body.get_payload(decode=True).decode("utf-8") == "Voici."
        assert attached.get_filename() == _FILE.filename
        assert attached.get_payload(decode=True) == _FILE.data

    async def test_a_message_without_a_file_is_sent_exactly_as_before(
        self, gmail: tuple[GoogleGmailClient, AsyncMock]
    ) -> None:
        client, spy = gmail

        await client.send_email(to="bob@example.com", subject="Hi", body="x")

        args, kwargs = spy.await_args
        assert args == ("POST", "/users/me/messages/send")
        assert set(kwargs) == {"json_data"}
        assert "raw" in kwargs["json_data"]

    async def test_a_forward_keeps_every_file_it_could_read(
        self, gmail: tuple[GoogleGmailClient, AsyncMock]
    ) -> None:
        # The forward builds its parts with the shared outgoing part: one file
        # that cannot be downloaded must not cost the others.
        client, spy = gmail
        client.get_message = AsyncMock(  # type: ignore[method-assign]
            return_value={"payload": {"headers": [{"name": "Subject", "value": "Devis"}]}}
        )
        client._extract_attachment_info = MagicMock(  # type: ignore[method-assign]
            return_value=[
                {"attachment_id": "a1", "filename": "devis.pdf", "mime_type": "application/pdf"},
                {"attachment_id": "a2", "filename": "plan.png", "mime_type": "image/png"},
            ]
        )
        client.get_attachment = AsyncMock(  # type: ignore[method-assign]
            side_effect=[ConnectionError("gone"), b"\x89PNG"]
        )

        await client.forward_email("m1", to="bob@example.com")

        # A forward carrying files leaves through the upload URI too: through
        # the metadata URI, anything past about 1 MiB was refused.
        kwargs = spy.await_args.kwargs
        assert kwargs["base_url"] == GOOGLE_GMAIL_UPLOAD_BASE_URL
        message = email.message_from_bytes(kwargs["content"])
        _body, files = _parts(message)
        assert [(f.get_filename(), f.get_content_type()) for f in files] == [
            ("plan.png", "image/png")
        ]
        assert files[0].get_payload(decode=True) == b"\x89PNG"


class TestOutlook:
    @pytest.fixture
    def outlook(self) -> tuple[MicrosoftOutlookClient, AsyncMock]:
        client = MicrosoftOutlookClient(uuid4(), _oauth_credentials(), MagicMock())
        spy = AsyncMock(return_value={})
        client._make_request = spy  # type: ignore[method-assign]
        return client, spy

    async def test_a_file_rides_in_the_request_as_a_file_attachment(
        self, outlook: tuple[MicrosoftOutlookClient, AsyncMock]
    ) -> None:
        client, spy = outlook

        await client.send_email(
            to="bob@example.com", subject="Hi", body="Voici.", attachments=[_FILE, _NOTE]
        )

        message = spy.await_args.kwargs["json_data"]["message"]
        pdf, note = message["attachments"]
        assert pdf == {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": _FILE.filename,
            "contentType": "application/pdf",
            "contentBytes": base64.b64encode(_FILE.data).decode("ascii"),
        }
        assert note["contentType"] == "text/markdown; charset=utf-8"
        assert base64.b64decode(note["contentBytes"]) == _NOTE.data

    async def test_no_file_adds_no_attachments_key(
        self, outlook: tuple[MicrosoftOutlookClient, AsyncMock]
    ) -> None:
        client, spy = outlook

        await client.send_email(to="bob@example.com", subject="Hi", body="x")

        assert "attachments" not in spy.await_args.kwargs["json_data"]["message"]


class TestApple:
    async def test_the_file_follows_the_body_in_one_mixed_message(self) -> None:
        client = AppleEmailClient(
            uuid4(), AppleCredentials(apple_id="jane@icloud.com", app_password="p"), MagicMock()
        )
        sent: dict[str, Any] = {}

        async def _capture(recipients: list[str], msg: Message) -> None:
            sent["recipients"] = recipients
            sent["msg"] = msg

        with patch.object(client, "_smtp_send", AsyncMock(side_effect=_capture)):
            await client._send_email_impl(
                "bob@example.com", "Été", "Voici.", None, None, False, [_FILE]
            )

        message = email.message_from_bytes(sent["msg"].as_bytes())
        assert message.get_content_type() == "multipart/mixed"
        assert _header(message, "Subject") == "Été"
        body, (attached,) = _parts(message)
        assert body.get_payload(decode=True).decode("utf-8") == "Voici."
        assert attached.get_content_type() == "application/pdf"
        assert attached.get_filename() == _FILE.filename
        assert sent["recipients"] == ["bob@example.com"]


class TestPublishedCeilings:
    """Each road states the largest file it takes — derived from its provider."""

    def test_every_mailbox_provider_declares_its_ceiling(self) -> None:
        for connector_type in CONNECTOR_FUNCTIONAL_CATEGORIES["email"]:
            client_class = ClientRegistry.get_client_class(connector_type)
            assert client_class is not None
            assert client_class.OUTGOING_FILE_MAX_BYTES > 0, connector_type

    def test_each_ceiling_is_derived_from_what_the_provider_documents(self) -> None:
        assert GoogleGmailClient.OUTGOING_FILE_MAX_BYTES == max_file_bytes(
            GMAIL_SEND_MESSAGE_MAX_BYTES
        )
        assert AppleEmailClient.OUTGOING_FILE_MAX_BYTES == max_file_bytes(
            APPLE_MAIL_MESSAGE_MAX_BYTES
        )
        assert MicrosoftOutlookClient.OUTGOING_FILE_MAX_BYTES == (
            OUTLOOK_INLINE_ATTACHMENT_MAX_BYTES
        )
